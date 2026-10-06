from tests.db_support import LONG_TEXT, fresh_db, make_source, make_user

from app.database import models as m
from app.services.job_service import (
    build_match_context,
    get_job_match,
    normalize_source_url,
    save_scraped_job,
    store_analysis,
    user_job_scope,
)
from app.services.application_service import delete_application, update_application


def add_job(db, source, title="Engineer", n=1, status=m.JobStatus.ACTIVE):
    return save_scraped_job(db, source, {
        "title": title, "original_url": f"https://e.com/{source.id}/{n}",
        "description": LONG_TEXT,
    })


def visible(db, user):
    scope = user_job_scope(db, user.id)
    if scope is None:
        return []
    return [j.title for j in db.query(m.Job).filter(m.Job.status == m.JobStatus.ACTIVE, scope).all()]


def test_users_only_see_jobs_from_their_own_companies():
    db = fresh_db()
    alice, bob, newbie = make_user(db, "a@x"), make_user(db, "b@x"), make_user(db, "n@x")
    add_job(db, make_source(db, alice, "Acme", "https://a.com"), "Alice job")
    add_job(db, make_source(db, bob, "Globex", "https://b.com"), "Bob job")

    assert visible(db, alice) == ["Alice job"]
    assert visible(db, bob) == ["Bob job"]
    assert visible(db, newbie) == []            # used to see everything


def test_same_company_name_shares_jobs_across_users_case_insensitively():
    db = fresh_db()
    alice, bob = make_user(db, "a@x"), make_user(db, "b@x")
    add_job(db, make_source(db, alice, "Stripe", "https://s.com/jobs"), "Payments Eng")
    make_source(db, bob, "stripe", "https://s.com/careers")
    assert visible(db, bob) == ["Payments Eng"]


def test_removed_sources_hide_their_jobs():
    db = fresh_db()
    u = make_user(db)
    src = make_source(db, u, "Acme", "https://a.com")
    add_job(db, src, "Job")
    src.is_active = False
    db.commit()
    assert visible(db, u) == []


def test_match_context_is_none_without_a_resume_and_scores_with_one():
    db = fresh_db()
    u = make_user(db)
    src = make_source(db, u)
    job = add_job(db, src, "Backend Developer")
    store_analysis(db, job, {"required_skills": ["Python", "Postgres"], "preferred_skills": []})

    assert build_match_context(db, u.id) is None
    assert get_job_match(db, job, u.id) is None

    db.add(m.Resume(user_id=u.id, file_name="r.pdf", storage_path="p", is_active=True,
                    extracted_text="python and sql", structured_profile={"skills": ["Python"], "total_years_experience": 2}))
    db.add(m.TargetRole(user_id=u.id, role_title="Backend Developer"))
    db.commit()

    r = get_job_match(db, job, u.id)
    assert r["match_score"] is not None and r["skill_match"] == 50.0
    assert r["missing_skills"] == ["Postgres"] and r["role_match"] == 100.0


def test_resume_text_helps_match_skills_missing_from_the_skills_list():
    db = fresh_db()
    u = make_user(db)
    job = add_job(db, make_source(db, u))
    store_analysis(db, job, {"required_skills": ["Docker"], "preferred_skills": []})
    db.add(m.Resume(user_id=u.id, file_name="r.pdf", storage_path="p", is_active=True,
                    extracted_text="Containerised services with Docker", structured_profile={"skills": []}))
    db.commit()
    assert get_job_match(db, job, u.id)["skill_match"] == 100.0


def test_application_lifecycle_and_applied_date():
    db = fresh_db()
    u = make_user(db)
    job = add_job(db, make_source(db, u))

    app = update_application(db, u.id, job.id, m.ApplicationStatus.SAVED, "n")
    assert app.applied_at is None

    app = update_application(db, u.id, job.id, m.ApplicationStatus.INTERVIEW, "n2")
    assert app.applied_at is not None and app.notes == "n2"       # interview implies applied
    stamp = app.applied_at

    app = update_application(db, u.id, job.id, m.ApplicationStatus.OFFER, "n3")
    assert app.applied_at == stamp                                  # not overwritten

    assert db.query(m.Application).count() == 1                     # upsert, not duplicate
    assert delete_application(db, u.id, job.id) is True
    assert delete_application(db, u.id, job.id) is False


def test_url_normalisation():
    assert normalize_source_url("HTTPS://Example.COM/Careers/#top") == "https://example.com/Careers"
    assert normalize_source_url("https://a.com/x/") == normalize_source_url("https://a.com/x")


def test_enum_columns_persist_values_not_names():
    """Regression: 'ACTIVE' violated the DB's jobs_status_check constraint."""
    from sqlalchemy import text

    db = fresh_db()
    u = make_user(db)
    job = add_job(db, make_source(db, u))
    update_application(db, u.id, job.id, m.ApplicationStatus.INTERVIEW, "n")

    assert db.execute(text("select status from jobs")).scalar() == "active"
    assert db.execute(text("select status from applications")).scalar() == "Interview"

    db.expire_all()
    assert db.query(m.Job).first().status is m.JobStatus.ACTIVE      # round-trips to the enum
    assert db.query(m.Application).first().status is m.ApplicationStatus.INTERVIEW
