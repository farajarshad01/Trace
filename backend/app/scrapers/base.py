from abc import ABC, abstractmethod
from urllib.parse import urldefrag


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT = 30


def clean_url(url: str | None) -> str | None:
    """Strip whitespace and #fragments so the same posting never duplicates."""

    if not url:
        return None

    cleaned = urldefrag(url.strip())[0]

    return cleaned or None


class BaseScraper(ABC):

    @abstractmethod
    def scrape(self, url: str) -> list[dict]:
        """Return job dicts: title, original_url, location, description, ..."""
        raise NotImplementedError

    def fetch_description(self, job: dict) -> str | None:
        """
        Optional second request for scrapers whose listing page does not
        include the job text. The worker only calls this for jobs it has
        never seen, and caps how many it makes per source per run.
        """
        return None
