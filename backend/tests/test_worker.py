"""
End-to-end worker tests against in-memory SQLite, with a fake scraper and a
fake Gemini. They encode the failure mode that kept Gemini "always busy".
"""

from datetime import datetime, timezone

from tests.db_support import LONG_TEXT, fresh_db, make_source, make_user

from app.ai.errors import (
    AIConfigError,
    AIOverloadedError,
    AIQuotaError,
    AIResponseError,
)
from app.core.config import settings
from app.database import models as m
from worker import monitor


class FakeScraper:
    def __init__(self, jobs):
        self.jobs = jobs

    def scrape(self, url):
        return [dict(j) for j in self.jobs]

    def fetch_description(self, job):
        return LONG_TEXT + "(fetched)"


def jobs_for(prefix, n, title="Software Engineer", description=LONG_TEXT):
    return [
        {
            "title": f"{title} {i}",
            "original_url": f"https://example.com/{prefix}/{i}",
            "description": description,
            "platform": "greenhouse",
        }
        for i in range(n)
    ]


GOOD = {
    "required_skills": ["Python"], "preferred_skills": [],
    "experience_requirements": "", "education_requirements": "",
    "role_summary": "Builds things.",
}


class Harness:
    """Patch the scraper + Gemini and count what the worker does."""

    def __init__(self, monkeypatch, scrapers, behaviour=None):
        self.calls = []
        self.behaviour = behaviour or (lambda title: GOOD)

        def fake_get_scraper(url, platform=None):
            return scrapers[url]

        def fake_analyze(title, description, **kw):
            self.calls.append(title)
            result = self.behaviour(title)
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(monitor, "get_scraper", fake_get_scraper)
        monkeypatch.setattr(monitor, "analyze_job", fake_analyze)
        monkeypatch.setattr(settings, "GOOGLE_API_KEY", "x")
        monkeypatch.setattr(settings, "GEMINI_MIN_INTERVAL_SECONDS", 0.0)
        monkeypatch.setattr(settings, "MAX_ANALYSES_PER_RUN", 10)


def count(db, model):
    return db.query(model).count()


# ── the original bug ─────────────────────────────────────────────────────

def test_a_big_board_no_longer_triggers_a_burst_of_gemini_calls(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 300))})

    summary = monitor.run_monitor()

    assert len(h.calls) == 10                      # budget, not 300
    assert summary.analyzed == 10
    assert summary.deferred == 290
    assert count(db, m.Job) == 300 and count(db, m.JobAnalysis) == 10


def test_backlog_drains_across_runs_without_reanalysing(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 25))})

    monitor.run_monitor()
    monitor.run_monitor()
    monitor.run_monitor()

    assert len(h.calls) == 25                      # every job exactly once
    assert len(set(h.calls)) == 25
    assert count(db, m.JobAnalysis) == 25

    before = len(h.calls)
    monitor.run_monitor()                          # nothing pending any more
    assert len(h.calls) == before


def test_overload_trips_the_breaker_instead_of_hammering(monkeypatch):
    """Old behaviour: one failing call per job, every job, every hour."""
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(
        monkeypatch,
        {src.career_url: FakeScraper(jobs_for("a", 100))},
        behaviour=lambda t: AIOverloadedError("busy"),
    )

    summary = monitor.run_monitor()

    assert len(h.calls) == monitor.BREAKER_THRESHOLD   # 2, not 100
    assert summary.stopped_reason == "Gemini overloaded"
    assert count(db, m.JobAnalysis) == 0               # nothing marked done
    assert summary.deferred == 100                     # all retried next run


