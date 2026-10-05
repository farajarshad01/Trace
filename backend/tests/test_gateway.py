"""
The Gemini gateway, exercised against a scripted fake client.

Every behaviour here is something the old ``analyze_*`` functions did NOT do:
retry, back off, honour retryDelay, fall back, or stop on a dead quota.
"""

import pytest

from google.genai import errors as genai_errors

from app.ai import gemini
from app.ai.errors import (
    AIConfigError,
    AIOverloadedError,
    AIQuotaError,
    AIRateLimitError,
    AIResponseError,
    classify_error,
)
from app.core.config import settings


class FakeResponse:
    def __init__(self, text):
        self.text = text


def api_error(code, message="boom", status="X", details=None):
    body = {"error": {"code": code, "message": message, "status": status}}
    if details:
        body["error"]["details"] = details
    return genai_errors.APIError(code, body)


def retry_info(seconds):
    return {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": f"{seconds}s"}


def daily_quota():
    return {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
    }


class FakeClient:
    """Plays back a script: each item is an exception to raise or text to return."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []           # (model, has_thinking)
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append((model, getattr(config, "thinking_config", None) is not None))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


OK = '{"required_skills": ["Python"]}'


def setup(monkeypatch, script, fallback="fallback-model"):
    client = FakeClient(script)
    sleeps = []
    monkeypatch.setattr(gemini, "get_client", lambda: client)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(gemini.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(settings, "GEMINI_MODEL", "primary-model")
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODEL", fallback)
    monkeypatch.setattr(settings, "GEMINI_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(settings, "GEMINI_MAX_RETRIES", 3)
    monkeypatch.setattr(settings, "GEMINI_THINKING_LEVEL", "low")
    gemini.reset_stats()
    return client, sleeps


def test_success_and_markdown_fences_are_stripped(monkeypatch):
    client, sleeps = setup(monkeypatch, ["```json\n" + OK + "\n```"])
    assert gemini.generate_json("p") == {"required_skills": ["Python"]}
    assert client.calls == [("primary-model", True)]      # thinking config sent
    assert sleeps == []


def test_transient_503_is_retried_with_backoff(monkeypatch):
    client, sleeps = setup(monkeypatch, [api_error(503), api_error(503), OK])
    assert gemini.generate_json("p")["required_skills"] == ["Python"]
    assert [m for m, _ in client.calls] == ["primary-model"] * 3
    assert sleeps == [3.0, 6.0]                           # exponential
    assert gemini.stats.retries == 2


def test_429_honours_server_retry_delay(monkeypatch):
    _, sleeps = setup(monkeypatch, [api_error(429, details=[retry_info(20)]), OK])
    gemini.generate_json("p")
    assert sleeps == [20.5]


def test_persistent_overload_switches_to_fallback_model(monkeypatch):
    client, _ = setup(monkeypatch, [api_error(503)] * 4 + [OK])
    assert gemini.generate_json("p")
    models = [m for m, _ in client.calls]
    assert models[:4] == ["primary-model"] * 4 and models[4] == "fallback-model"
    assert gemini.stats.fallbacks == 1


def test_daily_quota_does_not_waste_retries_on_the_primary(monkeypatch):
    client, sleeps = setup(
        monkeypatch, [api_error(429, details=[daily_quota()]), OK],
    )
    assert gemini.generate_json("p")
    assert [m for m, _ in client.calls] == ["primary-model", "fallback-model"]
    assert sleeps == []


def test_daily_quota_everywhere_raises_quota_error(monkeypatch):
    setup(monkeypatch, [api_error(429, details=[daily_quota()])] * 2)
    with pytest.raises(AIQuotaError):
        gemini.generate_json("p")


def test_retry_delay_too_long_skips_straight_to_fallback(monkeypatch):
    client, sleeps = setup(
        monkeypatch, [api_error(429, details=[retry_info(300)]), OK],
    )
    assert gemini.generate_json("p")
    assert sleeps == []
    assert client.calls[1][0] == "fallback-model"


def test_bad_api_key_fails_fast_without_fallback(monkeypatch):
    client, sleeps = setup(monkeypatch, [api_error(403)])
    with pytest.raises(AIConfigError):
        gemini.generate_json("p")
    assert len(client.calls) == 1 and sleeps == []


def test_model_not_found_tries_fallback(monkeypatch):
    client, _ = setup(monkeypatch, [api_error(404), OK])
    assert gemini.generate_json("p")
    assert client.calls[1][0] == "fallback-model"


def test_thinking_config_rejected_is_retried_without_it(monkeypatch):
    client, sleeps = setup(
        monkeypatch,
        [api_error(400, message="Thinking level low is not supported"), OK],
    )
    assert gemini.generate_json("p")
    assert [t for _, t in client.calls] == [True, False]
    assert sleeps == []


def test_invalid_json_is_retried_once_more(monkeypatch):
    client, _ = setup(monkeypatch, ["not json at all", OK])
    assert gemini.generate_json("p")
    assert len(client.calls) == 2


def test_persistently_invalid_json_raises_response_error(monkeypatch):
    setup(monkeypatch, ["nope"] * 4)
    with pytest.raises(AIResponseError):
        gemini.generate_json("p")


def test_json_wrapped_in_prose_is_recovered(monkeypatch):
    setup(monkeypatch, ['Sure! Here you go: {"a": 1} Hope that helps'])
    assert gemini.generate_json("p") == {"a": 1}


def test_interactive_calls_have_a_short_retry_budget(monkeypatch):
    client, sleeps = setup(monkeypatch, [api_error(503)] * 5)
    with pytest.raises(AIOverloadedError):
        gemini.generate_json("p", interactive=True)
    # 2 attempts on primary + 1 on fallback - a user must not wait forever
    assert len(client.calls) == 3
    assert max(sleeps) <= 8.0


def test_pacing_spaces_out_background_calls(monkeypatch):
    client, _ = setup(monkeypatch, [OK, OK])
    waits = []
    monkeypatch.setattr(settings, "GEMINI_MIN_INTERVAL_SECONDS", 6.0)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: waits.append(round(s)))
    monkeypatch.setattr(gemini, "_last_call_started", gemini.time.monotonic())
    gemini.generate_json("p")
    assert waits and waits[0] in (5, 6)


# ── classification ──────────────────────────────────────────────────────

def test_classification_uses_the_status_code_not_substrings():
    # Old code did `"400" in str(exc)` - any 400 inside a 503 body misrouted it.
    err = classify_error(api_error(503, message="model overloaded, request id 4003400"))
    assert isinstance(err, AIOverloadedError)


def test_429_without_daily_marker_is_a_plain_rate_limit():
    err = classify_error(api_error(429, details=[retry_info(7)]))
    assert isinstance(err, AIRateLimitError) and err.retry_after == 7.0


def test_network_timeouts_are_treated_as_transient():
    class ReadTimeout(Exception):
        pass
    assert isinstance(classify_error(ReadTimeout()), AIOverloadedError)
    assert isinstance(classify_error(TimeoutError()), AIOverloadedError)
