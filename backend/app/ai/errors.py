"""
Error handling for Google Gemini calls.

The old implementation looked for the text "503" or "429" anywhere inside
``str(exc)``. That is fragile (an unrelated number in a JSON error body
could match) and it threw away the one piece of information that matters
most for rate limits: *how long to wait*.

Here we read the structured fields on ``google.genai.errors.APIError``
(``code``, ``status``, ``details``) and turn them into a small hierarchy
the rest of the app can reason about:

    retryable  - worth trying again after a short wait (429 / 5xx / timeout)
    quota      - the *daily* quota is gone; waiting a few seconds won't help
    permanent  - bad key, bad request, malformed output ...
"""

from __future__ import annotations

import re
from typing import Any


class AIServiceError(Exception):
    """Raised when the AI service cannot complete a request."""

    status_code: int = 503
    retryable: bool = True
    # Whether switching to the fallback model could help.
    try_fallback: bool = True

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        drop_thinking: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        # Set when the API rejected the thinking config for this model.
        self.drop_thinking = drop_thinking

    def __str__(self) -> str:
        return self.message


class AIConfigError(AIServiceError):
    status_code = 500
    retryable = False
    try_fallback = False


class AIRateLimitError(AIServiceError):
    status_code = 429


class AIQuotaError(AIServiceError):
    """Daily / project quota exhausted. Retrying within the run is pointless."""

    status_code = 429
    retryable = False


class AIOverloadedError(AIServiceError):
    status_code = 503


class AIResponseError(AIServiceError):
    """The model answered, but not with usable JSON."""

    status_code = 502
    retryable = True       # one more attempt often fixes it
    try_fallback = False


class AIRequestError(AIServiceError):
    """4xx other than rate limiting: the request itself is the problem."""

    status_code = 502
    retryable = False
    try_fallback = False


class AIModelNotFoundError(AIServiceError):
    status_code = 502
    retryable = False
    try_fallback = True    # a fallback model may still work


_FRIENDLY = {
    AIRateLimitError: (
        "The AI service is rate-limited right now. "
        "Please wait a minute and try again."
    ),
    AIQuotaError: (
        "The AI usage quota for today has been reached. "
        "Please try again later."
    ),
    AIOverloadedError: (
        "The AI service is temporarily overloaded. "
        "Please try again in a few minutes."
    ),
    AIResponseError: (
        "The AI returned an invalid response. Please try again."
    ),
    AIModelNotFoundError: (
        "The configured AI model is not available. "
        "Check GEMINI_MODEL in your environment."
    ),
}

_AUTH_MESSAGE = (
    "The AI service rejected the API key. "
    "Check GOOGLE_API_KEY in your environment."
)

_DEFAULT_MESSAGE = (
    "The AI service is currently unavailable. Please try again later."
)


# ── helpers ───────────────────────────────────────────────────────────────

_DELAY_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*s?\s*$")


def _error_body(exc: Exception) -> dict[str, Any]:
    details = getattr(exc, "details", None)

    if isinstance(details, dict):
        inner = details.get("error")

        if isinstance(inner, dict):
            return inner

        return details

    return {}


def _detail_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items = body.get("details")

    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]

    return []


def parse_retry_delay(exc: Exception) -> float | None:
    """Pull the server-suggested wait (``RetryInfo.retryDelay``) if present."""

    for item in _detail_items(_error_body(exc)):
        if str(item.get("@type", "")).endswith("RetryInfo"):
            match = _DELAY_RE.match(str(item.get("retryDelay", "")))

            if match:
                return float(match.group(1))

    return None


def _is_daily_quota(exc: Exception) -> bool:
    body = _error_body(exc)

    for item in _detail_items(body):
        if str(item.get("@type", "")).endswith("QuotaFailure"):
            for violation in item.get("violations", []) or []:
                quota_id = str(violation.get("quotaId", ""))

                if "PerDay" in quota_id:
                    return True

    message = str(body.get("message") or getattr(exc, "message", "") or "")

    return "per day" in message.lower()


def _rejects_thinking(exc: Exception) -> bool:
    message = str(
        _error_body(exc).get("message")
        or getattr(exc, "message", "")
        or exc
    ).lower()

    return "thinking" in message


def _looks_like_network_failure(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True

    name = type(exc).__name__.lower()

    return any(
        marker in name
        for marker in ("timeout", "connect", "readerror", "remoteprotocol")
    )


# ── public API ────────────────────────────────────────────────────────────

def classify_error(exc: Exception) -> AIServiceError:
    """Convert any exception raised by the Gemini SDK into an AIServiceError."""

    if isinstance(exc, AIServiceError):
        return exc

    code = getattr(exc, "code", None)
    retry_after = parse_retry_delay(exc)

    if isinstance(code, int):
        if code == 429:
            if _is_daily_quota(exc):
                return AIQuotaError(_FRIENDLY[AIQuotaError])

            return AIRateLimitError(
                _FRIENDLY[AIRateLimitError],
                retry_after=retry_after,
            )

        if code in (500, 502, 503, 504):
            return AIOverloadedError(
                _FRIENDLY[AIOverloadedError],
                retry_after=retry_after,
            )

        if code in (401, 403):
            return AIConfigError(_AUTH_MESSAGE)

        if code == 404:
            return AIModelNotFoundError(_FRIENDLY[AIModelNotFoundError])

        if code == 400:
            return AIRequestError(
                "The AI service could not process this request.",
                drop_thinking=_rejects_thinking(exc),
            )

        return AIRequestError(_DEFAULT_MESSAGE)

    if _looks_like_network_failure(exc):
        return AIOverloadedError(_FRIENDLY[AIOverloadedError])

    return AIServiceError(_DEFAULT_MESSAGE)


# Backwards compatible name used by older call sites.
def handle_ai_error(exc: Exception) -> AIServiceError:
    return classify_error(exc)


def user_message(exc: AIServiceError) -> str:
    return exc.message or _DEFAULT_MESSAGE
