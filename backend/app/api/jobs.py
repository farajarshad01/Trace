from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, defer

from app.core.security import get_current_user_id
from app.database.connection import get_db
from app.database.models import (
    Application,
    Job,
    JobAnalysis,
    JobStatus,
)
from app.ai.matcher import Candidate, score_job
from app.schemas.job import JobResponse
from app.services.job_service import (
    analysis_to_dict,
    build_match_context,
    get_user_roles,
    user_job_scope,
)
from app.services.role_filter import title_matches_roles


router = APIRouter(
    prefix="/api/jobs",
    tags=["Jobs"],
)


def _to_response(
    job: Job,
    analysis: JobAnalysis | None,
    match: dict | None,
    *,
    with_description: bool,
) -> JobResponse:
    match = match or {}

    return JobResponse(
        id=job.id,
        company_name=job.company_name,
        title=job.title,
        location=job.location,
        employment_type=job.employment_type,
        description=job.description if with_description else None,
        original_url=job.original_url,
        platform=job.platform,
        status=job.status.value,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        match_score=match.get("match_score"),
        skill_match=match.get("skill_match"),
        experience_match=match.get("experience_match"),
        education_match=match.get("education_match"),
        role_match=match.get("role_match"),
        location_match=match.get("location_match"),
        required_skills=analysis.required_skills if analysis else None,
        preferred_skills=analysis.preferred_skills if analysis else None,
        matched_skills=match.get("matched_skills"),
        missing_skills=match.get("missing_skills"),
        experience_requirements=(
            analysis.experience_requirements if analysis else None
        ),
        education_requirements=(
            analysis.education_requirements if analysis else None
        ),
        role_summary=analysis.role_summary if analysis else None,
        analyzed=analysis is not None,
    )


def _score(
    candidate: Candidate | None,
    job: Job,
    analysis: JobAnalysis | None,
) -> dict | None:
    if candidate is None or analysis is None:
        return None

    return score_job(candidate, analysis_to_dict(analysis), job.title)


@router.get(
    "",
    response_model=list[JobResponse],
)
def get_jobs(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    # Only jobs whose title matches your target roles. Pass false to see
    # everything stored for your companies.
    role_filter: bool = Query(default=True),
):
    scope = user_job_scope(db, user_id)

    if scope is None:
        return []

    # One query for jobs + analyses (no N+1) and without the large
    # description column.
    rows = (
        db.query(Job, JobAnalysis)
        .outerjoin(JobAnalysis, JobAnalysis.job_id == Job.id)
        .options(defer(Job.description))
        .filter(Job.status == JobStatus.ACTIVE, scope)
        .all()
    )

    if role_filter:
        roles = get_user_roles(db, user_id)

        if roles:
            rows = [
                (job, analysis)
                for job, analysis in rows
                if title_matches_roles(job.title, roles)
            ]

    candidate = build_match_context(db, user_id)

    scored = [
        (job, analysis, _score(candidate, job, analysis))
        for job, analysis in rows
    ]

    # Best match first; unscored jobs last; newest first within ties. Doing
    # this *before* the limit is applied means the top matches can no longer
    # be hidden behind an arbitrary "last_seen_at" cut-off (every run bumps
    # last_seen_at on every job, so that ordering was meaningless).
    scored.sort(
        key=lambda item: (
            item[2] is None or item[2].get("match_score") is None,
            -((item[2] or {}).get("match_score") or 0),
            -item[0].first_seen_at.timestamp(),
        )
    )

    return [
        _to_response(job, analysis, match, with_description=False)
        for job, analysis, match in scored[offset: offset + limit]
    ]


@router.get(
    "/{job_id}",
    response_model=JobResponse,
)
def get_job(
    job_id: int,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    tracked = (
        db.query(Application.id)
        .filter(Application.user_id == user_id, Application.job_id == job_id)
        .first()
    )

    if not tracked:
        scope = user_job_scope(db, user_id)
        allowed = (
            scope is not None
            and db.query(Job.id).filter(Job.id == job_id, scope).first()
        )

        if not allowed:
            raise HTTPException(status_code=404, detail="Job not found.")

    analysis = (
        db.query(JobAnalysis).filter(JobAnalysis.job_id == job.id).first()
    )

    match = _score(build_match_context(db, user_id), job, analysis)

    return _to_response(job, analysis, match, with_description=True)
