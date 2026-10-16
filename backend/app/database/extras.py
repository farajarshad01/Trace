"""
Tables added after the original schema: hidden jobs and company logos.

They live in a separate module, and as separate TABLES (not new columns on
existing ones), on purpose: if one is ever missing - say the database user
may not run DDL - only that feature degrades. Jobs, applications and sources
keep working, which they would not if the ORM selected a column that does
not exist.

`ensure_extra_tables()` creates them if absent. It is idempotent and is
called when the API and the worker start, so no manual migration is needed.
The equivalent SQL is also in backend/migrations/001_hidden_jobs_and_logos.sql.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


logger = logging.getLogger("trace.db")


class DismissedJob(Base):
    """A job one user marked "not relevant". Per user - other users still see it."""

    __tablename__ = "dismissed_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_dismissed_jobs_user_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class CompanyLogo(Base):
    """Resolved logo per company (lower-cased name), shared by every user."""

    __tablename__ = "company_logos"

    company_key: Mapped[str] = mapped_column(String(255), primary_key=True)

    # NULL = we looked and found nothing (retried after a cool-down).
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    website: Mapped[str | None] = mapped_column(Text, nullable=True)

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


def ensure_extra_tables(engine) -> bool:
    """Create the tables above if missing. Returns False if any step failed."""

    ok = True

    for model in (DismissedJob, CompanyLogo):
        try:
            model.__table__.create(bind=engine, checkfirst=True)

            # Supabase exposes every public table through its REST API. With
            # RLS on and no policies, only the backend (which connects with
            # the database role) can touch these tables - not the anon key.
            if engine.dialect.name == "postgresql":
                with engine.begin() as conn:
                    conn.execute(
                        text(f'ALTER TABLE "{model.__tablename__}" ENABLE ROW LEVEL SECURITY')
                    )
        except Exception as exc:  # noqa: BLE001
            ok = False
            logger.warning(
                "Could not prepare table %s (%s). That feature will be "
                "unavailable until it exists - see "
                "backend/migrations/001_hidden_jobs_and_logos.sql",
                model.__tablename__, str(exc).splitlines()[0][:160],
            )

    return ok
