"""ETL Phase 2 — Scheduler: Run the ETL pipeline (extract → refine → vectorize) on a schedule.

Runs entirely offline as a background long-running process.
Checks if the live LLM is actively generating before running (to avoid CPU contention).

Usage:
    py -m backend.etl.scheduler          # Runs every 4 hours (default)
    ETL_INTERVAL_HOURS=2 py -m backend.etl.scheduler

Never import or call this from the live request pipeline.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Ensure package is importable when run as __main__
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import schedule

from backend.config import ETL_INTERVAL_HOURS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("etl.scheduler")


def _is_llm_generating() -> bool:
    """Check if the live LLM is currently generating (to avoid CPU contention)."""
    try:
        from backend.modules.llm import _is_generating
        return bool(_is_generating)
    except Exception:
        return False


def run_etl_pipeline() -> None:
    """Run the full ETL pipeline: extract → refine → vectorize."""
    if _is_llm_generating():
        logger.info("LLM is actively generating — deferring ETL run to avoid CPU contention.")
        return

    logger.info("=== ETL Pipeline Starting ===")

    # Phase 2a: Extract
    try:
        from backend.etl.extract import extract_all
        downloaded = extract_all()
        logger.info("Extract: %d new files downloaded", downloaded)
    except Exception as exc:
        logger.error("Extract phase failed: %s", exc)
        downloaded = 0

    if downloaded == 0:
        # Check if there are already-downloaded raw files waiting for refinement
        from backend.config import ETL_RAW_DIR
        pending_raw = list(ETL_RAW_DIR.glob("*.html"))
        if not pending_raw:
            logger.info("No raw files to process. ETL pipeline skipping refine/vectorize.")
            return

    # Phase 2b: Refine
    try:
        from backend.etl.refine import refine_all
        approved, rejected = refine_all()
        logger.info("Refine: approved=%d rejected=%d", approved, rejected)
    except Exception as exc:
        logger.error("Refine phase failed: %s", exc)
        approved = 0

    if approved == 0:
        logger.info("No approved refined files. Skipping vectorize phase.")
        return

    # Phase 2c: Vectorize
    try:
        from backend.etl.vectorize import vectorize_all
        vectorized = vectorize_all()
        logger.info("Vectorize: %d files ingested to Qdrant", vectorized)
    except Exception as exc:
        logger.error("Vectorize phase failed: %s", exc)

    logger.info("=== ETL Pipeline Complete ===")


def main() -> None:
    interval_hours = max(1, ETL_INTERVAL_HOURS)
    logger.info(
        "ETL Scheduler started. Pipeline runs every %d hour(s). "
        "Running initial pass immediately...",
        interval_hours,
    )

    # Run immediately on startup
    run_etl_pipeline()

    # Schedule recurring runs
    schedule.every(interval_hours).hours.do(run_etl_pipeline)

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("ETL Scheduler stopped by user.")


if __name__ == "__main__":
    main()
