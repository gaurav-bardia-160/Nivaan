# etl package — Phase 2 Background ETL Pipeline (offline write path only)
# This package runs as scheduled offline jobs and handles:
#   extract.py  — download raw HTML from pending_ingestion.jsonl URLs
#   refine.py   — LLM discriminator: statutory content? strip boilerplate, generate JSON
#   vectorize.py — generate FastEmbed vectors and push to domain-isolated Qdrant collections
#   scheduler.py — run extract → refine → vectorize on a configurable schedule
#
# IMPORTANT: None of these modules are called from the live request pipeline (pipeline.py).
# Qdrant writes only happen here, in the offline ETL path.
