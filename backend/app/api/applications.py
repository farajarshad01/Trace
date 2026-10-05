from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user_id
from app.database.connection import get_db
from app.database.models import (
    Application,
    Job,
)
from app.schemas.application import (
    ApplicationResponse,
    ApplicationUpdate,
)
from app.services.application_service import (
    delete_application,
    update_application,
)


router = APIRouter(
    prefix="/api/applications",
    tags=["Applications"],
)


@router.get(
    "",
    response_model=list[ApplicationResponse],
)
def get_applications(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # The job is embedded so the Applications page no longer has to fetch
    # (and be limited to) the dashboard's job list to find a title.
    return (
        db.query(Application)
        .options(joinedload(Application.job))
        .filter(Application.user_id == user_id)
        .order_by(Application.updated_at.desc())
        .all()
    )


@router.get(
    "/{job_id}",
    response_model=ApplicationResponse | None,
)
def get_application(
    job_id: int,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(Application)
        .options(joinedload(Application.job))
        .filter(
            Application.user_id == user_id,
            Application.job_id == job_id,
        )
        .first()
    )


@router.put(
    "/{job_id}",
    response_model=ApplicationResponse,
)
def save_application(
    job_id: int,
    payload: ApplicationUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    update_application(
        db=db,
        user_id=user_id,
        job_id=job_id,
        status=payload.status,
        notes=payload.notes,
    )

    return (
        db.query(Application)
        .options(joinedload(Application.job))
        .filter(
            Application.user_id == user_id,
            Application.job_id == job_id,
        )
        .first()
    )


@router.delete("/{job_id}")
def remove_application(
    job_id: int,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not delete_application(db, user_id, job_id):
        raise HTTPException(
            status_code=404,
            detail="Application not found.",
        )

    return {"message": "Application removed."}
