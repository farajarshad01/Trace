"""Hide jobs the user finds irrelevant (per user; the job itself is untouched)."""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.extras import DismissedJob


logger = logging.getLogger("trace.dismiss")


def dismissed_ids(db: Session, user_id) -> set[int]:
    """Ids this user hid. Empty (never an error) if the table is unavailable."""

    try:
        rows = (
            db.query(DismissedJob.job_id)
            .filter(DismissedJob.user_id == user_id)
            .all()
        )
    except Exception as exc:  # noqa: BLE001 - feature degrades, app keeps working
        db.rollback()
        logger.warning("dismissed_jobs unavailable: %s", str(exc).splitlines()[0][:120])
        return set()

    return {row.job_id for row in rows}


def dismiss_job(db: Session, user_id, job_id: int) -> None:
    """Idempotent: hiding an already hidden job is a no-op."""

    exists = (
        db.query(DismissedJob.id)
        .filter(DismissedJob.user_id == user_id, DismissedJob.job_id == job_id)
        .first()
    )

    if exists:
        return

    db.add(DismissedJob(user_id=user_id, job_id=job_id))

    try:
        db.commit()
    except IntegrityError:           # two clicks racing: the other one won
        db.rollback()


def restore_job(db: Session, user_id, job_id: int) -> bool:
    deleted = (
        db.query(DismissedJob)
        .filter(DismissedJob.user_id == user_id, DismissedJob.job_id == job_id)
        .delete()
    )

    db.commit()

    return bool(deleted)
