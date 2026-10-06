"""
Does a job title match one of the roles the user is looking for?

Deterministic and transparent on purpose: no AI call, so it costs no quota and
behaves the same every time. The idea is to compare *what kind of job* it is,
not just shared words. "Engineer" is in half of all titles, so sharing it says
nothing; "Backend" or "Salesforce" does.

A title matches a role when BOTH hold:

1. every *specific* word of the role appears in the title (for roles with
   three or more specific words, 60% of them), where seniority and filler
   words are ignored and common spellings are unified
   (Front-end = Frontend, ML = AI = Machine Learning, Node.js = Node ...);
2. it is the same *kind* of job: Developer / Engineer / Programmer are
   interchangeable, but a Data Engineer is not a Data Analyst, a Consultant
   or a Manager.

The word "Software" in a role is soft: "Software Engineer" accepts any
engineering title with a software-flavoured word in it (Backend, Frontend,
Mobile, Python, DevOps ...), because those are software engineers too - but
not Salesforce, QA or Pre-Sales.

Examples, for the role "Backend Developer":
    Senior Backend Engineer        match
    Backend Python Developer       match
    Back-end Developer (Node.js)   match
    Senior Salesforce Developer    no   (no "backend")
    Pre-Sales Engineer             no
    Software Engineer - iOS        no
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable


# Spelling variants -> one canonical token. Order matters (first match wins
# for overlapping text, and everything is lower-cased beforehand).
_PHRASES: list[tuple[str, str]] = [
    (r"full[\s-]*stack", " fullstack "),
    (r"front[\s-]*end", " frontend "),
    (r"back[\s-]*end", " backend "),
    (r"dev[\s-]*ops|site reliability|\bsre\b", " devops "),
    (r"machine[\s-]*learning|deep[\s-]*learning|artificial[\s-]*intelligence|"
     r"generative[\s-]*ai|gen[\s-]*ai|\bgenai\b|\bllms?\b|\bnlp\b|"
     r"computer[\s-]*vision|\bmlops\b|\bml\b|\bai\b", " aiml "),
    (r"quality[\s-]*assurance|\bsdet\b|\bqa\b", " qa "),
    (r"\bswe\b|\bsde\b", " software engineer "),
    (r"c\+\+", " cpp "),
    (r"c#", " csharp "),
    (r"\.net\b|\bdotnet\b", " dotnet "),
    (r"node\.?js", " node "),
    (r"react\.?js|react\.?native", " react "),
    (r"next\.?js", " next "),
    (r"vue\.?js", " vue "),
    (r"\bgolang\b", " go "),
    (r"\bjs\b", " javascript "),
    (r"\bts\b", " typescript "),
]

_WORD_MAP = {
    "dev": "developer",
    "programmer": "developer",
    "coder": "developer",
    "internship": "intern",
    "interns": "intern",
    "trainee": "intern",
}

# The "head noun" - what kind of job it is.
_FAMILY = {
    "engineer": "eng",
    "developer": "eng",
    "scientist": "sci",
    "researcher": "sci",
    "analyst": "analyst",
    "consultant": "consult",
    "architect": "arch",
    "manager": "mgr",
    "designer": "design",
    "administrator": "admin",
    "admin": "admin",
    "specialist": "spec",
    "technician": "tech",
    "tester": "qa",
}

# Words that never identify a role.
_IGNORE = {
    # seniority
    "senior", "sr", "junior", "jr", "lead", "staff", "principal", "associate",
    "mid", "entry", "level", "head", "chief", "i", "ii", "iii", "iv",
    # filler
    "the", "a", "an", "of", "and", "for", "in", "at", "to", "with", "on",
    "engineering", "remote", "hybrid", "onsite", "site", "team", "role",
}

# For the "Software Engineer" role: engineering titles that are clearly
# software work even without the word "software".
_SOFTWAREISH = {
    "software", "backend", "frontend", "fullstack", "web", "mobile", "ios",
    "android", "devops", "cloud", "platform", "api", "aiml", "data",
    "python", "java", "javascript", "typescript", "node", "react", "angular",
    "vue", "go", "rust", "ruby", "rails", "php", "cpp", "csharp", "dotnet",
    "kotlin", "swift", "flutter", "django", "flask", "fastapi", "spring",
    "embedded", "systems", "infrastructure", "security", "game",
}

_TOKEN = re.compile(r"[a-z0-9+#]+")


@lru_cache(maxsize=8192)
def parse(text: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return (specific words, job-kind families) for a title or role."""

    lowered = (text or "").lower().replace("&", " and ")

    for pattern, replacement in _PHRASES:
        lowered = re.sub(pattern, replacement, lowered)

    specific: set[str] = set()
    families: set[str] = set()

    for word in _TOKEN.findall(lowered):
        if word.endswith("s") and word[:-1] in _FAMILY:
            word = word[:-1]                       # engineers -> engineer

        for part in _WORD_MAP.get(word, word).split():
            if part in _FAMILY:
                families.add(_FAMILY[part])
            elif part not in _IGNORE:
                specific.add(part)

    return frozenset(specific), frozenset(families)


def _matches(title: tuple, role: tuple) -> bool:
    t_spec, t_fam = title
    r_spec, r_fam = role

    if not r_spec and not r_fam:
        return False

    main = set(r_spec)

    # "Software" is a soft word: it is satisfied by any clearly-software title
    # (Backend, Mobile, Python ...), not only by the literal word.
    if "software" in main:
        if not (t_spec & _SOFTWAREISH):
            return False

        main.discard("software")

    if main:
        needed = 1.0 if len(main) <= 2 else 0.6

        if len(main & t_spec) / len(main) < needed:
            return False

    # Same kind of job. A role with only a head noun ("Developer") needs the
    # title to have that kind of noun.
    if r_fam:
        if t_fam and not (r_fam & t_fam):
            return False

        if not t_fam and not r_spec:
            return False

    return True


def title_matches_roles(title: str, roles: Iterable[str]) -> bool:
    """True if ``title`` matches at least one role. No roles -> no filtering."""

    role_list = [r for r in roles if r and r.strip()]

    if not role_list:
        return True

    parsed_title = parse(title or "")

    return any(_matches(parsed_title, parse(role)) for role in role_list)


def filter_jobs(jobs: list[dict], roles: Iterable[str]) -> list[dict]:
    """Keep scraped jobs whose title matches the roles (all, if no roles)."""

    role_list = [r for r in roles if r and r.strip()]

    if not role_list:
        return jobs

    return [j for j in jobs if title_matches_roles(j.get("title", ""), role_list)]
