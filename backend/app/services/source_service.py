from app.services.job_service import detect_platform
from app.scrapers.generic import GenericScraper
from app.scrapers.platforms.greenhouse import (
    GreenhouseScraper,
)
from app.scrapers.platforms.lever import LeverScraper
from app.scrapers.platforms.workday import (
    WorkdayScraper,
)


def get_scraper(
    url: str,
    platform: str | None = None,
):
    detected = platform or detect_platform(url)

    if detected == "greenhouse":
        return GreenhouseScraper()

    if detected == "lever":
        return LeverScraper()

    if detected == "workday":
        return WorkdayScraper()

    return GenericScraper()