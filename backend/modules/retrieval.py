from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from rapidfuzz import fuzz

from backend.schemas import KnowledgeEntry

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "check", "could",
    "did", "do", "does", "for", "from", "have", "how", "i", "if", "in", "into",
    "is", "it", "its", "late", "look", "make", "may", "need", "needs", "of", "on",
    "or", "read", "should", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "those", "to", "use", "when", "where", "which", "who", "why",
    "will", "with", "would", "you", "your"
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [token for token in text.split() if token not in STOPWORDS]
    return " ".join(tokens)


def _load_entries() -> list[dict[str, Any]]:
    try:
        with DATA_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    valid_entries: list[dict[str, Any]] = []
    for item in data:
        try:
            valid_entries.append(KnowledgeEntry(**item).model_dump())
        except Exception:
            continue
    return valid_entries


def find_entry(query: str) -> Optional[dict[str, Any]]:
    """Return the best matching verified knowledge entry, or None if no good match exists."""
    if not query or not query.strip():
        return None

    normalized_query = _normalize(query)
    if not normalized_query:
        return None

    best_entry: Optional[dict[str, Any]] = None
    best_score = 0.0

    for entry in _load_entries():
        title = str(entry.get("title", ""))
        summary = str(entry.get("summary", ""))
        title_norm = _normalize(title)
        summary_norm = _normalize(summary)

        title_tokens = set(title_norm.split())
        summary_tokens = set(summary_norm.split())
        query_tokens = set(normalized_query.split())

        overlap_title = len(query_tokens & title_tokens)
        overlap_summary = len(query_tokens & summary_tokens)

        title_score = fuzz.ratio(normalized_query, title_norm)
        summary_score = fuzz.ratio(normalized_query, summary_norm)
        combined_score = (title_score * 0.7) + (summary_score * 0.3)

        final_score = combined_score + (overlap_title * 18) + (overlap_summary * 8)

        if final_score > best_score:
            best_score = final_score
            best_entry = entry

    if best_entry is None:
        return None

    if best_score < 55:
        return None

    return best_entry


__all__ = ["find_entry", "_load_entries"]
