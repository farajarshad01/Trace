import pytest

from app.ai.matcher import (
    _canon,
    _tokens,
    build_candidate,
    calculate_match,
    required_years,
    score_job,
)


PROFILE = {
    "skills": ["Python", "REST APIs", "Docker"],
    "programming_languages": ["JavaScript", "SQL"],
    "frameworks": ["React.js", "FastAPI"],
    "databases": ["Postgres"],
    "tools": ["Git"],
    "total_years_experience": 3,
    "education": [{"degree": "Bachelor of Science in Computer Science", "institution": "X"}],
}


# ── normalisation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("React.js", "React"),
    ("ReactJS", "react"),
    ("Node.js", "NodeJS"),
    ("Postgres", "PostgreSQL"),
    ("Python 3.11", "python"),
    ("python3", "Python"),
    ("Python programming", "Python"),
    ("K8s", "Kubernetes"),
    ("Golang", "Go"),
    ("REST APIs", "RESTful API"),
    ("JS", "JavaScript"),
])
def test_equivalent_skills_canonicalise_the_same(a, b):
    assert _tokens(a) == _tokens(b), (_canon(a), _canon(b))


@pytest.mark.parametrize("a,b", [
    ("React", "React Native"),
    ("Java", "JavaScript"),
    ("SQL", "SQL Server"),
    ("C", "C++"),
])
def test_distinct_skills_do_not_collide(a, b):
    c = build_candidate({"skills": [a]})
    assert not any(
        t == _tokens(b) or (len(t) >= 2 and t <= _tokens(b)) for t in c.skills
    )


# ── skills ───────────────────────────────────────────────────────────────

def test_fuzzy_skill_match_scores_full_marks():
    r = calculate_match(
        PROFILE,
        {"required_skills": ["React", "PostgreSQL", "Python 3"], "preferred_skills": []},
        "Software Engineer",
    )
    assert r["skill_match"] == 100.0
    assert r["missing_skills"] == []
    assert set(r["matched_skills"]) == {"React", "PostgreSQL", "Python 3"}


def test_missing_required_skills_are_reported():
    r = calculate_match(
        PROFILE,
        {"required_skills": ["Python", "Kubernetes", "Go"], "preferred_skills": []},
        "Software Engineer",
    )
    assert r["skill_match"] == pytest.approx(33.33, abs=0.01)
    assert r["missing_skills"] == ["Kubernetes", "Go"]


def test_required_skill_found_in_resume_text_counts():
    r = calculate_match(
        {"skills": ["Python"]},
        {"required_skills": ["Redis"], "preferred_skills": []},
        "Engineer",
        resume_text="Built a caching layer with Redis and Celery.",
    )
    assert r["skill_match"] == 100.0


def test_short_skill_names_are_not_searched_in_prose():
    # "go" appears as an English word; it must not count as the Go language.
    r = calculate_match(
        {"skills": ["Python"]},
        {"required_skills": ["Go"], "preferred_skills": []},
        "Engineer",
        resume_text="Ready to go the extra mile.",
    )
    assert r["skill_match"] == 0.0


def test_required_and_preferred_are_weighted_80_20():
    r = calculate_match(
        {"skills": ["Python"]},
        {"required_skills": ["Python"], "preferred_skills": ["Rust"]},
        "Engineer",
    )
    assert r["skill_match"] == 80.0


def test_no_skills_extracted_means_no_score_not_a_perfect_score():
    r = calculate_match(PROFILE, {"required_skills": [], "preferred_skills": []}, "Engineer")
    assert r["match_score"] is None
    assert r["skill_match"] is None


def test_null_fields_from_the_model_do_not_crash():
    r = calculate_match(
        {"skills": None, "frameworks": None, "education": None, "total_years_experience": None},
        {"required_skills": None, "preferred_skills": None,
         "experience_requirements": None, "education_requirements": None},
        "Engineer",
    )
    assert r["match_score"] is None


# ── experience ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("3+ years of backend development", 3),
    ("3-5 years experience", 3),
    ("At least 2 yrs in sales", 2),
    ("Entry level position", 0),
    ("Open to new graduates", 0),
    ("Strong communication", None),
    ("", None),
    (None, None),
])
def test_required_years_parsing(text, expected):
    assert required_years(text) == expected


