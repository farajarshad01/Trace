import os

from dotenv import load_dotenv


load_dotenv()


def _get_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name, "").strip()

    if not raw:
        return default

    try:
        return max(int(raw), minimum)
    except ValueError:
        return default


def _get_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name, "").strip()

    if not raw:
        return default

    try:
        return max(float(raw), minimum)
    except ValueError:
        return default


_OFF = {"none", "off", "disabled", "false", "0"}


def _get_str(name: str, default: str, allow_off: bool = False) -> str:
    """
    Treat an empty value as "unset". GitHub Actions passes undefined
    variables (``${{ vars.X }}``) as empty strings, which would otherwise
    override the default with "".
    """

    value = (os.getenv(name) or "").strip()

    if not value:
        return default

    if allow_off and value.lower() in _OFF:
        return ""

    return value


def _get_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)

    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    APP_ENV: str = _get_str("APP_ENV", "development")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")

    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY",
        "",
    )

    # ── Gemini ────────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = (
        os.getenv("GOOGLE_API_KEY", "")
        or os.getenv("GEMINI_API_KEY", "")
    )

    # Primary model. Rate limits are enforced per model, so a *different*
    # fallback model gives us a second quota bucket when the primary is
    # overloaded (503) or rate-limited (429). Set to "" to disable.
    GEMINI_MODEL: str = _get_str("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_FALLBACK_MODEL: str = _get_str(
        "GEMINI_FALLBACK_MODEL",
        "gemini-3.5-flash",
        allow_off=True,        # GEMINI_FALLBACK_MODEL=none disables it
    )

    # Extraction does not need deep reasoning. The default level for
    # Gemini 3.8 Flash is "medium"; thinking tokens count against your
    # tokens-per-minute quota, so "low" is both faster and cheaper.
    GEMINI_THINKING_LEVEL: str = _get_str(
        "GEMINI_THINKING_LEVEL",
        "low",
        allow_off=True,        # GEMINI_THINKING_LEVEL=none sends no config
    )

    GEMINI_TIMEOUT_SECONDS: float = _get_float(
        "GEMINI_TIMEOUT_SECONDS", 60.0, minimum=5.0,
    )

    # Minimum gap between *background* Gemini calls (the worker). 6s keeps
    # the worker at <= 10 requests/minute, which fits free-tier limits.
    # Paid tiers can lower this (e.g. 0.5).
    GEMINI_MIN_INTERVAL_SECONDS: float = _get_float(
        "GEMINI_MIN_INTERVAL_SECONDS", 6.0,
    )

    GEMINI_MAX_RETRIES: int = _get_int("GEMINI_MAX_RETRIES", 3)

    # Hard ceiling on Gemini calls per worker run. Anything left over is
    # picked up by the next run, so the backlog drains gradually instead
    # of being re-attempted all at once every hour.
    MAX_ANALYSES_PER_RUN: int = _get_int("MAX_ANALYSES_PER_RUN", 20)

    # Scrapers whose listing page lacks the job text (Workday, generic) need
    # one extra request per *new* job. Cap it so one big board cannot make
    # a single run enormous.
    MAX_DETAIL_FETCHES_PER_SOURCE: int = _get_int(
        "MAX_DETAIL_FETCHES_PER_SOURCE", 40,
    )

    # Input size guards (characters, not tokens).
    JOB_DESCRIPTION_MAX_CHARS: int = _get_int(
        "JOB_DESCRIPTION_MAX_CHARS", 12000, minimum=1000,
    )
    RESUME_TEXT_MAX_CHARS: int = _get_int(
        "RESUME_TEXT_MAX_CHARS", 30000, minimum=2000,
    )
    MAX_RESUME_BYTES: int = _get_int(
        "MAX_RESUME_BYTES", 5 * 1024 * 1024, minimum=1024,
    )

    # ── HTTP ──────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = _get_list(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )


settings = Settings()
