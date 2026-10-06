"""
Fallback scraper for arbitrary company careers pages. It returns every
posting it can recognise; the worker then keeps only those matching the
user's target roles.

The first version treated *any* link whose text contained a word like "AI" or
"Development" as a job. On real company sites that picks up the navigation
menu, footer and cookie banner - e.g. "AI Consulting Services", "Podcast",
"Healthcare & Pharma Clinical AI" - and saves them as jobs.

It now trusts, in order, only signals that actually indicate a job posting:

1. schema.org ``JobPosting`` JSON-LD embedded in the page (authoritative);
2. an embedded/linked Greenhouse, Lever or Workday board, which is handed to
   the dedicated scraper for that platform;
3. links inside the page's *main content* (menus, headers, footers, cookie
   banners and forms are removed first) whose URL looks like a job URL
   (``/jobs/<slug>``, ``/careers/<slug>``, a known ATS host, ...) and whose
   title looks like an engineering role.

A page with no openings correctly yields no jobs.
"""

import json
import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.core.text import html_to_text
from app.scrapers.base import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    BaseScraper,
    clean_url,
)


logger = logging.getLogger("trace.scraper")


# A sanity check that a link's text is a job *title* and not "Benefits" or
# "Our culture". Deliberately broad (not tech-only): WHICH jobs you want is
# decided by your target roles in the worker, not here. The old hard-coded
# engineering keyword list wrongly dropped valid postings like "Technical
# Consultant" and let in any link containing "AI".
_TITLE_NOUN = re.compile(
    r"\b(?:engineers?|engineering|developers?|programmers?|architects?|"
    r"scientists?|researchers?|analysts?|consultants?|designers?|managers?|"
    r"directors?|leads?|specialists?|executives?|officers?|associates?|"
    r"assistants?|coordinators?|administrators?|technicians?|representatives?|"
    r"recruiters?|accountants?|writers?|editors?|strategists?|advisors?|"
    r"testers?|interns?|internships?|trainees?|apprentices?|supervisors?|"
    r"planners?|operators?|instructors?|trainers?|producers?|devops|sre|"
    r"sdet|qa|head|vp|president|clerk|agent|analytics)\b",
    re.IGNORECASE,
)

# Where a card's title ends and its metadata ("Posted 15 days ago", "On-site",
# "Full-time") begins. Links usually wrap the WHOLE card, so without this the
# title was saved as "Senior Salesforce Developer Posted 15 days ago On-site...".
_META_START = re.compile(
    r"\b(?:posted\b|\d+\s+(?:minutes?|hours?|days?|weeks?|months?)\s+ago|"
    r"on[\s-]?site\b|remote\b|hybrid\b|full[\s-]?time\b|part[\s-]?time\b|"
    r"contract\b|apply\b|view\s+(?:job|details)|read\s+more)",
    re.IGNORECASE,
)

# /jobs/<slug>, /careers/<slug>, /open-roles/<slug>, /positions/<id> ...
# The segment AFTER the keyword is required, so the listing page itself
# ("/careers") never counts as a job.
_JOB_WORDS = (
    r"(?:jobs?|careers?|positions?|openings?|vacanc(?:y|ies)|"
    r"opportunit(?:y|ies)|roles?|requisitions?|postings?)"
)
_JOB_PATH = re.compile(
    rf"(?:^|/)[\w-]*{_JOB_WORDS}[\w-]*/[^/?#]+", re.IGNORECASE,
)
# /job-details?id=123  (the id is in the query string, not the path)
_JOB_QUERY_PATH = re.compile(rf"(?:^|/)[\w-]*{_JOB_WORDS}[\w-]*$", re.IGNORECASE)
_JOB_QUERY_ID = re.compile(
    r"(?:^|&)(?:id|job_?id|jid|pid|req(?:uisition)?_?id|gh_jid)=", re.IGNORECASE,
)

# Hosted applicant-tracking systems whose job links are valid on any path.
_ATS_HOSTS = (
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "workable.com",
    "ashbyhq.com", "smartrecruiters.com", "bamboohr.com", "recruitee.com",
    "breezy.hr", "teamtailor.com", "personio.de", "personio.com",
)

