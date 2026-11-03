"""Page fetcher — fetches HTML from an allowlisted government URL and returns clean plaintext.

Phase 1 only: ephemeral, in-memory. The fetched text is NEVER written to Qdrant here.
Write path is exclusively in backend/etl/extract.py (offline scheduled ETL).
"""
from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup, Comment

from backend.web_search.allowlist import is_allowlisted_url

logger = logging.getLogger("web_search.fetcher")

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-IN,en;q=0.9",
}

# Tags whose entire subtree is noise — stripped before text extraction
_NOISE_TAGS = {
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "button", "input", "select", "textarea", "iframe", "svg",
    "video", "audio", "canvas", "dialog",
}

# Protected structural tags that must NEVER be decomposed even if class has hints
_PROTECTED_TAGS = {"html", "body", "main", "article", "section"}


def fetch_page_text(
    url: str,
    *,
    timeout: float = 10.0,
    max_chars: int = 8000,
) -> str:
    """Fetch and extract clean plaintext from an allowlisted government URL.

    Args:
        url: The target URL. Must pass is_allowlisted_url() check.
        timeout: HTTP request timeout in seconds.
        max_chars: Maximum characters of plaintext to return (truncated if longer).

    Returns:
        Clean plaintext string, or empty string on failure.
    """
    if not is_allowlisted_url(url):
        logger.warning("Blocked fetch of non-allowlisted URL: %.80s", url)
        return ""

    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=5.0),
            follow_redirects=True,
            headers=_FETCH_HEADERS,
            verify=False,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()

            # Handle PDF documents
            content_type = resp.headers.get("content-type", "").lower()
            if "application/pdf" in content_type or url.lower().split("?")[0].endswith(".pdf"):
                try:
                    import io
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                        pages = [p.extract_text() or "" for p in pdf.pages[:6]]
                        clean_pdf = "\n\n".join(p.strip() for p in pages if p.strip())
                        return clean_pdf[:max_chars]
                except Exception as exc:
                    logger.warning("PDF extraction failed (%s): %.80s", exc, url)
                    return ""

            html = resp.text
    except httpx.TimeoutException:
        logger.warning("Page fetch timed out: %.80s", url)
        return ""
    except httpx.HTTPStatusError as exc:
        logger.warning("Page fetch HTTP error %s: %.80s", exc.response.status_code, url)
        return ""
    except Exception as exc:
        logger.warning("Page fetch failed (%s): %.80s", exc, url)
        return ""

    return _extract_text(html, max_chars=max_chars)


def _extract_text(html: str, *, max_chars: int = 8000) -> str:
    """Extract clean article/body text using Trafilatura, with BeautifulSoup fallback."""
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html,
            include_links=False,
            include_images=False,
            include_tables=True,
            no_fallback=False,
        )
        if extracted and len(extracted.strip()) > 40:
            lines = [line.strip() for line in extracted.splitlines()]
            meaningful = [l for l in lines if l and not re.match(r"^[-=_|*]{3,}$", l)]
            cleaned = "\n".join(meaningful)
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
            return cleaned[:max_chars].strip()
    except Exception as exc:
        logger.debug("Trafilatura extraction failed (%s), falling back to BS4", exc)

    # Fallback to BeautifulSoup cleaning
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return ""

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove noise tags directly
    for tag_name in _NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Remove cookie / modal / popup elements specifically without touching protected tags
    for tag in soup.find_all(True):
        if tag.name in _PROTECTED_TAGS:
            continue
        attrs = getattr(tag, "attrs", None)
        if not isinstance(attrs, dict):
            continue
        cls_list = " ".join(str(c) for c in attrs.get("class", [])).lower()
        tag_id = str(attrs.get("id") or "").lower()
        combined = f"{cls_list} {tag_id}"
        # Only decompose specific noise overlays
        if any(h in combined for h in ("cookie-banner", "cookie-notice", "gdpr", "popup-modal", "modal-dialog", "subscribe-popup")):
            tag.decompose()

    # Extract text: prioritize main content containers if present
    content_candidates = soup.select(
        "main, article, .content, .main-content, #content, #main, .post-body, .entry-content"
    )
    if content_candidates:
        text_parts = [el.get_text(separator="\n", strip=True) for el in content_candidates]
        raw_text = "\n\n".join(p for p in text_parts if p.strip())
    else:
        body = soup.find("body")
        raw_text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

    # Clean up whitespace
    lines = [line.strip() for line in raw_text.splitlines()]
    meaningful_lines = [
        line for line in lines
        if len(line) > 15 and not re.match(r"^[-=_|*]{3,}$", line)
    ]
    cleaned = "\n".join(meaningful_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned[:max_chars].strip()


_NAVIGATION_NOISE_PHRASES = (
    "skip to navigation",
    "skip to main content",
    "screen reader access",
    "font size increase",
    "text size decrease",
    "select your language",
    "copyright ©",
    "all rights reserved",
    "site map",
    "feedback",
    "what's new",
    "latest updates",
    "read more",
    "press release",
    "achievements",
    "no front page content has been created yet",
    "follow the user guide",
    "state of the art dashboard",
    "showcasing our achievements",
    "products & services",
    "advisory / achievments",
)


def is_navigation_or_boilerplate_text(text: str) -> bool:
    """Detect whether extracted text is purely navigation boilerplate without procedural content."""
    if not text or len(text.strip()) < 40:
        return True

    lowered = text.lower()
    step_verbs = (
        "visit ", "enter ", "click ", "select ", "submit ", "apply ", "login ",
        "register ", "dial ", "call ", "upload ", "download ", "verify ", "pay ", "fill ",
        "correct", "update", "form",
    )
    has_step_indicators = bool(re.search(r"\b(?:step\s*\d+|steps|[a-g][\.\)])\b", lowered))
    verb_count = sum(1 for v in step_verbs if v in lowered)

    noise_count = sum(1 for p in _NAVIGATION_NOISE_PHRASES if p in lowered)
    # If the text has noise/landing phrases and lacks explicit numbered/lettered steps
    if noise_count >= 1 and not has_step_indicators and verb_count <= 2:
        return True

    if noise_count >= 2:
        return True

    return False


__all__ = ["fetch_page_text", "is_navigation_or_boilerplate_text"]
