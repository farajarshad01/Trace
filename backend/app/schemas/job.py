from datetime import datetime

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: int
    company_name: str
    title: str
    location: str | None = None
    employment_type: str | None = None
    # Only populated by GET /api/jobs/{id}. The list endpoint leaves it out:
    # full postings are several KB each and the cards never show them.
    description: str | None = None
    original_url: str
    platform: str | None = None
    status: str
    first_seen_at: datetime
    last_seen_at: datetime

    match_score: float | None = None
    skill_match: float | None = None
    experience_match: float | None = None
    education_match: float | None = None
    role_match: float | None = None
    location_match: float | None = None

    required_skills: list | None = None
    preferred_skills: list | None = None
    matched_skills: list[str] | None = None
    missing_skills: list[str] | None = None
    experience_requirements: str | None = None
    education_requirements: str | None = None
    role_summary: str | None = None

    analyzed: bool = False