_ATS_URL = re.compile(
    r"https?://(?:[\w-]+\.)?(?:greenhouse\.io|lever\.co|myworkdayjobs\.com)"
    r"/[^\s\"'<>)\\]+",
    re.IGNORECASE,
)

# Page chrome that never contains job listings.
_CHROME_TAGS = ("nav", "header", "footer", "aside", "form", "noscript", "dialog")
# Deliberately narrow: a bare "nav"/"menu" also appears on page wrappers
# (<body class="nav-open">), and removing one would delete the whole page.
_CHROME_ATTR = re.compile(
    r"(?:^|[\s_-])(?:cookie|cookies|consent|gdpr|navbar|mega[-_]?menu|"
    r"footer|breadcrumbs?|newsletter)(?:[\s_-]|$)",
    re.IGNORECASE,
)
_STRUCTURAL = {"html", "body", "main", "article"}
_CHROME_ROLES = {"navigation", "banner", "contentinfo", "complementary", "dialog"}

_MIN_TITLE = 4
_MAX_TITLE = 140
_MIN_DESCRIPTION = 200

# A real posting talks about the job; a services page or blog post does not.
_LOOKS_LIKE_JOB = re.compile(
    r"responsibilit|requirement|qualification|you will|what you.ll|"
    r"years of experience|we.re looking for|about the role|apply",
    re.IGNORECASE,
)


def _headers() -> dict:
    return {"User-Agent": USER_AGENT}


def _json_ld_postings(soup: BeautifulSoup) -> list[dict]:
    """Collect schema.org JobPosting objects from <script type=ld+json>."""

    found: list[dict] = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]

            if "JobPosting" in kinds:
                found.append(node)

            for key in ("@graph", "itemListElement", "item", "mainEntity"):
                if key in node:
                    walk(node[key])

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(script.string or script.get_text() or ""))
        except (ValueError, TypeError):
            continue

    return found


def _location(posting: dict) -> str | None:
    loc = posting.get("jobLocation")

    if isinstance(loc, list):
        loc = loc[0] if loc else None

    if isinstance(loc, dict):
        address = loc.get("address")

        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry")
                if isinstance(address.get("addressCountry"), str) else None,
            ]
            text = ", ".join(p for p in parts if p)

            if text:
                return text

    if posting.get("jobLocationType") == "TELECOMMUTE":
        return "Remote"

    return None


def _remove_chrome(soup: BeautifulSoup) -> None:
    for tag in soup(list(_CHROME_TAGS) + ["script", "style"]):
        tag.decompose()

    doomed = []

    for tag in soup.find_all(True):
        if tag.name in _STRUCTURAL or tag.find(["main", "article"]):
            continue                 # never remove something that holds the content

        classes = " ".join(tag.get("class") or [])
        ident = tag.get("id") or ""

        if (
            _CHROME_ATTR.search(classes)
            or _CHROME_ATTR.search(ident)
            or tag.get("role") in _CHROME_ROLES
        ):
            doomed.append(tag)

    for tag in doomed:
        if not tag.decomposed:       # a parent may already have taken it
            tag.decompose()


def _is_job_url(url: str, listing_url: str) -> bool:
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False

    if clean_url(url) == clean_url(listing_url):
        return False

    host = parsed.netloc.lower()

    if any(host == h or host.endswith("." + h) for h in _ATS_HOSTS):
        return True

    if _JOB_PATH.search(parsed.path):
        return True

    return bool(
        _JOB_QUERY_PATH.search(parsed.path.rstrip("/"))
        and _JOB_QUERY_ID.search(parsed.query)
    )


def _link_title(link) -> str:
    """The job title for a link, even when the link wraps an entire card."""

    heading = link.find(re.compile(r"^h[1-6]$"))
    titled = link.find(class_=re.compile(r"title|job-?name|position|role", re.I))
    node = heading or titled or link

    text = node.get_text(" ", strip=True)

    # The first metadata marker that is not at the very start. (A leading
    # "Remote" belongs to the title: "Remote Support Engineer".)
    for meta in _META_START.finditer(text):
        if meta.start() >= _MIN_TITLE:
            text = text[: meta.start()]
            break

    return re.sub(r"[\s|·•\-–—:,(]+$", "", text).strip()


