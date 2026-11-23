"""Web search module — DuckDuckGo HTML endpoint scraper constrained to civic allowlist.

Phase 1 only: ephemeral, read-only. No results are stored to Qdrant here.
Audit logging of failed queries happens via audit_log.py after this module returns results.

Design choices:
- DuckDuckGo HTML endpoint (no API key required, zero cost)
- Falls back gracefully to empty list on any error (timeouts, blocks, empty results)
- Filters results strictly via is_allowlisted_url() — non-gov URLs are silently discarded
- Optional SerpAPI support via SERPAPI_KEY env var for higher quality results
"""
from __future__ import annotations

import logging
import os
import re
from typing import NamedTuple

import httpx
from bs4 import BeautifulSoup

from backend.web_search.allowlist import is_allowlisted_url, get_site_constraint
from backend.modules.domain_router import route_query

logger = logging.getLogger("web_search.searcher")

_SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()

# DuckDuckGo HTML endpoint — POST form-based search, no JS required
_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_DDG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}


def _query_site_domains(query: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\bsite:([A-Za-z0-9.-]+)", query.lower())))


def _matches_query_site(url: str, query: str) -> bool:
    """Require results to honor explicit site constraints instead of only the broad allowlist."""
    domains = _query_site_domains(query)
    if not domains:
        return True
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


class WebSearchResult(dict):
    """A single web search result supporting both object and dict access."""

    def __init__(self, url: str = "", title: str = "", snippet: str = "", link: str = ""):
        actual_url = url or link
        super().__init__(url=actual_url, link=actual_url, title=title, snippet=snippet)
        self.url = actual_url
        self.link = actual_url
        self.title = title
        self.snippet = snippet

    def __repr__(self) -> str:
        return f"WebSearchResult(url='{self.url}', title='{self.title}')"


def _search_serpapi(query: str, *, max_results: int, timeout: float) -> list[WebSearchResult]:
    """SerpAPI-backed search (requires SERPAPI_KEY env var)."""
    try:
        resp = httpx.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "engine": "google",
                "num": max_results,
                "hl": "en",
                "gl": "in",
                "api_key": _SERPAPI_KEY,
            },
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[WebSearchResult] = []
        for item in data.get("organic_results", [])[:max_results]:
            url = str(item.get("link", "")).strip()
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if url and is_allowlisted_url(url) and _matches_query_site(url, query):
                results.append(WebSearchResult(url=url, title=title, snippet=snippet))
        logger.debug("SerpAPI returned %d allowlisted results for query: %.60s", len(results), query)
        return results
    except Exception as exc:
        logger.warning("SerpAPI search failed (%s), falling back to DuckDuckGo", exc)
        return []


def _search_duckduckgo_html(query: str, *, max_results: int, timeout: float) -> list[WebSearchResult]:
    """DuckDuckGo HTML scraper — no API key required."""
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=5.0),
            follow_redirects=True,
            headers=_DDG_HEADERS,
        ) as client:
            resp = client.post(
                _DDG_HTML_URL,
                data={"q": query, "b": "", "kl": "in-en"},
            )
            resp.raise_for_status()
            html = resp.text
    except httpx.TimeoutException:
        logger.warning("DuckDuckGo search timed out for query: %.60s", query)
        return []
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    results: list[WebSearchResult] = []

    # DDG HTML result structure: div.result > h2.result__title > a.result__a
    for result_div in soup.select("div.result"):
        link_tag = result_div.select_one("a.result__a")
        if not link_tag:
            continue

        href = str(link_tag.get("href", "")).strip()
        # DDG sometimes uses redirect URLs — extract the actual target URL
        url = _extract_actual_url(href)
        if not url or not is_allowlisted_url(url) or not _matches_query_site(url, query):
            continue

        title = link_tag.get_text(separator=" ", strip=True)
        snippet_tag = result_div.select_one(".result__snippet")
        snippet = snippet_tag.get_text(separator=" ", strip=True) if snippet_tag else ""

        results.append(WebSearchResult(url=url, title=title[:200], snippet=snippet[:400]))
        if len(results) >= max_results:
            break

    logger.debug("DuckDuckGo returned %d allowlisted results for query: %.60s", len(results), query)
    return results


def _extract_actual_url(href: str) -> str:
    """Extract the real destination URL from DuckDuckGo's redirect wrapper."""
    if not href:
        return ""
    # DDG redirect format: //duckduckgo.com/l/?uddg=https%3A%2F%2F...
    if "uddg=" in href:
        m = re.search(r"uddg=(https?[^&]+)", href)
        if m:
            from urllib.parse import unquote
            return unquote(m.group(1))
    # Direct URL
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return ""


