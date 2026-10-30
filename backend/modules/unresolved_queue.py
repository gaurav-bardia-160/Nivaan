"""Audit queue for low-confidence and unresolved citizen queries.

Persists failure clusters and ungrounded queries to guide automated crawler expansion
and ingestion auditing.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.config import DATA_DIR
from backend.modules.guardrails import mask_text

logger = logging.getLogger("unresolved_queue")
UNRESOLVED_CSV_PATH = DATA_DIR / "feedback" / "unresolved_queries.csv"


def log_unresolved_query(
    query: str,
    *,
    reason: str,
    domain: str | None = None,
    top_score: float = 0.0,
    conversation_id: str | None = None,
) -> None:
    """Log an unresolved or low-confidence query into the crawler audit queue."""
    if not query or not query.strip():
        return
    try:
        UNRESOLVED_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        is_new = not UNRESOLVED_CSV_PATH.exists() or UNRESOLVED_CSV_PATH.stat().st_size == 0
        masked = mask_text(query).text or query
        timestamp = datetime.now(timezone.utc).isoformat()
        with UNRESOLVED_CSV_PATH.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if is_new:
                writer.writerow(["timestamp", "conversation_id", "query", "domain", "top_score", "reason"])
            writer.writerow([
                timestamp,
                conversation_id or "anonymous",
                masked.replace("\n", " ").strip(),
                domain or "unknown",
                f"{top_score:.4f}",
                reason,
            ])
    except Exception as exc:
        logger.warning("Failed to log unresolved query to audit queue: %s", exc)


__all__ = ["UNRESOLVED_CSV_PATH", "log_unresolved_query"]
