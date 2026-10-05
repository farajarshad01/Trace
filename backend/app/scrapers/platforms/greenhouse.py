import re
from urllib.parse import parse_qs, urlparse

import requests

from app.core.text import html_to_text
from app.scrapers.base import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    BaseScraper,
    clean_url,
)


_NOT_TOKENS = {"embed", "v1", "boards", "jobs", "job_board"}


def board_token(url: str) -> str:
    """
    https://boards.greenhouse.io/acme                  -> acme
    https://job-boards.greenhouse.io/acme/jobs/12345   -> acme
    https://boards.greenhouse.io/embed/job_board?for=acme -> acme
    """

    parsed = urlparse(url)

    query_token = parse_qs(parsed.query).get("for")

    if query_token:
        return query_token[0]

    for part in parsed.path.split("/"):
        if part and part not in _NOT_TOKENS:
            return part

    raise ValueError(f"Could not find a Greenhouse board name in {url}")


class GreenhouseScraper(BaseScraper):

    def scrape(self, url: str) -> list[dict]:
        token = board_token(url)

        response = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
            params={"content": "true"},
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )

        response.raise_for_status()

        jobs = []

        for job in response.json().get("jobs", []):
            job_url = clean_url(job.get("absolute_url"))
            title = (job.get("title") or "").strip()

            # original_url / title are NOT NULL in the database.
            if not job_url or not title:
                continue

            jobs.append(
                {
                    "title": title,
                    "original_url": job_url,
                    "location": (job.get("location") or {}).get("name"),
                    "employment_type": None,
                    # Greenhouse returns HTML that is itself HTML-escaped.
                    "description": html_to_text(job.get("content")) or None,
                    "external_job_id": str(job.get("id")),
                    "platform": "greenhouse",
                }
            )

        return jobs
