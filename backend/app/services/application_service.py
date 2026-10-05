from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database.models import (
    Application,
    ApplicationStatus,
)


# Reaching any of these implies the person has applied.
_APPLIED_OR_LATER = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
}


def update_application(
    db: Session,
    user_id,
    job_id: int,
    status: ApplicationStatus,
    notes: str | None,
):
    application = (
        db.query(Application)
        .filter(
            Application.user_id == user_id,
            Application.job_id == job_id,
        )
        .first()
    )

    now = datetime.now(timezone.utc)

    if not application:
        application = Application(
            user_id=user_id,
            job_id=job_id,
            status=status,
            notes=notes,
        )

        if status in _APPLIED_OR_LATER:
            application.applied_at = now

        db.add(application)

    else:
        application.status = status
        application.notes = notes

        if status in _APPLIED_OR_LATER and application.applied_at is None:
            application.applied_at = now

    db.commit()
    db.refresh(application)

    return application


def delete_application(db: Session, user_id, job_id: int) -> bool:
    application = (
        db.query(Application)
        .filter(
            Application.user_id == user_id,
            Application.job_id == job_id,
        )
        .first()
    )

    if not application:
        return False

    db.delete(application)
    db.commit()

    return True
