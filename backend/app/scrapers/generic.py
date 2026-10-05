import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.core.text import html_to_text
from app.scrapers.base import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    BaseScraper,
    clean_url,
)


# Word boundaries matter: the old substring check treated "ai" as a keyword,
# so "Maintenance Technician", "Retail Assistant" and "Chair" all matched.
_JOB_KEYWORDS = re.compile(
    r"\b(?:engineer|engineering|developer|software|machine learning|"
    r"data scientist|data analyst|intern|internship|trainee|backend|"
    r"frontend|full[\s-]?stack|python|devops|sre|ai|ml)\b",
    re.IGNORECASE,
)

_MIN_TITLE = 4
_MAX_TITLE = 140
_MIN_DESCRIPTION = 200


def _headers() -> dict:
    return {"User-Agent": USER_AGENT}


class GenericScraper(BaseScraper):

    def scrape(self, url: str) -> list[dict]:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=_headers(),
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        unique: dict[str, dict] = {}

        for link in soup.find_all("a", href=True):
            title = link.get_text(" ", strip=True)

            if not (_MIN_TITLE <= len(title) <= _MAX_TITLE):
                continue

            if not _JOB_KEYWORDS.search(title):
                continue

            href = link["href"].strip()

            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue

            job_url = clean_url(urljoin(url, href))

            if not job_url:
                continue

            unique[job_url] = {
                "title": title,
                "original_url": job_url,
                "location": None,
                "employment_type": None,
                "description": None,           # fetched lazily
                "platform": "generic",
            }

        return list(unique.values())

    def fetch_description(self, job: dict) -> str | None:
        response = requests.get(
            job["original_url"],
            timeout=REQUEST_TIMEOUT,
            headers=_headers(),
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        container = soup.find("main") or soup.find("article") or soup.body

        if container is None:
            return None

        text = html_to_text(str(container))

        return text if len(text) >= _MIN_DESCRIPTION else None