def test_daily_quota_stops_after_a_single_call(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(
        monkeypatch,
        {src.career_url: FakeScraper(jobs_for("a", 50))},
        behaviour=lambda t: AIQuotaError("quota"),
    )

    summary = monitor.run_monitor()

    assert len(h.calls) == 1
    assert summary.stopped_reason == "AIQuotaError"


def test_bad_api_key_stops_immediately(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(
        monkeypatch,
        {src.career_url: FakeScraper(jobs_for("a", 50))},
        behaviour=lambda t: AIConfigError("bad key"),
    )
    monitor.run_monitor()
    assert len(h.calls) == 1


def test_recovery_after_overload_continues_where_it_stopped(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    state = {"down": True}
    h = Harness(
        monkeypatch,
        {src.career_url: FakeScraper(jobs_for("a", 6))},
        behaviour=lambda t: AIOverloadedError("busy") if state["down"] else GOOD,
    )

    monitor.run_monitor()
    assert count(db, m.JobAnalysis) == 0

    state["down"] = False
    monitor.run_monitor()
    assert count(db, m.JobAnalysis) == 6


def test_single_blip_does_not_trip_the_breaker(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    seen = {"n": 0}

    def flaky(title):
        seen["n"] += 1
        return AIOverloadedError("blip") if seen["n"] == 2 else GOOD

    Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 5))}, flaky)
    summary = monitor.run_monitor()

    assert summary.analyzed == 4 and summary.stopped_reason != "Gemini overloaded"


# ── permanent failures ───────────────────────────────────────────────────

def test_permanent_failures_are_not_retried_every_hour(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(
        monkeypatch,
        {src.career_url: FakeScraper(jobs_for("a", 3))},
        behaviour=lambda t: AIResponseError("garbage"),
    )

    s1 = monitor.run_monitor()
    assert s1.failed_permanent == 3 and len(h.calls) == 3

    monitor.run_monitor()
    assert len(h.calls) == 3                       # not re-sent

    monitor.run_monitor(retry_failed=True)         # explicit opt-in
    assert len(h.calls) == 6


# ── prioritisation / dedupe ──────────────────────────────────────────────

def test_jobs_matching_target_roles_are_analysed_first(monkeypatch):
    db = fresh_db()
    user = make_user(db)
    src = make_source(db, user, url="https://x/board")
    db.add(m.TargetRole(user_id=user.id, role_title="Backend Developer"))
    db.commit()

    jobs = (jobs_for("m", 8, title="Marketing Manager")
            + jobs_for("b", 3, title="Senior Backend Engineer"))
    h = Harness(monkeypatch, {src.career_url: FakeScraper(jobs)})
    monkeypatch.setattr(settings, "MAX_ANALYSES_PER_RUN", 3)

    monitor.run_monitor()

    assert all("Backend" in t for t in h.calls)


def test_same_posting_under_two_sources_costs_one_call(monkeypatch):
    db = fresh_db()
    user = make_user(db)
    a = make_source(db, user, name="Stripe", url="https://x/board")
    b = make_source(db, make_user(db, "o@e.com"), name="Stripe Inc", url="https://x/board/")
    h = Harness(monkeypatch, {
        a.career_url: FakeScraper(jobs_for("s", 4)),
        b.career_url: FakeScraper(jobs_for("s", 4)),
    })

    summary = monitor.run_monitor()

    assert count(db, m.Job) == 8                   # each user sees their own
    assert len(h.calls) == 4 and summary.reused == 4
    assert count(db, m.JobAnalysis) == 8


def test_postings_with_no_real_text_cost_nothing(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 5, description="Apply now"))})

    summary = monitor.run_monitor()

    assert h.calls == [] and summary.skipped_short == 5


def test_no_api_key_skips_analysis_but_still_scrapes(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 5))})
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "")

    monitor.run_monitor()

    assert h.calls == [] and count(db, m.Job) == 5


def test_scrape_only_flag(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    h = Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 5))})
    monitor.run_monitor(analyze=False)
    assert h.calls == [] and count(db, m.Job) == 5


# ── scraping behaviour ───────────────────────────────────────────────────

