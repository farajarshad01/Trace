"""
Hourly job monitor.

    python -m worker.monitor                 # scrape, then analyse
    python -m worker.monitor --no-ai         # scrape only (debugging)
    python -m worker.monitor --max-analyses 5
    python -m worker.monitor --retry-failed  # re-queue jobs whose analysis failed

Why Gemini was "always busy"
----------------------------
The previous version analysed jobs *inside* the scrape loop:

    for each source:
        for each job:
            save job
            if no JobAnalysis yet:
                analyze_job()      # <- Gemini, immediately, no pacing

That caused three compounding problems:

1. A burst. A Greenhouse board with 300 postings meant ~300 requests in a
   few minutes - far beyond any per-minute quota - so most came back 429/503.
2. A retry loop. A failed analysis saved nothing, so the *next hourly run*
   found the same jobs still un-analysed and fired the same burst again.
   The backlog never drained, and every run re-spent the quota.
3. A shared quota. Rate limits are per *project*, so that background burst
   also starved the interactive resume-upload endpoint on the same key.

What this version does instead
------------------------------
* Scraping and analysis are separate phases; a failing scraper cannot burn
  Gemini quota and vice versa.
* Analysis has a hard per-run budget (MAX_ANALYSES_PER_RUN), is paced
  (GEMINI_MIN_INTERVAL_SECONDS), and works the most relevant jobs first
  (title overlap with users' target roles), newest first.
* Leftovers wait for the next run, so the backlog drains steadily.
* A circuit breaker stops the phase after repeated overload errors or any
  quota error instead of hammering a service that is already saying no.
* Jobs that fail *permanently* (invalid output, rejected request) are stored
  as empty analyses so they are not retried every hour.
* Identical postings (same URL under two sources) reuse one analysis.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func

from app.ai import gemini
from app.ai.errors import (
    AIConfigError,
    AIQuotaError,
    AIResponseError,
    AIServiceError,
)
from app.ai.job_analyzer import analyze_job, is_analyzable
from app.ai.matcher import _role_tokens
from app.core.config import settings
from app.database.connection import SessionLocal
from app.database.models import (
    CareerSource,
    Job,
    JobAnalysis,
    JobStatus,
    TargetRole,
)
from app.scrapers.base import clean_url
from app.services.job_service import (
    close_missing_jobs,
    find_job,
    normalize_source_url,
    save_scraped_job,
    store_analysis,
)
from app.services.source_service import get_scraper


logger = logging.getLogger("trace.worker")

# Stop analysing after this many overload/rate-limit failures in a row.
BREAKER_THRESHOLD = 2


@dataclass
class Summary:
    sources: int = 0
    sources_failed: int = 0
    jobs_seen: int = 0
    jobs_new: int = 0
    jobs_closed: int = 0
    analyzed: int = 0
    reused: int = 0
    failed_permanent: int = 0
    skipped_short: int = 0
    deferred: int = 0
    stopped_reason: str | None = None


# ══════════════════════════════════════════════════════════════════════════
# Phase 1 - scraping
# ══════════════════════════════════════════════════════════════════════════

def process_source(
    db,
    source: CareerSource,
    scraped_cache: dict[str, list[dict]],
    run_started_at: datetime,
    summary: Summary,
) -> None:
    company = source.company_name
    logger.info("Checking %s: %s", company, source.career_url)

    scraper = get_scraper(source.career_url, source.platform)
    cache_key = normalize_source_url(source.career_url)

    try:
        if cache_key in scraped_cache:
            jobs = scraped_cache[cache_key]
        else:
            jobs = scraper.scrape(source.career_url)
            scraped_cache[cache_key] = jobs
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        summary.sources_failed += 1
        logger.error("Source failed (%s): %s", company, exc)
        return

    logger.info("  found %d jobs", len(jobs))

    detail_fetches = 0
    errors = 0

    for scraped in jobs:
        try:
            url = clean_url(scraped.get("original_url"))

            if not url:
                continue

            existing = find_job(db, source.company_name, url)

            # Listing-only scrapers: fetch the text for jobs we have never
            # stored a description for, within a per-source cap.
            if (
                not scraped.get("description")
                and not (existing and existing.description)
                and detail_fetches < settings.MAX_DETAIL_FETCHES_PER_SOURCE
            ):
                detail_fetches += 1

                try:
                    description = scraper.fetch_description(scraped)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("  no description for %s: %s", url, exc)
                    description = None

                if description:
                    scraped["description"] = description

            save_scraped_job(db, source, scraped)

            summary.jobs_seen += 1

            if existing is None:
                summary.jobs_new += 1

        except Exception as exc:  # noqa: BLE001
            errors += 1
            db.rollback()
            logger.warning("  failed saving a job: %s", exc)

    # Only close postings when the scrape clearly worked. An empty or
    # partially failed scrape must never wipe out a whole board.
    if jobs and errors == 0:
        closed = close_missing_jobs(db, source, run_started_at)
        summary.jobs_closed += closed

        if closed:
            logger.info("  closed %d jobs no longer listed", closed)

    source.last_checked_at = datetime.now(timezone.utc)
    db.commit()


def scrape_all(db, run_started_at: datetime, summary: Summary) -> None:
    sources = (
        db.query(CareerSource)
        .filter(CareerSource.is_active.is_(True))
        .order_by(CareerSource.id)
        .all()
    )

    summary.sources = len(sources)
    logger.info("Monitoring %d sources.", len(sources))

    scraped_cache: dict[str, list[dict]] = {}

    for source in sources:
        process_source(db, source, scraped_cache, run_started_at, summary)


# ══════════════════════════════════════════════════════════════════════════
# Phase 2 - analysis (budgeted)
# ══════════════════════════════════════════════════════════════════════════

def _active_role_token_sets(db) -> list[frozenset[str]]:
    rows = (
        db.query(TargetRole.role_title)
        .filter(TargetRole.is_active.is_(True))
        .distinct()
        .all()
    )

    return [t for t in (_role_tokens(r.role_title) for r in rows) if t]


def _relevance(title: str, role_sets: list[frozenset[str]]) -> float:
    if not role_sets:
        return 0.0

    title_tokens = _role_tokens(title)

    return max(
        (len(roles & title_tokens) / len(roles) for roles in role_sets),
        default=0.0,
    )


def pending_job_ids(db) -> list[int]:
    """Active jobs with text but no analysis, most relevant + newest first."""

    rows = (
        db.query(Job.id, Job.title, Job.first_seen_at)
        .outerjoin(JobAnalysis, JobAnalysis.job_id == Job.id)
        .filter(
            JobAnalysis.id.is_(None),
            Job.status == JobStatus.ACTIVE,
            Job.description.isnot(None),
            func.length(Job.description) > 0,
        )
        .all()
    )

    role_sets = _active_role_token_sets(db)

    rows.sort(
        key=lambda r: (
            -_relevance(r.title, role_sets),
            -(r.first_seen_at.timestamp() if r.first_seen_at else 0),
        )
    )

    return [r.id for r in rows]


def _copy_from_twin(db, job: Job) -> bool:
    """Same posting already analysed under another source? Reuse it."""

    twin = (
        db.query(JobAnalysis)
        .join(Job, Job.id == JobAnalysis.job_id)
        .filter(Job.original_url == job.original_url, Job.id != job.id)
        .first()
    )

    if twin is None:
        return False

    store_analysis(
        db,
        job,
        {
            "required_skills": twin.required_skills,
            "preferred_skills": twin.preferred_skills,
            "experience_requirements": twin.experience_requirements,
            "education_requirements": twin.education_requirements,
            "role_summary": twin.role_summary,
        },
    )

    return True


def analyze_pending(db, budget: int, summary: Summary) -> None:
    if budget <= 0:
        return

    if not settings.GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not set - skipping AI analysis.")
        summary.stopped_reason = "no API key"
        return

    queue = pending_job_ids(db)

    logger.info(
        "Analysis queue: %d pending, budget %d call(s), pacing %.1fs.",
        len(queue), budget, settings.GEMINI_MIN_INTERVAL_SECONDS,
    )

    calls_used = 0
    consecutive_overload = 0
    overload_skipped = 0
    position = 0

    while position < len(queue):
        if calls_used >= budget:
            summary.stopped_reason = "budget reached"
            break

        job = db.get(Job, queue[position])
        position += 1

        if job is None:
            continue

        if not is_analyzable(job.description):
            summary.skipped_short += 1
            continue

        if _copy_from_twin(db, job):
            summary.reused += 1
            continue

        calls_used += 1

        try:
            data = analyze_job(job.title, job.description)

        except (AIQuotaError, AIConfigError) as exc:
            # Waiting a few seconds will not fix a spent daily quota or a
            # bad key. Stop now and leave the rest for a later run.
            db.rollback()
            summary.stopped_reason = type(exc).__name__
            logger.error("Stopping analysis: %s", exc)
            break

        except AIServiceError as exc:
            db.rollback()

            if exc.retryable and not _is_bad_output(exc):
                consecutive_overload += 1
                overload_skipped += 1
                logger.warning(
                    "Gemini overloaded (%d/%d): %s",
                    consecutive_overload, BREAKER_THRESHOLD, exc,
                )

                if consecutive_overload >= BREAKER_THRESHOLD:
                    summary.stopped_reason = "Gemini overloaded"
                    logger.error(
                        "Circuit breaker open - deferring the remaining "
                        "jobs to the next run."
                    )
                    break

                continue

            # Permanent for this job: remember it, so it is not re-sent
            # every hour. (Use --retry-failed to re-queue these.)
            consecutive_overload = 0
            summary.failed_permanent += 1
            logger.warning("Analysis failed for job %s: %s", job.id, exc)
            store_analysis(db, job, {})
            continue

        consecutive_overload = 0
        store_analysis(db, job, data)
        summary.analyzed += 1

    summary.deferred = max(len(queue) - position, 0) + overload_skipped

    if summary.deferred and not summary.stopped_reason:
        summary.stopped_reason = "queue drained"


def _is_bad_output(exc: AIServiceError) -> bool:
    # "retryable" covers malformed model output too, but that is a problem
    # with this specific job rather than with service availability.
    return isinstance(exc, AIResponseError)


def reset_failed_analyses(db) -> int:
    """Delete empty placeholder analyses so those jobs are queued again."""

    rows = (
        db.query(JobAnalysis)
        .filter(JobAnalysis.role_summary.is_(None))
        .all()
    )

    count = 0

    for row in rows:
        if not row.required_skills and not row.preferred_skills:
            db.delete(row)
            count += 1

    db.commit()

    return count


# ══════════════════════════════════════════════════════════════════════════
# entry point
# ══════════════════════════════════════════════════════════════════════════

def run_monitor(
    *,
    scrape: bool = True,
    analyze: bool = True,
    max_analyses: int | None = None,
    retry_failed: bool = False,
) -> Summary:
    summary = Summary()
    gemini.reset_stats()

    run_started_at = datetime.now(timezone.utc)
    db = SessionLocal()

    try:
        if retry_failed:
            logger.info(
                "Re-queued %d failed analyses.", reset_failed_analyses(db),
            )

        if scrape:
            scrape_all(db, run_started_at, summary)

        if analyze:
            budget = (
                settings.MAX_ANALYSES_PER_RUN
                if max_analyses is None
                else max_analyses
            )
            analyze_pending(db, budget, summary)

    finally:
        db.close()

    _log_summary(summary)

    return summary


def _log_summary(s: Summary) -> None:
    g = gemini.stats

    logger.info("─" * 60)
    logger.info(
        "Sources: %d (%d failed) | Jobs: %d seen, %d new, %d closed",
        s.sources, s.sources_failed, s.jobs_seen, s.jobs_new, s.jobs_closed,
    )
    logger.info(
        "Analysis: %d done, %d reused, %d failed, %d too short, "
        "%d deferred%s",
        s.analyzed, s.reused, s.failed_permanent, s.skipped_short,
        s.deferred,
        f" (stopped: {s.stopped_reason})" if s.stopped_reason else "",
    )
    logger.info(
        "Gemini: %d calls, %d failures, %d retries, %d fallbacks",
        g.calls, g.failures, g.retries, g.fallbacks,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trace job monitor")
    parser.add_argument("--no-ai", action="store_true",
                        help="scrape only; skip Gemini analysis")
    parser.add_argument("--no-scrape", action="store_true",
                        help="only analyse jobs already in the database")
    parser.add_argument("--max-analyses", type=int, default=None,
                        help="override MAX_ANALYSES_PER_RUN for this run")
    parser.add_argument("--retry-failed", action="store_true",
                        help="re-queue jobs whose analysis previously failed")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    run_monitor(
        scrape=not args.no_scrape,
        analyze=not args.no_ai,
        max_analyses=args.max_analyses,
        retry_failed=args.retry_failed,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
