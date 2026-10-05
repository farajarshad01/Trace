"""
Test bootstrap.

The real google-genai SDK is only needed when talking to Google, so the unit
tests inject a tiny stand-in (shaped like the real one: ``errors.APIError``
carries ``code`` / ``status`` / ``details``). That keeps the suite runnable
anywhere, with no network and no API key.
"""

import os
import sys
import types as pytypes

# FORCE (not setdefault): the worker tests call drop_all()/create_all(), so a
# real DATABASE_URL leaking in from the shell or a .env file must never be used.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GOOGLE_API_KEY"] = "test-key"

BACKEND = os.path.dirname(os.path.dirname(__file__))

if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _install_fake_genai():
    try:
        import google.genai  # noqa: F401
        import pydantic_core  # noqa: F401  (real SDK needs a working core)
        return
    except Exception:
        pass

    for name in ("google", "google.genai", "google.genai.errors", "google.genai.types"):
        sys.modules.pop(name, None)

    google = pytypes.ModuleType("google")
    genai = pytypes.ModuleType("google.genai")
    errors = pytypes.ModuleType("google.genai.errors")
    types = pytypes.ModuleType("google.genai.types")

    class APIError(Exception):
        def __init__(self, code, response_json=None):
            self.code = code
            self.details = response_json or {}
            err = self.details.get("error", {}) if isinstance(self.details, dict) else {}
            self.message = err.get("message")
            self.status = err.get("status")
            super().__init__(f"{code} {self.status}. {self.details}")

    class ClientError(APIError):
        pass

    class ServerError(APIError):
        pass

    errors.APIError, errors.ClientError, errors.ServerError = APIError, ClientError, ServerError

    class HttpOptions:
        def __init__(self, timeout=None):
            self.timeout = timeout

    class ThinkingLevel(str):
        def __new__(cls, value):
            if str(value).upper() not in {"MINIMAL", "LOW", "MEDIUM", "HIGH"}:
                raise ValueError(value)
            return str.__new__(cls, str(value).upper())

    class ThinkingConfig:
        def __init__(self, thinking_level=None):
            self.thinking_level = thinking_level

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    types.HttpOptions = HttpOptions
    types.ThinkingLevel = ThinkingLevel
    types.ThinkingConfig = ThinkingConfig
    types.GenerateContentConfig = GenerateContentConfig

    class Client:  # replaced per-test via monkeypatch
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    genai.Client = Client
    genai.errors = errors
    genai.types = types
    google.genai = genai

    sys.modules.update({
        "google": google,
        "google.genai": genai,
        "google.genai.errors": errors,
        "google.genai.types": types,
    })


_install_fake_genai()
