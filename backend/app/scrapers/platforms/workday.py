"""
Workday career sites are JavaScript single-page apps: the HTML you get from
``requests.get`` contains no job links, so the old regex-over-HTML approach
returned nothing (and titled every hit "Workday Job").

They do expose the JSON API the page itself uses:

    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}

NOTE: this endpoint is unofficial and varies slightly between tenants. It is
written defensively, but verify it against your target companies.
"""

import re
from urllib.parse import urlparse

import requests

from app.core.text import html_to_text
from app.scrapers.base import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    BaseScraper,
    clean_url,
)


PAGE_SIZE = 20
MAX_JOBS = 200

_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2})?$")


def workday_target(url: str) -> tuple[str, str, str]:
    """Return (host, tenant, site) from a myworkdayjobs.com URL."""

    parsed = urlparse(url)
    host = parsed.netloc
    tenant = host.split(".")[0]

    parts = [p for p in parsed.path.split("/") if p]

    if parts and _LOCALE_RE.match(parts[0]):
        parts = parts[1:]

    if not parts:
        raise ValueError(f"Could not find a Workday site name in {url}")

    return host, tenant, parts[0]


class WorkdayScraper(BaseScraper):

    def _headers(self) -> dict:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def scrape(self, url: str) -> list[dict]:
        host, tenant, site = workday_target(url)
        api = f"https://{host}/wday/cxs/{tenant}/{site}"

        jobs: list[dict] = []
        offset = 0

        while offset < MAX_JOBS:
            response = requests.post(
                f"{api}/jobs",
                json={
                    "appliedFacets": {},
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "searchText": "",
                },
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            postings = response.json().get("jobPostings") or []

            if not postings:
                break

            for posting in postings:
                path = posting.get("externalPath")
                title = (posting.get("title") or "").strip()

                if not path or not title:
                    continue

                jobs.append(
                    {
                        "title": title,
                        "original_url": clean_url(
                            f"https://{host}/{site}{path}"
                        ),
                        "location": posting.get("locationsText"),
                        "employment_type": None,
                        "description": None,       # fetched lazily
                        "external_job_id": path.rsplit("_", 1)[-1],
                        "platform": "workday",
                        "_api_path": f"{api}{path}",
                    }
                )

            offset += PAGE_SIZE

        return jobs

    def fetch_description(self, job: dict) -> str | None:
        api_url = job.get("_api_path")

        if not api_url:
            return None

        response = requests.get(
            api_url,
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        info = response.json().get("jobPostingInfo") or {}

        job["employment_type"] = info.get("timeType") or job.get(
            "employment_type"
        )

        return html_to_text(info.get("jobDescription")) or None
