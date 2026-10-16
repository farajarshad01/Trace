"""
Find a company's logo and remember it.

Where the logo comes from
-------------------------
We read it from the company's own website: the ``apple-touch-icon`` (a square,
high-resolution logo most sites publish), else the best ``<link rel="icon">``
(SVG preferred), else ``/favicon.ico``. The URL stored is the company's own
asset; the browser loads it directly, so no third-party logo service sees
which companies you follow.

Which website?
--------------
* Career page on the company's own domain (``devsinc.com/careers``,
  ``careers.acme.com``): that domain.
* Career page on an applicant-tracking system (Greenhouse, Lever, Workday ...):
  the URL says nothing about the company, so we *guess* ``<name>.com`` (then
  .io/.ai/.co) and only accept it if the homepage's title/site name is exactly
  the company name. A wrong logo is worse than initials, so ambiguous names
  ("Linear" -> linear.com is a different company) are rejected.

Everything is best-effort: any failure just means initials are shown.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.database.extras import CompanyLogo
from app.scrapers.base import REQUEST_TIMEOUT, USER_AGENT


logger = logging.getLogger("trace.logo")

FOUND_TTL = timedelta(days=30)       # re-check a known logo monthly
MISSING_TTL = timedelta(days=7)      # retry "not found" weekly
_TIMEOUT = min(REQUEST_TIMEOUT, 10)
_MAX_ICON_BYTES = 2 * 1024 * 1024
_MIN_ICON_BYTES = 120                # smaller is a 1x1 tracking pixel/placeholder

# Hosts whose domain is NOT the company's own.
_THIRD_PARTY = (
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "workable.com",
    "ashbyhq.com", "smartrecruiters.com", "bamboohr.com", "recruitee.com",
    "breezy.hr", "teamtailor.com", "personio.de", "personio.com",
    "jobvite.com", "icims.com", "taleo.net", "oraclecloud.com",
    "applytojob.com", "rippling.com", "linkedin.com", "indeed.com",
    "glassdoor.com", "wellfound.com", "rozee.pk", "dover.com",
)

_CAREER_SUBDOMAINS = {"careers", "career", "jobs", "job", "apply", "hire", "work", "join", "talent", "www"}
_LEGAL_SUFFIX = re.compile(
    r"\b(?:inc|incorporated|llc|ltd|limited|corp|corporation|co|company|pvt|"
    r"private|gmbh|plc|sa|ag|bv|oy)\b\.?", re.IGNORECASE,
)
_GUESS_TLDS = ("com", "io", "ai", "co")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _is_third_party(host: str) -> bool:
    host = host.lower()

    return any(host == h or host.endswith("." + h) for h in _THIRD_PARTY)


def company_domain(career_url: str) -> str | None:
    """The company's own domain from its careers URL, or None if it is hosted
    on an applicant-tracking system / job board."""

    host = (urlparse(career_url or "").hostname or "").lower()

    if not host or "." not in host or _is_third_party(host):
        return None

    labels = host.split(".")

    while len(labels) > 2 and labels[0] in _CAREER_SUBDOMAINS:
        labels = labels[1:]

    return ".".join(labels)


def guess_domains(company_name: str) -> list[str]:
    name = (company_name or "").strip()
    bare = _LEGAL_SUFFIX.sub(" ", name)
    slugs = []

    for candidate in (_norm(bare), _norm(name)):
        if candidate and candidate not in slugs and len(candidate) >= 3:
            slugs.append(candidate)

    return [f"{slug}.{tld}" for slug in slugs for tld in _GUESS_TLDS][:6]


# ── fetching ──────────────────────────────────────────────────────────────

def _get(url: str):
    return requests.get(
        url, timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )


def _icon_candidates(html: str, base_url: str) -> list[str]:
    """Icon URLs found in the page, best first."""

    soup = BeautifulSoup(html, "html.parser")
    scored: list[tuple[int, int, str]] = []

    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        href = urljoin(base_url, link["href"].strip())
        sizes = link.get("sizes") or ""
        biggest = max([int(n) for n in re.findall(r"(\d+)x\d+", sizes)] or [0])

        if "apple-touch-icon" in rel:
            scored.append((0, -(biggest or 180), href))
        elif re.search(r"\bicon\b", rel) and "mask-icon" not in rel:
            is_svg = href.lower().split("?")[0].endswith(".svg") or "svg" in (link.get("type") or "")
            scored.append((1 if is_svg else 2, -biggest, href))

    scored.sort(key=lambda item: (item[0], item[1]))

    urls = [u for _, _, u in scored]
    urls += [urljoin(base_url, "/apple-touch-icon.png"), urljoin(base_url, "/favicon.ico")]

    seen, ordered = set(), []

    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    return ordered[:6]


def _valid_icon(url: str) -> str | None:
    """The final https URL if it really serves an image, else None."""

    try:
        response = _get(url)
    except requests.RequestException:
        return None

    final = str(getattr(response, "url", url) or url)
    kind = (response.headers.get("content-type") or "").lower()
    body = response.content or b""

    if response.status_code != 200 or not final.startswith("https://"):
        return None

    path = final.lower().split("?")[0]
    looks_like_image = kind.startswith("image/") or path.endswith((".ico", ".svg", ".png", ".jpg", ".jpeg", ".webp"))

    if not looks_like_image or "text/html" in kind:
        return None

    if not (_MIN_ICON_BYTES <= len(body) <= _MAX_ICON_BYTES):
        return None

    return final


def _name_matches_page(soup: BeautifulSoup, company_name: str) -> bool:
    """Strict: the page's title/site name must BE the company name."""

    wanted = {_norm(company_name), _norm(_LEGAL_SUFFIX.sub(" ", company_name))} - {""}
    found = set()

    if soup.title and soup.title.string:
        first = re.split(r"\s*[|\u2013\u2014:\u00b7]\s*|\s+-\s+", soup.title.string.strip())[0]
        found.add(_norm(first))

    site = soup.find("meta", attrs={"property": "og:site_name"})

    if site and site.get("content"):
        found.add(_norm(site["content"]))

    return bool(wanted & found)


