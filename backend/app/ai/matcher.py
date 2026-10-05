"""
Deterministic resume-to-job matching. No AI calls happen here.

What changed versus the first version
-------------------------------------
* ``experience_match``, ``education_match`` and ``location_match`` used to be
  hard-coded to 70, so half the score was a constant. The practical effect was
  that scores lived in a narrow ~35-85 band and the dashboard's "90%+" filter
  could never match anything. They are now computed from the data.
* Skill matching is no longer an exact string intersection: "React.js" matches
  "React", "Postgres" matches "PostgreSQL", and a required skill that appears
  in the resume text (but not in its skills list) still counts.
* ``None`` inputs (the model sometimes returns null) no longer raise.
* A job with no extractable skills gets no score instead of a perfect one.
* Location has no preference data behind it, so it is reported as ``None`` and
  excluded from the weighted score instead of pretending to be 70.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable


# Components with value None are excluded and the rest are renormalised.
WEIGHTS = {
    "skills": 0.45,
    "experience": 0.20,
    "education": 0.10,
    "role": 0.25,
}


# ── normalisation ─────────────────────────────────────────────────────────

_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react js": "react",
    "node": "node",
    "nodejs": "node",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "golang": "go",
    "py": "python",
    "python3": "python",
    "python2": "python",
    "ml": "machine learning",
    "gcp": "google cloud",
    "amazon web services": "aws",
    "c sharp": "c#",
    "dotnet": ".net",
    "rest": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",
    "rest apis": "rest api",
}

# Words that add no identity to a skill name ("Python programming" == "Python").
_GENERIC = {
    "programming", "development", "framework", "language", "languages",
    "library", "libraries", "tools", "tool", "experience", "skills", "skill",
    "knowledge", "proficiency", "basics", "fundamentals", "engineering",
    "technologies", "technology", "software", "platform", "and", "of", "the",
}

_SPLIT_RE = re.compile(r"[\s/,;()&|]+")
_VERSION_TAIL_RE = re.compile(r"\s+v?\d+(?:\.\d+)*$")
_JS_SUFFIX_RE = re.compile(r"(?<=[a-z0-9])\.?js$")


def _canon(skill: Any) -> str:
    text = str(skill or "").strip().lower()

    if not text:
        return ""

    text = _VERSION_TAIL_RE.sub("", text)

    if text in _ALIASES:
        return _ALIASES[text]

    # "node.js" / "nodejs" / "vue.js" -> "node" / "vue"
    if text not in {"js", "javascript"}:
        stripped = _JS_SUFFIX_RE.sub("", text)

        if stripped and stripped != text:
            text = stripped

    return _ALIASES.get(text, text)


def _tokens(skill: Any) -> frozenset[str]:
    canon = _canon(skill)
    parts = [part for part in _SPLIT_RE.split(canon) if part]
    meaningful = [part for part in parts if part not in _GENERIC]

    return frozenset(meaningful or parts)


def _same_skill(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False

    if a == b:
        return True

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)

    # "machine learning" is contained in "machine learning engineering",
    # but a lone "react" must not match "react native".
    return len(shorter) >= 2 and shorter <= longer


@lru_cache(maxsize=2048)
def _word_pattern(canon: str) -> re.Pattern[str]:
    return re.compile(
        r"(?<![a-z0-9+#.])" + re.escape(canon) + r"(?![a-z0-9+#])"
    )


def _as_list(value: Any) -> list:
    return value if isinstance(value, (list, tuple)) else []


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())

    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_text(v) for v in value)

    return str(value)


# ── experience ────────────────────────────────────────────────────────────

_YEARS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:\+|plus)?\s*(?:-|–|to)?\s*"
    r"(?:\d+(?:\.\d+)?)?\s*\+?\s*(?:years?|yrs?)",
    re.IGNORECASE,
)
_ENTRY_RE = re.compile(
    r"entry[\s-]*level|new\s*grad|fresh\s*grad|graduate|intern", re.IGNORECASE,
)


def required_years(text: str | None) -> float | None:
    """Minimum years of experience a posting asks for, if it says."""

    if not text:
        return None

    match = _YEARS_RE.search(text)

    if match:
        return float(match.group(1))

    if _ENTRY_RE.search(text):
        return 0.0

    return None


def _experience_score(years: float | None, requirement: str | None) -> float:
    required = required_years(requirement)

    if required is None:
        return 80.0           # nothing asked for

    if required == 0:
        return 100.0          # entry level: anyone qualifies

    if years is None:
        return 60.0           # asked for something we cannot verify

    if years >= required:
        return 100.0

    return round(max(20.0, 100.0 * years / required), 1)


# ── education ─────────────────────────────────────────────────────────────

_LEVELS: list[tuple[int, re.Pattern[str]]] = [
    (4, re.compile(r"\b(?:ph\.?\s?d|doctorate|doctoral)\b", re.I)),
    (3, re.compile(r"\b(?:master'?s?|m\.?sc?|mba|m\.?tech|m\.?eng)\b", re.I)),
    (2, re.compile(r"\b(?:bachelor'?s?|b\.?sc?|b\.?a|b\.?tech|b\.?eng|b\.e|undergraduate)\b", re.I)),
    (1, re.compile(r"\b(?:associate'?s?|diploma)\b", re.I)),
]


def _education_level(text: str) -> int | None:
    for level, pattern in _LEVELS:       # highest first
        if pattern.search(text):
            return level

    return None


def _education_score(
    candidate_level: int | None,
    requirement: str | None,
) -> float:
    required = _education_level(requirement or "")

    if required is None:
        return 90.0           # nothing asked for

    if candidate_level is None:
        return 60.0

    if candidate_level >= required:
        return 100.0

    return 55.0               # "or equivalent experience" is common


# ── roles ─────────────────────────────────────────────────────────────────

_ROLE_SYNONYMS = {
    "developer": "engineer",
    "dev": "engineer",
    "programmer": "engineer",
    "swe": "software engineer",
    "sde": "software engineer",
}
_ROLE_STOP = {"the", "a", "an", "of", "and", "for", "in", "at", "to", "-", "&"}
_ROLE_SPLIT = re.compile(r"[^a-z0-9+#.]+")


def _role_tokens(text: str) -> frozenset[str]:
    out: set[str] = set()

    for word in _ROLE_SPLIT.split(text.lower()):
        word = _ROLE_SYNONYMS.get(word, word)

        for part in word.split():
            if part and part not in _ROLE_STOP:
                out.add(part)

    return frozenset(out)


# ── candidate ─────────────────────────────────────────────────────────────

@dataclass
class Candidate:
    skills: list[frozenset[str]] = field(default_factory=list)
    text: str = ""
    years: float | None = None
    education_level: int | None = None
    roles: list[tuple[str, frozenset[str]]] = field(default_factory=list)


_PROFILE_SKILL_KEYS = (
    "skills", "programming_languages", "frameworks",
    "libraries", "tools", "databases",
)


def build_candidate(
    profile: dict | None,
    target_roles: Iterable[str] = (),
    resume_text: str | None = None,
) -> Candidate:
    """Pre-compute everything that does not depend on the job."""

    profile = profile or {}

    raw_skills: list = []

    for key in _PROFILE_SKILL_KEYS:
        raw_skills.extend(_as_list(profile.get(key)))

    years = profile.get("total_years_experience")

    try:
        years = float(years) if years is not None else None
    except (TypeError, ValueError):
        years = None

    return Candidate(
        skills=[t for t in (_tokens(s) for s in raw_skills) if t],
        text=(resume_text or "").lower(),
        years=years,
        education_level=_education_level(
            _flatten_text(profile.get("education"))
        ),
        roles=[
            (role.strip().lower(), _role_tokens(role))
            for role in target_roles
            if role and role.strip()
        ],
    )


# ── scoring ───────────────────────────────────────────────────────────────

def _has_skill(candidate: Candidate, skill: str) -> bool:
    wanted = _tokens(skill)

    if not wanted:
        return False

    if any(_same_skill(wanted, have) for have in candidate.skills):
        return True

    canon = _canon(skill)

    # Fall back to the resume text. Very short names ("c", "r", "go") are far
    # too ambiguous to search for in prose.
    if candidate.text and len(canon) > 2:
        return bool(_word_pattern(canon).search(candidate.text))

    return False


def _role_score(candidate: Candidate, title: str) -> float | None:
    if not candidate.roles:
        return None

    title_lower = title.lower()
    title_tokens = _role_tokens(title)
    best = 0.0

    for role_text, role_tokens in candidate.roles:
        if role_text and role_text in title_lower:
            return 100.0

        if role_tokens:
            overlap = len(role_tokens & title_tokens) / len(role_tokens)
            best = max(best, overlap * 100.0)

    return round(best, 1)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    for value in values:
        key = _canon(value)

        if key and key not in seen:
            seen.add(key)
            out.append(value)

    return out


def score_job(
    candidate: Candidate,
    job_analysis: dict,
    job_title: str,
) -> dict:
    required = _unique([str(s) for s in _as_list(job_analysis.get("required_skills")) if s])
    preferred = _unique([str(s) for s in _as_list(job_analysis.get("preferred_skills")) if s])

    matched_required = [s for s in required if _has_skill(candidate, s)]
    matched_preferred = [s for s in preferred if _has_skill(candidate, s)]

    skill_score: float | None

    if not required and not preferred:
        skill_score = None
    elif required and preferred:
        skill_score = (
            80.0 * len(matched_required) / len(required)
            + 20.0 * len(matched_preferred) / len(preferred)
        )
    elif required:
        skill_score = 100.0 * len(matched_required) / len(required)
    else:
        skill_score = 100.0 * len(matched_preferred) / len(preferred)

    components: dict[str, float | None] = {
        "skills": skill_score,
        "experience": _experience_score(
            candidate.years,
            job_analysis.get("experience_requirements"),
        ),
        "education": _education_score(
            candidate.education_level,
            job_analysis.get("education_requirements"),
        ),
        "role": _role_score(candidate, job_title),
    }

    def rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 2)

    result = {
        "match_score": None,
        "skill_match": rounded(components["skills"]),
        "experience_match": rounded(components["experience"]),
        "education_match": rounded(components["education"]),
        "role_match": rounded(components["role"]),
        "location_match": None,
        "matched_skills": matched_required + matched_preferred,
        "missing_skills": [s for s in required if s not in matched_required],
    }

    # No skill information at all -> we genuinely cannot score this job.
    if skill_score is None:
        return result

    used = {k: v for k, v in components.items() if v is not None}
    total_weight = sum(WEIGHTS[k] for k in used)

    result["match_score"] = round(
        sum(WEIGHTS[k] * v for k, v in used.items()) / total_weight,
        2,
    )

    return result


def calculate_match(
    profile: dict,
    job_analysis: dict,
    job_title: str,
    job_location: str | None = None,  # kept for API compatibility
    target_roles: Iterable[str] = (),
    resume_text: str | None = None,
) -> dict:
    """Convenience wrapper for scoring a single job."""

    return score_job(
        build_candidate(profile, target_roles, resume_text),
        job_analysis,
        job_title,
    )
