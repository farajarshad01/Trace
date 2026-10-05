"""Text helpers shared by the scrapers and the AI layer."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup


_BLOCK_TAGS = (
    "p", "div", "section", "article", "ul", "ol", "table",
    "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote",
)

_SPACES = re.compile(r"[ \t\u00a0\u200b]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_ENTITY_LEFTOVER = re.compile(r"&(?:lt|gt|amp|quot|#\d+);", re.IGNORECASE)


def html_to_text(value: str | None) -> str:
    """
    Convert HTML (or HTML-escaped HTML) into readable plain text.

    Greenhouse's ``content=true`` field is HTML that has itself been
    HTML-escaped (``&lt;p&gt;Hello&lt;/p&gt;``). Sending that to an LLM
    wastes a large share of the prompt on markup, so we unescape first,
    then strip tags while keeping paragraph and list structure.
    """

    if not value:
        return ""

    text = html.unescape(value)

    # Double-escaped content: unescape a second time if entities remain.
    if _ENTITY_LEFTOVER.search(text) and "<" not in text:
        text = html.unescape(text)

    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        for br in soup.find_all("br"):
            br.replace_with("\n")

        for li in soup.find_all("li"):
            li.insert_before("\n• ")

        for tag in soup.find_all(_BLOCK_TAGS):
            tag.append("\n")

        text = soup.get_text()

    return normalize_whitespace(text)


def normalize_whitespace(text: str) -> str:
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]

    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def truncate(text: str, max_chars: int) -> str:
    """Cut to ``max_chars`` on a paragraph/sentence boundary where possible."""

    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]

    boundary = max(cut.rfind("\n\n"), cut.rfind(". "))

    if boundary > max_chars * 0.6:
        cut = cut[: boundary + 1]

    return cut.rstrip() + "\n[truncated]"
