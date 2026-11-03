"""ETL Phase 2 — Extract: Download raw HTML for all pending ingestion URLs.

Reads pending_ingestion.jsonl (written by Phase 1 audit_log.py) and downloads
the raw HTML of each flagged URL to backend/data/etl/raw/.

This script:
  1. Reads all records from pending_ingestion.jsonl
  2. Skips already-processed URLs (tracked in a .processed marker file)
  3. Downloads each URL's HTML to ETL_RAW_DIR/{url_hash}.html
  4. Saves a metadata sidecar at ETL_RAW_DIR/{url_hash}.json

Usage (offline only):
    py -m backend.etl.extract

Never import or call this from the live request pipeline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import httpx

# Ensure package is importable when run as __main__
if __name__ == "__main__":
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import ETL_RAW_DIR, PENDING_INGESTION_PATH
from backend.web_search.allowlist import is_allowlisted_url
from backend.web_search.audit_log import read_pending_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("etl.extract")

_PROCESSED_MARKER = ETL_RAW_DIR / ".processed_urls.json"
_FETCH_TIMEOUT = 15.0
_RATE_LIMIT_DELAY = 1.5  # seconds between requests (be polite to gov servers)

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-IN,en;q=0.9",
}


def _url_hash(url: str) -> str:
    """Generate a stable filename-safe hash for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _load_processed_urls() -> set[str]:
    """Load the set of already-processed URLs from the marker file."""
    if not _PROCESSED_MARKER.exists():
        return set()
    try:
        with open(_PROCESSED_MARKER, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_processed_urls(processed: set[str]) -> None:
    """Persist the set of processed URLs."""
    try:
        with open(_PROCESSED_MARKER, "w", encoding="utf-8") as f:
            json.dump(sorted(processed), f, indent=2)
    except Exception as exc:
        logger.warning("Failed to save processed URLs marker: %s", exc)


def extract_all() -> int:
    """Run extraction for all pending URLs. Returns number of newly downloaded files."""
    ETL_RAW_DIR.mkdir(parents=True, exist_ok=True)

    pending = read_pending_queue()
    if not pending:
        logger.info("No pending URLs to extract.")
        return 0

    processed_urls = _load_processed_urls()
    newly_processed: set[str] = set()
    download_count = 0

    logger.info("Found %d pending records. Already processed: %d", len(pending), len(processed_urls))

    for record in pending:
        url = record.get("url", "").strip()
        if not url:
            continue
        if url in processed_urls:
            logger.debug("Skipping already-processed URL: %.60s", url)
            continue
        if not is_allowlisted_url(url):
            logger.warning("Skipping non-allowlisted URL: %.60s", url)
            processed_urls.add(url)
            continue

        url_hash = _url_hash(url)
        html_path = ETL_RAW_DIR / f"{url_hash}.html"
        meta_path = ETL_RAW_DIR / f"{url_hash}.json"

        if html_path.exists():
            logger.debug("Raw file already exists for %.60s, skipping download", url)
            processed_urls.add(url)
            continue

        logger.info("Downloading: %.80s", url)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(_FETCH_TIMEOUT, connect=5.0),
                follow_redirects=True,
                headers=_FETCH_HEADERS,
                verify=False,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html_bytes = resp.content
                encoding = resp.encoding or "utf-8"

            # Write raw HTML
            html_path.write_bytes(html_bytes)

            # Write metadata sidecar
            meta = {
                "url": url,
                "domain": record.get("domain", "unknown"),
                "query": record.get("query", ""),
                "snippet": record.get("snippet", ""),
                "fetched_at": record.get("timestamp", ""),
                "http_status": resp.status_code,
                "encoding": encoding,
                "content_length": len(html_bytes),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            download_count += 1
            newly_processed.add(url)
            logger.info("Downloaded %d bytes → %s.html", len(html_bytes), url_hash)

        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %s for %.60s — marking as processed", exc.response.status_code, url)
            newly_processed.add(url)
        except Exception as exc:
            logger.warning("Download failed for %.60s: %s", url, exc)
            # Don't mark as processed — will retry next run

        time.sleep(_RATE_LIMIT_DELAY)

    processed_urls |= newly_processed
    _save_processed_urls(processed_urls)

    logger.info("Extract complete. Downloaded %d new files.", download_count)
    return download_count


if __name__ == "__main__":
    count = extract_all()
    sys.exit(0 if count >= 0 else 1)
