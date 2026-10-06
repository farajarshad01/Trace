from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.ai.matcher import Candidate, build_candidate, score_job
from app.database.models import (
    CareerSource,
    Job,
    JobAnalysis,
    JobStatus,
    Resume,
    TargetRole,
)
from app.scrapers.base import clean_url


# ── platforms / urls ──────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    url_lower = url.lower()

    if "greenhouse.io" in url_lower:
        return "greenhouse"

    if "lever.co" in url_lower:
        return "lever"

    if "myworkdayjobs.com" in url_lower:
        return "workday"

    return "generic"


def normalize_source_url(url: str) -> str:
    """Stable form for comparing career-page URLs (case, fragment, slash)."""

    parts = urlsplit((url or "").strip())

    path = parts.path.rstrip("/")

    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


# ── jobs ──────────────────────────────────────────────────────────────────

def find_job(
    db: Session,
    company_name: str,
    original_url: str,
) -> Job | None:
    return (
        db.query(Job)
        .filter(
            Job.company_name == company_name,
            Job.original_url == original_url,
        )
        .first()
    )


def save_scraped_job(
    db: Session,
    source: CareerSource,
    scraped_job: dict,
) -> Job:
    original_url = clean_url(scraped_job.get("original_url"))
    title = (scraped_job.get("title") or "").strip()

    if not original_url or not title:
        raise ValueError("Scraped job has no title or URL.")

    existing = find_job(db, source.company_name, original_url)
    now = datetime.now(timezone.utc)

    description = scraped_job.get("description")

    if existing:
        existing.title = title
        existing.location = scraped_job.get("location") or existing.location
        existing.employment_type = (
            scraped_job.get("employment_type") or existing.employment_type
        )

        # Never overwrite real text with an empty value (the generic and
        # Workday listing pages carry no description).
        if description:
            existing.description = description

        if existing.source_id is None:
            existing.source_id = source.id

        existing.last_seen_at = now
        existing.status = JobStatus.ACTIVE

        db.commit()
        db.refresh(existing)

        return existing

    job = Job(
        source_id=source.id,
        company_name=source.company_name,
        title=title,
        location=scraped_job.get("location"),
        employment_type=scraped_job.get("employment_type"),
        description=description,
        original_url=original_url,
        external_job_id=scraped_job.get("external_job_id"),
        platform=scraped_job.get("platform"),
        status=JobStatus.ACTIVE,
        first_seen_at=now,
        last_seen_at=now,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


def close_missing_jobs(
    db: Session,
    source: CareerSource,
    run_started_at: datetime,
) -> int:
    """
    Mark jobs this source did not list during the current run as closed.

    ``JobStatus.CLOSED`` existed but nothing ever set it, so postings stayed
    "active" on the dashboard forever after the company took them down.
    """

    stale = (
        db.query(Job)
        .filter(
            Job.source_id == source.id,
            Job.status == JobStatus.ACTIVE,
            Job.last_seen_at < run_started_at,
        )
        .all()
    )

    for job in stale:
        job.status = JobStatus.CLOSED

    db.commit()

    return len(stale)


# ── analysis ──────────────────────────────────────────────────────────────

def store_analysis(db: Session, job: Job, data: dict) -> JobAnalysis:
    """Create or update the JobAnalysis row for ``job``."""

    analysis = (
        db.query(JobAnalysis).filter(JobAnalysis.job_id == job.id).first()
    )

    if analysis is None:
        analysis = JobAnalysis(job_id=job.id)
        db.add(analysis)

    analysis.required_skills = data.get("required_skills") or []
    analysis.preferred_skills = data.get("preferred_skills") or []
    analysis.experience_requirements = data.get("experience_requirements")
    analysis.education_requirements = data.get("education_requirements")
    analysis.role_summary = data.get("role_summary")

    db.commit()
    db.refresh(analysis)

    return analysis


def analysis_to_dict(analysis: JobAnalysis | None) -> dict:
    if analysis is None:
        return {}

    return {
        "required_skills": analysis.required_skills or [],
        "preferred_skills": analysis.preferred_skills or [],
        "experience_requirements": analysis.experience_requirements,
        "education_requirements": analysis.education_requirements,
    }


# ── matching ──────────────────────────────────────────────────────────────

def build_match_context(db: Session, user_id) -> Candidate | None:
    """
    Load the user's resume and target roles ONCE.

    ``get_job_match`` used to run three queries per job, so the dashboard
    issued 200+ round-trips to a remote database for a page of 50 jobs.
    """

    resume = (
        db.query(Resume)
        .filter(Resume.user_id == user_id, Resume.is_active.is_(True))
        .order_by(Resume.created_at.desc())
        .first()
    )

    if not resume or not resume.structured_profile:
        return None

    roles = (
        db.query(TargetRole.role_title)
        .filter(TargetRole.user_id == user_id, TargetRole.is_active.is_(True))
        .all()
    )

    return build_candidate(
        resume.structured_profile,
        [role.role_title for role in roles],
        resume.extracted_text,
    )


def get_job_match(db: Session, job: Job, user_id) -> dict | None:
    """Score a single job. For lists, use ``build_match_context`` instead."""

    candidate = build_match_context(db, user_id)

    if candidate is None:
        return None

    analysis = (
        db.query(JobAnalysis).filter(JobAnalysis.job_id == job.id).first()
    )

    if analysis is None:
        return None

    return score_job(candidate, analysis_to_dict(analysis), job.title)


# ── visibility ────────────────────────────────────────────────────────────

def user_job_scope(db: Session, user_id):
    """
    SQL condition limiting jobs to the companies *this user* tracks, or
    ``None`` if they track nothing.

    The old jobs endpoint returned every active job in the table, so a
    brand-new user saw jobs scraped for everyone else's career pages. Jobs
    match by source id, or by company name (case-insensitive) so two users
    who track the same company share one set of job rows.
    """

    sources = (
        db.query(CareerSource.id, CareerSource.company_name)
        .filter(
            CareerSource.user_id == user_id,
            CareerSource.is_active.is_(True),
        )
        .all()
    )

    if not sources:
        return None

    ids = [s.id for s in sources]
    names = {s.company_name.strip().lower() for s in sources}

    return or_(
        Job.source_id.in_(ids),
        func.lower(Job.company_name).in_(names),
    )


# ── target roles ──────────────────────────────────────────────────────────

def get_user_roles(db: Session, user_id) -> list[str]:
    rows = (
        db.query(TargetRole.role_title)
        .filter(TargetRole.user_id == user_id, TargetRole.is_active.is_(True))
        .all()
    )

    return sorted(
        {r.role_title.strip() for r in rows if r.role_title and r.role_title.strip()},
        key=str.lower,
    )


def roles_for_source(db: Session, source: CareerSource) -> list[str]:
    """
    The roles a scraped job must match to be worth saving for ``source``.

    Jobs are shared by everyone who tracks the same company, so this is the
    union of the roles of all of them. If ANY of those users has no target
    roles they want everything, so nothing is filtered (returns []).
    """

    owners = {source.user_id}

    same_company = (
        db.query(CareerSource.user_id)
        .filter(
            CareerSource.is_active.is_(True),
            func.lower(CareerSource.company_name)
            == (source.company_name or "").strip().lower(),
        )
        .all()
    )

    owners.update(row.user_id for row in same_company)

    union: set[str] = set()

    for owner in owners:
        roles = get_user_roles(db, owner)

        if not roles:
            return []

        union.update(roles)

    return sorted(union, key=str.lower)
