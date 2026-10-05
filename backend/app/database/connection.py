from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


DATABASE_URL = (settings.DATABASE_URL or "").strip()

# The old code silently fell back to a local SQLite file when DATABASE_URL was
# missing. The models use PostgreSQL-only types (JSONB), so that fallback could
# never actually work - it just moved the failure somewhere more confusing.
if not DATABASE_URL or "your_supabase_database_url" in DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. Copy backend/.env.example to "
        "backend/.env and set it to your Supabase Postgres connection string."
    )

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql+psycopg2://", 1,
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+psycopg2://", 1,
    )

engine_kwargs: dict = {}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

    if ":memory:" in DATABASE_URL or DATABASE_URL in ("sqlite://", "sqlite:///"):
        engine_kwargs["poolclass"] = StaticPool    # used by the test-suite
else:
    # Supabase's pooler closes idle connections; without pre-ping the first
    # request after a quiet period fails with "server closed the connection".
    engine_kwargs.update(
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
