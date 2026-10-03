"""Retrieval module for finding verified knowledge base entries matching user queries."""

from __future__ import annotations

import json
from typing import Any, Optional

try:
    from backend.config import DATA_DIR
except ImportError:
    from config import DATA_DIR


def _load_knowledge_base() -> list[dict[str, Any]]:
    kb_path = DATA_DIR / "knowledge_base.json"
    if not kb_path.exists():
        return []
    with open(kb_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _score_match(query: str, entry: dict[str, Any]) -> float:
    query_lower = query.lower()
    score = 0.0

    if query_lower in entry.get("title", "").lower():
        score += 0.5

    keywords = entry.get("keywords", [])
    if keywords:
        keyword_matches = sum(1 for kw in keywords if kw.lower() in query_lower)
        score += (keyword_matches / max(len(keywords), 1)) * 0.3

    summary = entry.get("summary", "").lower()
    if query_lower in summary:
        score += 0.2

    return min(score, 1.0)


def find_entry(query: str) -> Optional[dict[str, Any]]:
    if not query or not query.strip():
        return None

    entries = _load_knowledge_base()
    if not entries:
        return None

    scored = [
        (entry, _score_match(query, entry))
        for entry in entries
        if entry.get("status") == "verified"
    ]

    if not scored:
        return None

    best_entry, best_score = max(scored, key=lambda x: x[1])
    if best_score > 0.0:
        return best_entry

    return None