def find_logo(company_name: str, career_url: str) -> tuple[str | None, str | None, bool]:
    """
    Returns (logo_url, website, reachable). ``reachable`` is False when no site
    could be contacted at all (offline) - the caller should not cache that.
    """

    own = company_domain(career_url)
    sites = [(own, False)] if own else [(d, True) for d in guess_domains(company_name)]
    reachable = False

    for domain, must_verify in sites:
        for base in (f"https://{domain}", f"https://www.{domain}"):
            try:
                page = _get(base)
            except requests.RequestException:
                continue

            reachable = True

            if page.status_code != 200 or "html" not in (page.headers.get("content-type") or "html").lower():
                continue

            site_url = str(getattr(page, "url", base) or base)
            soup = BeautifulSoup(page.text or "", "html.parser")

            if must_verify and not _name_matches_page(soup, company_name):
                break                           # a different company: next domain

            for candidate in _icon_candidates(page.text or "", site_url):
                logo = _valid_icon(candidate)

                if logo:
                    return logo, site_url, True

            return None, site_url, True

    return None, None, reachable


# ── storage ───────────────────────────────────────────────────────────────

def _key(company_name: str) -> str:
    return (company_name or "").strip().lower()[:255]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def ensure_logo(db: Session, company_name: str, career_url: str) -> bool:
    """
    Look the logo up if we do not have a fresh answer. Returns True if it made
    network requests (so callers can budget them).
    """

    key = _key(company_name)

    if not key:
        return False

    now = datetime.now(timezone.utc)
    row = db.get(CompanyLogo, key)

    if row is not None and row.checked_at is not None:
        age = now - _aware(row.checked_at)

        if age < (FOUND_TTL if row.logo_url else MISSING_TTL):
            return False

    logo_url, website, reachable = find_logo(company_name, career_url)

    if not reachable:
        return True                # offline: do not record a false "not found"

    if row is None:
        row = CompanyLogo(company_key=key)
        db.add(row)

    # Never replace a working logo with "not found" because of a bad day.
    if logo_url or not row.logo_url:
        row.logo_url = logo_url

    row.website = website or row.website
    row.checked_at = now

    db.commit()

    return True


def logo_map(db: Session, company_names) -> dict[str, str]:
    """{lower-cased company name: logo url}. Empty if the table is unavailable."""

    keys = {_key(n) for n in company_names if n}

    if not keys:
        return {}

    try:
        rows = (
            db.query(CompanyLogo.company_key, CompanyLogo.logo_url)
            .filter(CompanyLogo.company_key.in_(keys), CompanyLogo.logo_url.isnot(None))
            .all()
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("company_logos unavailable: %s", str(exc).splitlines()[0][:120])
        return {}

    return {row.company_key: row.logo_url for row in rows}


def logo_for(logos: dict[str, str], company_name: str) -> str | None:
    return logos.get(_key(company_name))
