from urllib.parse import urlparse

import requests

from app.core.text import html_to_text
from app.scrapers.base import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    BaseScraper,
    clean_url,
)


def lever_target(url: str) -> tuple[str, str]:
    """Return (api_host, company) for jobs.lever.co and jobs.eu.lever.co."""

    parsed = urlparse(url)
    host = "api.eu.lever.co" if ".eu." in parsed.netloc else "api.lever.co"

    parts = [p for p in parsed.path.split("/") if p]

    if not parts:
        raise ValueError(f"Could not find a Lever company name in {url}")

    # The company is the *first* path segment; later ones are posting ids.
    return host, parts[0]


def build_description(job: dict) -> str:
    """
    ``descriptionPlain`` only holds the intro paragraph. The requirements -
    the part that matters for skill extraction - live in ``lists``.
    """

    parts = [job.get("descriptionPlain") or ""]

    for section in job.get("lists") or []:
        heading = section.get("text") or ""
        body = html_to_text(section.get("content"))

        if heading or body:
            parts.append(f"{heading}\n{body}".strip())

    parts.append(job.get("additionalPlain") or "")

    return "\n\n".join(p.strip() for p in parts if p and p.strip())


class LeverScraper(BaseScraper):

    def scrape(self, url: str) -> list[dict]:
        host, company = lever_target(url)

        response = requests.get(
            f"https://{host}/v0/postings/{company}",
            params={"mode": "json"},
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )

        response.raise_for_status()

        jobs = []

        for job in response.json():
            job_url = clean_url(job.get("hostedUrl"))
            title = (job.get("text") or "").strip()

            if not job_url or not title:
                continue

            categories = job.get("categories") or {}

            jobs.append(
                {
                    "title": title,
                    "original_url": job_url,
                    "location": categories.get("location"),
                    "employment_type": categories.get("commitment"),
                    "description": build_description(job) or None,
                    "external_job_id": job.get("id"),
                    "platform": "lever",
                }
            )

        return jobs
