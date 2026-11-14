# etl package — offline web-search ingestion pipeline
# This package runs as an operator-controlled offline job and handles:
#   extract.py   — download approved official pages from pending_ingestion.jsonl
#   refine.py    — classify and clean procedural source text
#   vectorize.py — publish schema-validated JSONL into the canonical manifest and
#                  rebuild the unified local Qdrant index used by live RAG
#   scheduler.py — run extract → refine → canonical publish/index
#
# IMPORTANT: None of these modules are called from the live request pipeline.
# The canonical manifest is the source of truth for both lexical and vector RAG.