def _search_ddgs(query: str, domain: str = None, *, max_results: int = 3, timeout: float = 8.0) -> list[WebSearchResult]:
    """
    Executes web search without stripping site: constraints.
    """
    # 1. Fetch the exact single domain constraint based on the routed intent
    site_constraint = get_site_constraint(domain) if domain else ""

    # 2. Prevent duplicate constraints if one was already injected
    clean_query = re.sub(r"\bsite:[^\s]+", "", query).strip()

    # 3. Combine query with strict single-site constraint
    constrained_query = f"{clean_query} {site_constraint}".strip() if site_constraint else query
    logger.info(f"Executing DDGS search: {constrained_query}")

    results: list[WebSearchResult] = []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        # Pass the constrained_query directly; do NOT strip site filters
        with DDGS(timeout=timeout) as ddgs:
            raw_results = list(ddgs.text(constrained_query, max_results=max_results, region="in-en"))
            if raw_results:
                for r in raw_results:
                    url = r.get("href", "") or r.get("link", "")
                    title = r.get("title", "")
                    snippet = r.get("body", "") or r.get("snippet", "")
                    if url and is_allowlisted_url(url):
                        results.append(WebSearchResult(url=url, link=url, title=title, snippet=snippet))
    except Exception as e:
        logger.error(f"DDGS Search failed: {e}")
    return results


def prioritize_deep_links(results: list[WebSearchResult]) -> list[WebSearchResult]:
    """Sort allowlisted results so deep procedural sub-pages precede generic root homepages."""
    from urllib.parse import urlparse

    def is_shallow(url: str) -> bool:
        try:
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            shallow_exact = (
                "", "en", "hi", "gu", "home", "index.html", "index.php", "default.aspx",
                "parivahan", "vahan", "sarathi", "foportal", "portal", "main", "welcome",
            )
            if not path or path in shallow_exact:
                return True
            lowered_path = path.lower()
            if any(term in lowered_path for term in ("/login", "/signin", "/auth", "login.", "signin.", "usermgmt")):
                return True
            parts = [p for p in path.split("/") if p and p not in ("en", "hi", "gu", "index.php", "index.html")]
            # Single-segment directory paths without deep ID or extension (e.g. /parivahan/ or /parivahan/index.html)
            if len(parts) <= 1 and not any(parts[0].endswith(ext) for ext in (".pdf", ".html", ".xhtml", ".aspx", ".php") if not parts[0].startswith(("index", "login", "default"))):
                return True
            return False
        except Exception:
            return False

    deep = [r for r in results if not is_shallow(r.url)]
    shallow = [r for r in results if is_shallow(r.url)]
    return deep + shallow


def _result_relevance_score(query: str, result: WebSearchResult) -> float:
    """Deterministically rank official results by topical overlap and procedural depth."""
    query_terms = set(re.findall(r"\b[a-z0-9]{3,}\b", re.sub(r"\bsite:[^\s]+", "", query.lower())))
    text = f"{result.title} {result.snippet} {result.url}".lower()
    overlap = sum(1 for term in query_terms if term in text)
    procedural = sum(1 for term in ("apply", "procedure", "eligibility", "complaint", "faq", "guideline", "scheme", "service") if term in text)
    return float(overlap * 3 + procedural)


def rank_results_for_query(query: str, results: list[WebSearchResult]) -> list[WebSearchResult]:
    deep_first = prioritize_deep_links(results)
    original_order = {result: index for index, result in enumerate(deep_first)}
    return sorted(
        deep_first,
        key=lambda result: (-_result_relevance_score(query, result), original_order[result]),
    )


def search_duckduckgo(
    query: str,
    *,
    domain: str = None,
    max_results: int = 3,
    timeout: float = 8.0,
) -> list[WebSearchResult]:
    """Search DuckDuckGo (or SerpAPI if key is configured) and return allowlisted civic results.

    Args:
        query: The search query string (should include site: constraints from build_allowlist_query).
        domain: Optional civic domain to apply strict targeted site constraints.
        max_results: Maximum number of allowlisted results to return.
        timeout: HTTP request timeout in seconds.

    Returns:
        List of WebSearchResult (url, title, snippet). Empty list on any failure.
    """
    raw_results: list[WebSearchResult] = []
    if _SERPAPI_KEY:
        raw_results = _search_serpapi(query, max_results=max_results, timeout=timeout)
        if raw_results:
            return rank_results_for_query(query, raw_results)[:max_results]
        # Fall through to DuckDuckGo if SerpAPI returns nothing allowlisted

    # Primary: Modern DDGS library
    raw_results = _search_ddgs(query, domain=domain, max_results=max_results * 2, timeout=timeout)
    if raw_results:
        return rank_results_for_query(query, raw_results)[:max_results]

    # Fallback: HTML endpoint scraper
    raw_results = _search_duckduckgo_html(query, max_results=max_results * 2, timeout=timeout)
    return rank_results_for_query(query, raw_results)[:max_results]


__all__ = ["WebSearchResult", "search_duckduckgo", "prioritize_deep_links", "rank_results_for_query"]