def test_experience_score_scales_with_gap():
    job = {"required_skills": ["Python"], "experience_requirements": "6+ years"}
    r = calculate_match({"skills": ["Python"], "total_years_experience": 3}, job, "Eng")
    assert r["experience_match"] == 50.0

    r = calculate_match({"skills": ["Python"], "total_years_experience": 8}, job, "Eng")
    assert r["experience_match"] == 100.0

    r = calculate_match({"skills": ["Python"]}, job, "Eng")
    assert r["experience_match"] == 60.0     # unknown candidate years


def test_entry_level_roles_never_penalise_unknown_years():
    r = calculate_match(
        {"skills": ["Python"]},
        {"required_skills": ["Python"], "experience_requirements": "Entry level"},
        "Eng",
    )
    assert r["experience_match"] == 100.0


# ── education ────────────────────────────────────────────────────────────

def test_education_levels():
    job = lambda req: {"required_skills": ["x"], "education_requirements": req}
    bach = {"skills": ["x"], "education": [{"degree": "B.Tech in CS"}]}
    none = {"skills": ["x"], "education": []}

    assert calculate_match(bach, job("Bachelor's degree"), "t")["education_match"] == 100.0
    assert calculate_match(bach, job("Master's degree"), "t")["education_match"] == 55.0
    assert calculate_match(bach, job(""), "t")["education_match"] == 90.0
    assert calculate_match(none, job("Bachelor's degree"), "t")["education_match"] == 60.0


def test_the_word_be_does_not_count_as_a_bachelors_degree():
    r = calculate_match(
        {"skills": ["x"], "education": []},
        {"required_skills": ["x"], "education_requirements": "Must be able to relocate"},
        "t",
    )
    assert r["education_match"] == 90.0     # i.e. "no requirement found"


# ── roles ────────────────────────────────────────────────────────────────

def test_role_matching():
    job = {"required_skills": ["Python"]}
    p = {"skills": ["Python"]}

    exact = calculate_match(p, job, "Senior Backend Developer", target_roles=["Backend Developer"])
    assert exact["role_match"] == 100.0

    synonym = calculate_match(p, job, "Backend Engineer", target_roles=["Backend Developer"])
    assert synonym["role_match"] == 100.0       # developer ~ engineer

    partial = calculate_match(p, job, "Software Engineer, Backend", target_roles=["Backend Developer"])
    assert partial["role_match"] == 100.0

    unrelated = calculate_match(p, job, "Marketing Manager", target_roles=["Backend Developer"])
    assert unrelated["role_match"] == 0.0


def test_no_target_roles_means_role_is_excluded_not_zero():
    job = {"required_skills": ["Python"]}
    with_roles = calculate_match({"skills": ["Python"]}, job, "Marketing", target_roles=["Backend Developer"])
    without = calculate_match({"skills": ["Python"]}, job, "Marketing")

    assert without["role_match"] is None
    assert without["match_score"] > with_roles["match_score"]


# ── overall ──────────────────────────────────────────────────────────────

def test_score_range_is_no_longer_capped_below_90():
    """Regression: with three components hard-coded to 70 the max was ~85."""
    r = calculate_match(
        PROFILE,
        {"required_skills": ["Python", "React"], "preferred_skills": ["Docker"],
         "experience_requirements": "2+ years", "education_requirements": "Bachelor's"},
        "Backend Developer",
        target_roles=["Backend Developer"],
    )
    assert r["match_score"] >= 95


def test_zero_overlap_scores_low():
    r = calculate_match(
        PROFILE,
        {"required_skills": ["COBOL", "Mainframe"], "preferred_skills": [],
         "experience_requirements": "10+ years", "education_requirements": "PhD"},
        "Mainframe Operator",
        target_roles=["Backend Developer"],
    )
    assert r["match_score"] < 35


def test_bulk_scoring_reuses_candidate():
    cand = build_candidate(PROFILE, ["Backend Developer"], "built things in python")
    a = score_job(cand, {"required_skills": ["Python"]}, "Backend Developer")
    b = score_job(cand, {"required_skills": ["Rust"]}, "Backend Developer")
    assert a["match_score"] > b["match_score"]