class GenericScraper(BaseScraper):

    # ── listing page ─────────────────────────────────────────────────────
    def scrape(self, url: str) -> list[dict]:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=_headers(),
        )

        response.raise_for_status()

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. Structured data is the most reliable signal there is.
        postings = self._from_json_ld(soup, url)

        if postings:
            return postings

        # 2. A careers page that just embeds Greenhouse / Lever / Workday.
        delegated = self._delegate_to_ats(html, url)

        if delegated:
            return delegated

        # 3. Job-looking links in the main content only.
        return self._from_links(soup, url)

    def _from_json_ld(self, soup: BeautifulSoup, page_url: str) -> list[dict]:
        jobs: dict[str, dict] = {}

        for posting in _json_ld_postings(soup):
            title = str(posting.get("title") or "").strip()
            link = clean_url(
                urljoin(page_url, str(posting.get("url") or posting.get("@id") or ""))
            )

            if not title or not link or link == clean_url(page_url):
                continue

            jobs[link] = {
                "title": title,
                "original_url": link,
                "location": _location(posting),
                "employment_type": (
                    ", ".join(posting["employmentType"])
                    if isinstance(posting.get("employmentType"), list)
                    else posting.get("employmentType")
                ),
                "description": html_to_text(posting.get("description")) or None,
                "platform": "generic",
            }

        return list(jobs.values())

    def _delegate_to_ats(self, html: str, page_url: str) -> list[dict]:
        match = _ATS_URL.search(html)

        if not match:
            return []

        ats_url = match.group(0).rstrip(".,;")
        lowered = ats_url.lower()

        # Imported here to avoid a circular import with the platform modules.
        from app.scrapers.platforms.greenhouse import GreenhouseScraper
        from app.scrapers.platforms.lever import LeverScraper
        from app.scrapers.platforms.workday import WorkdayScraper

        if "greenhouse.io" in lowered:
            scraper = GreenhouseScraper()
        elif "lever.co" in lowered:
            scraper = LeverScraper()
        else:
            scraper = WorkdayScraper()

        try:
            jobs = scraper.scrape(ats_url)
        except Exception as exc:  # noqa: BLE001 - fall through to link search
            logger.info("Embedded ATS %s did not work: %s", ats_url, exc)
            return []

        logger.info("%s embeds %s (%d jobs)", page_url, ats_url, len(jobs))

        return jobs

    def _from_links(self, soup: BeautifulSoup, page_url: str) -> list[dict]:
        _remove_chrome(soup)

        unique: dict[str, dict] = {}
        anchors = soup.find_all("a", href=True)

        for link in anchors:
            href = link["href"].strip()

            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue

            job_url = clean_url(urljoin(page_url, href))

            if not job_url or not _is_job_url(job_url, page_url):
                continue

            title = _link_title(link)

            if not (_MIN_TITLE <= len(title) <= _MAX_TITLE):
                continue

            if not _TITLE_NOUN.search(title):
                continue

            unique.setdefault(
                job_url,
                {
                    "title": title,
                    "original_url": job_url,
                    "location": None,
                    "employment_type": None,
                    "description": None,           # fetched lazily
                    "platform": "generic",
                },
            )

        logger.info(
            "  %s: %d links in main content, %d look like job postings",
            page_url, len(anchors), len(unique),
        )

        return list(unique.values())

    # ── single posting ───────────────────────────────────────────────────
    def fetch_description(self, job: dict) -> str | None:
        response = requests.get(
            job["original_url"],
            timeout=REQUEST_TIMEOUT,
            headers=_headers(),
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for posting in _json_ld_postings(soup):
            text = html_to_text(posting.get("description"))

            if len(text) >= _MIN_DESCRIPTION:
                job["location"] = job.get("location") or _location(posting)

                return text

        _remove_chrome(soup)

        container = soup.find("main") or soup.find("article") or soup.body

        if container is None:
            return None

        text = html_to_text(str(container))

        if len(text) < _MIN_DESCRIPTION or not _LOOKS_LIKE_JOB.search(text):
            return None

        return text