def test_dropped_postings_are_closed_but_an_empty_scrape_never_wipes_a_board(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    scraper = FakeScraper(jobs_for("a", 5))
    Harness(monkeypatch, {src.career_url: scraper})

    monitor.run_monitor(analyze=False)
    assert db.query(m.Job).filter(m.Job.status == m.JobStatus.ACTIVE).count() == 5

    scraper.jobs = jobs_for("a", 3)                 # company removed 2
    monitor.run_monitor(analyze=False)
    db.expire_all()
    assert db.query(m.Job).filter(m.Job.status == m.JobStatus.ACTIVE).count() == 3
    assert db.query(m.Job).filter(m.Job.status == m.JobStatus.CLOSED).count() == 2

    scraper.jobs = []                               # flaky scrape returns nothing
    monitor.run_monitor(analyze=False)
    db.expire_all()
    assert db.query(m.Job).filter(m.Job.status == m.JobStatus.ACTIVE).count() == 3


def test_reappearing_postings_are_reopened(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    scraper = FakeScraper(jobs_for("a", 2))
    Harness(monkeypatch, {src.career_url: scraper})

    monitor.run_monitor(analyze=False)
    scraper.jobs = jobs_for("a", 1)
    monitor.run_monitor(analyze=False)
    scraper.jobs = jobs_for("a", 2)
    monitor.run_monitor(analyze=False)
    db.expire_all()
    assert db.query(m.Job).filter(m.Job.status == m.JobStatus.ACTIVE).count() == 2


def test_listing_only_scrapers_fetch_descriptions_for_new_jobs_only(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    scraper = FakeScraper(jobs_for("a", 3, description=None))
    fetched = []
    scraper.fetch_description = lambda job: fetched.append(job["title"]) or LONG_TEXT
    Harness(monkeypatch, {src.career_url: scraper})

    monitor.run_monitor(analyze=False)
    assert len(fetched) == 3

    monitor.run_monitor(analyze=False)              # already have the text
    assert len(fetched) == 3


def test_description_is_not_overwritten_by_an_empty_rescrape(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    scraper = FakeScraper(jobs_for("a", 1))
    Harness(monkeypatch, {src.career_url: scraper})
    monitor.run_monitor(analyze=False)

    scraper.jobs = jobs_for("a", 1, description=None)
    scraper.fetch_description = lambda job: None
    monitor.run_monitor(analyze=False)
    db.expire_all()
    assert db.query(m.Job).first().description == LONG_TEXT


def test_one_broken_source_does_not_stop_the_others(monkeypatch):
    db = fresh_db()
    user = make_user(db)
    bad = make_source(db, user, name="Bad", url="https://x/bad")
    good = make_source(db, user, name="Good", url="https://x/good")

    class Boom:
        def scrape(self, url):
            raise RuntimeError("404")

    Harness(monkeypatch, {bad.career_url: Boom(), good.career_url: FakeScraper(jobs_for("g", 2))})
    summary = monitor.run_monitor(analyze=False)

    assert summary.sources_failed == 1 and count(db, m.Job) == 2


def test_inactive_sources_are_ignored(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    src.is_active = False
    db.commit()
    Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 3))})
    monitor.run_monitor(analyze=False)
    assert count(db, m.Job) == 0


# ── failure visibility ───────────────────────────────────────────────────

def test_systemic_save_failures_stop_the_source_early_and_do_not_claim_it_was_checked(monkeypatch, caplog):
    from sqlalchemy.exc import IntegrityError

    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 40))})

    attempts = []

    def always_fails(db_, source, scraped):
        attempts.append(1)
        raise IntegrityError("INSERT INTO jobs ... " + "X" * 5000, {}, Exception("CHECK constraint failed: jobs_status_check"))

    monkeypatch.setattr(monitor, "save_scraped_job", always_fails)

    summary = monitor.run_monitor(analyze=False)

    assert len(attempts) == monitor.SAVE_FAILURE_LIMIT          # 3, not 40
    assert summary.sources_failed == 1
    db.expire_all()
    assert db.query(m.CareerSource).first().last_checked_at is None   # not "checked 1 min ago"
    # the huge INSERT must not be dumped into the log
    assert all(len(r.getMessage()) < 600 for r in caplog.records)
    assert "jobs_status_check" in caplog.text


def test_a_source_with_some_good_saves_is_marked_checked(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    Harness(monkeypatch, {src.career_url: FakeScraper(jobs_for("a", 3))})
    monitor.run_monitor(analyze=False)
    db.expire_all()
    assert db.query(m.CareerSource).first().last_checked_at is not None


def test_a_page_with_no_openings_is_still_marked_checked(monkeypatch):
    db = fresh_db()
    src = make_source(db, make_user(db), url="https://x/board")
    Harness(monkeypatch, {src.career_url: FakeScraper([])})
    monitor.run_monitor(analyze=False)
    db.expire_all()
    assert db.query(m.CareerSource).first().last_checked_at is not None
