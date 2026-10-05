"""
Single entry point for every Gemini call in Trace.

Why this exists
---------------
Before, ``analyze_resume`` and ``analyze_job`` each built a brand-new client
and fired a request with no pacing, no retry, no timeout and no backoff. The
hourly worker called ``analyze_job`` back-to-back for every job on every
board, so it burst straight through the per-minute quota, and because
failures were never recorded the same jobs were retried again the next hour.
The key stayed "busy" for the resume-upload endpoint too, because quotas are
per project, not per request path.

This gateway fixes the *request side* of that problem:

* one cached client (with a request timeout)
* pacing between background calls (``GEMINI_MIN_INTERVAL_SECONDS``)
* retry with exponential backoff + jitter, honouring the server's
  ``retryDelay`` hint on 429s
* a fallback model (separate quota bucket) when the primary is overloaded
* JSON response mode and a low thinking level - extraction work does not
  need the default "medium" reasoning budget

The *queue side* (how many calls the worker makes per run) lives in
``worker/monitor.py``.
"""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import types

from app.ai.errors import (
    AIConfigError,
    AIResponseError,
    AIServiceError,
    classify_error,
)
from app.core.config import settings


logger = logging.getLogger("trace.ai")


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_INVALID_JSON_MESSAGE = (
    "The AI returned an invalid response. Please try again."
)


# ── usage counters (handy for the worker's end-of-run summary) ────────────

@dataclass
class GeminiStats:
    calls: int = 0
    failures: int = 0
    retries: int = 0
    fallbacks: int = 0


stats = GeminiStats()


def reset_stats() -> None:
    global stats
    stats = GeminiStats()


# ── client ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    if not settings.GOOGLE_API_KEY:
        raise AIConfigError("GOOGLE_API_KEY is not configured.")

    return genai.Client(
        api_key=settings.GOOGLE_API_KEY,
        http_options=types.HttpOptions(
            timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000),
        ),
    )


def _model_chain() -> list[str]:
    primary = (settings.GEMINI_MODEL or "").strip()

    if not primary:
        raise AIConfigError("GEMINI_MODEL is not configured.")

    chain = [primary]

    fallback = (settings.GEMINI_FALLBACK_MODEL or "").strip()

    if fallback and fallback != primary:
        chain.append(fallback)

    return chain


def _build_config(use_thinking: bool) -> types.GenerateContentConfig:
    kwargs: dict[str, Any] = {"response_mime_type": "application/json"}

    # NOTE: temperature is intentionally left at the API default. Google
    # recommends the default for Gemini 3 models; lowering it can cause
    # looping or degraded output.
    level = (settings.GEMINI_THINKING_LEVEL or "").strip()

    if use_thinking and level:
        try:
            kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(level.upper()),
            )
        except ValueError:
            logger.warning(
                "Ignoring invalid GEMINI_THINKING_LEVEL=%r", level,
            )

    return types.GenerateContentConfig(**kwargs)


# ── pacing ────────────────────────────────────────────────────────────────

_pace_lock = threading.Lock()
_last_call_started = 0.0


def _pace(min_interval: float) -> None:
    """Block until at least ``min_interval`` seconds since the last call."""

    global _last_call_started

    if min_interval <= 0:
        return

    with _pace_lock:
        wait = _last_call_started + min_interval - time.monotonic()

        if wait > 0:
            time.sleep(wait)

        _last_call_started = time.monotonic()


def _backoff_seconds(
    attempt: int,
    error: AIServiceError,
    *,
    interactive: bool,
) -> float | None:
    """
    Seconds to wait before retrying, or ``None`` if the wait the server asked
    for is too long to be worth blocking on (we then move to the fallback).
    """

    cap = 8.0 if interactive else 45.0
    base = 1.0 if interactive else 3.0

    delay = min(cap, base * (2 ** attempt)) + random.uniform(0.0, 1.0)

    if error.retry_after:
        if error.retry_after > cap + 15:
            return None

        delay = max(delay, error.retry_after + 0.5)

    return delay


# ── response parsing ──────────────────────────────────────────────────────

def _parse_json(response: Any) -> dict:
    try:
        text = response.text
    except Exception:  # SDK raises when there are no usable candidates
        text = None

    if not text or not text.strip():
        raise AIResponseError(_INVALID_JSON_MESSAGE)

    cleaned = _FENCE_RE.sub("", text.strip()).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = _OBJECT_RE.search(cleaned)

        if not match:
            raise AIResponseError(_INVALID_JSON_MESSAGE) from None

        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise AIResponseError(_INVALID_JSON_MESSAGE) from None

    if not isinstance(data, dict):
        raise AIResponseError(_INVALID_JSON_MESSAGE)

    return data


# ── public API ────────────────────────────────────────────────────────────

def generate_json(
    prompt: str,
    *,
    label: str = "request",
    interactive: bool = False,
) -> dict:
    """
    Run ``prompt`` and return the parsed JSON object.

    ``interactive=True`` is for calls a user is waiting on (resume upload):
    no pacing and a short retry budget so the request doesn't hang.
    Background callers (the worker) get pacing and a longer retry budget.

    Raises ``AIServiceError`` (or a subclass) when every model/attempt fails.
    """

    client = get_client()
    models = _model_chain()

    min_interval = (
        0.0 if interactive else settings.GEMINI_MIN_INTERVAL_SECONDS
    )

    primary_attempts = 2 if interactive else settings.GEMINI_MAX_RETRIES + 1
    fallback_attempts = 1 if interactive else 2

    last_error: AIServiceError | None = None

    for index, model in enumerate(models):
        if index > 0:
            stats.fallbacks += 1
            logger.warning(
                "Gemini %s: switching to fallback model %s", label, model,
            )

        attempts = primary_attempts if index == 0 else fallback_attempts
        use_thinking = True
        attempt = 0

        while attempt < attempts:
            _pace(min_interval)
            stats.calls += 1

            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=_build_config(use_thinking),
                )

                return _parse_json(response)

            except Exception as exc:  # noqa: BLE001 - classified below
                error = classify_error(exc)

            stats.failures += 1
            last_error = error

            logger.warning(
                "Gemini %s failed (model=%s attempt=%d/%d type=%s): %s",
                label, model, attempt + 1, attempts,
                type(error).__name__, error,
            )

            # The model rejected our thinking config: retry once without it,
            # without spending one of the normal attempts.
            if error.drop_thinking and use_thinking:
                use_thinking = False
                continue

            if not error.retryable:
                break

            attempt += 1

            if attempt >= attempts:
                break

            wait = _backoff_seconds(
                attempt - 1, error, interactive=interactive,
            )

            if wait is None:
                break

            stats.retries += 1
            logger.info("Gemini %s: retrying in %.1fs", label, wait)
            time.sleep(wait)

        if last_error is not None and not last_error.try_fallback:
            break

    assert last_error is not None
    raise last_error
