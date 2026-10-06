"""Shared helpers: an in-memory SQLite database that understands our models."""

import uuid

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):  # pragma: no cover
    return "JSON"


from sqlalchemy import CheckConstraint  # noqa: E402

from app.database import models as m  # noqa: E402
from app.database.connection import Base, SessionLocal, engine  # noqa: E402


# Mirror the CHECK constraints a hand-written Supabase schema has. SQLite
# would otherwise accept ANY string, which is exactly how a name-vs-value
# mismatch (writing 'ACTIVE' where the DB wants 'active') slipped through.
def _add_check(table, name, column, allowed):
    if not any(getattr(c, "name", None) == name for c in table.constraints):
        values = ", ".join(f"'{v}'" for v in allowed)
        table.append_constraint(CheckConstraint(f"{column} IN ({values})", name=name))


_add_check(m.Job.__table__, "jobs_status_check", "status", [s.value for s in m.JobStatus])
_add_check(m.Application.__table__, "applications_status_check", "status", [s.value for s in m.ApplicationStatus])


def fresh_db():
    # Hard safety net: drop_all() below must only ever touch a throwaway DB.
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError(
            "Refusing to run tests against a non-SQLite database: "
            f"{engine.url.get_backend_name()}"
        )

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return SessionLocal()


def make_user(db, email="u@example.com"):
    user = m.UserProfile(id=uuid.uuid4(), email=email)
    db.add(user)
    db.commit()
    return user


def make_source(db, user, name="Acme", url="https://boards.greenhouse.io/acme"):
    source = m.CareerSource(
        user_id=user.id, company_name=name, career_url=url, platform="greenhouse",
    )
    db.add(source)
    db.commit()
    return source


LONG_TEXT = "We are looking for an engineer who knows Python and SQL. " * 4
