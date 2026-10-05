from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.database.connection import get_db
from app.database.models import CareerSource
from app.schemas.source import (
    CareerSourceCreate,
    CareerSourceResponse,
)
from app.services.job_service import (
    detect_platform,
    normalize_source_url,
)


router = APIRouter(
    prefix="/api/sources",
    tags=["Career Sources"],
)


@router.get(
    "",
    response_model=list[CareerSourceResponse],
)
def get_sources(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(CareerSource)
        .filter(
            CareerSource.user_id == user_id,
            CareerSource.is_active.is_(True),
        )
        .order_by(CareerSource.created_at.desc())
        .all()
    )


@router.post(
    "",
    response_model=CareerSourceResponse,
)
def create_source(
    payload: CareerSourceCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    url = normalize_source_url(str(payload.career_url))
    company_name = payload.company_name.strip()

    if not company_name:
        raise HTTPException(
            status_code=400,
            detail="Company name cannot be empty.",
        )

    # Compare normalised URLs so "…/careers" and "…/careers/" are the same.
    candidates = (
        db.query(CareerSource)
        .filter(CareerSource.user_id == user_id)
        .all()
    )

    existing = next(
        (
            source for source in candidates
            if normalize_source_url(source.career_url) == url
        ),
        None,
    )

    if existing:
        # "Remove" only sets is_active=False. The old code then found that
        # row on re-add and returned it unchanged, so a removed company
        # could never be added back.
        if not existing.is_active:
            existing.is_active = True
            existing.company_name = company_name
            db.commit()
            db.refresh(existing)

        return existing

    source = CareerSource(
        user_id=user_id,
        company_name=company_name,
        career_url=url,
        platform=detect_platform(url),
        is_active=True,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return source


@router.delete("/{source_id}")
def delete_source(
    source_id: int,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    source = (
        db.query(CareerSource)
        .filter(
            CareerSource.id == source_id,
            CareerSource.user_id == user_id,
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Career source not found.",
        )

    source.is_active = False

    db.commit()

    return {
        "message": "Career source removed."
    }
