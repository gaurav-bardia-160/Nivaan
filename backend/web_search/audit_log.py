"""Audit log — thread-safe append-only log for queries that fell through to web search.

This log is the HANDOFF between Phase 1 (live request) and Phase 2 (background ETL).
The ETL pipeline reads this file offline to decide which URLs to download and ingest into Qdrant.

IMPORTANT: This module only writes to pending_ingestion.jsonl.
           It NEVER writes to Qdrant. The live pipeline is strictly read-only to Qdrant.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import TypedDict

from backend.config import ETL_DIR, PENDING_INGESTION_PATH

logger = logging.getLogger("web_search.audit_log")

# Thread-safe write lock — multiple concurrent requests should not interleave JSONL lines
_write_lock = threading.Lock()


class IngestionRecord(TypedDict):
    """Schema for a single pending ingestion record."""
    query: str          # The original user query (PII should already be masked)
    url: str            # The web page URL that was successfully fetched
    domain: str         # Domain string (e.g., "transport", "tax", "identity")
    timestamp: str      # ISO 8601 UTC timestamp
    snippet: str        # Short snippet from the search result (for QA)


def log_pending_ingestion(record: IngestionRecord) -> None:
    """Append a single IngestionRecord to pending_ingestion.jsonl (thread-safe).

    Creates the ETL directory and file if they don't exist.
    Silently drops the record on any write error (never crashes the live pipeline).

    Args:
        record: An IngestionRecord dict with query, url, domain, timestamp, snippet.
    """
    try:
        # Ensure ETL directory exists
        ETL_DIR.mkdir(parents=True, exist_ok=True)

        # Validate and sanitize the record
        sanitized: IngestionRecord = {
            "query": str(record.get("query", ""))[:800],
            "url": str(record.get("url", ""))[:500],
            "domain": str(record.get("domain", "unknown"))[:40],
            "timestamp": str(record.get("timestamp", datetime.now(timezone.utc).isoformat())),
            "snippet": str(record.get("snippet", ""))[:400],
        }

        line = json.dumps(sanitized, ensure_ascii=False)

        with _write_lock:
            with open(PENDING_INGESTION_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        logger.info(
            "Audit log: queued URL for ETL ingestion — domain=%s url=%.60s",
            sanitized["domain"],
            sanitized["url"],
        )
    except Exception as exc:
        # Never let audit logging crash the live response pipeline
        logger.warning("Audit log write failed (non-critical): %s", exc)


def read_pending_queue() -> list[IngestionRecord]:
    """Read all pending ingestion records. Used by ETL extract.py offline.

    Returns:
        List of IngestionRecord dicts. Returns empty list if file doesn't exist or is corrupt.
    """
    if not PENDING_INGESTION_PATH.exists():
        return []

    records: list[IngestionRecord] = []
    try:
        with open(PENDING_INGESTION_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if isinstance(record, dict):
                        records.append(record)  # type: ignore[arg-type]
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed audit log line")
    except Exception as exc:
        logger.warning("Failed to read pending ingestion queue: %s", exc)

    return records


__all__ = ["IngestionRecord", "log_pending_ingestion", "read_pending_queue"]
