from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Optional

from rapidfuzz import fuzz

from backend.config import KNOWLEDGE_BASE_PATH
from backend.schemas import KnowledgeEntry

DATA_PATH = KNOWLEDGE_BASE_PATH
MATCH_THRESHOLD = 55
EXACT_KEYWORD_BONUS = 80
TOKEN_KEYWORD_BONUS = 28
GENERIC_MATCH_TOKENS = {
    "application", "apply", "card", "document", "documents", "form", "new", "proof", "update",
    "fee", "fees", "charge", "charges", "cost", "penalty", "make",
    "online", "portal", "website", "official", "service", "services", "center", "kendra", "procedure", "process",
    "generated", "generating", "generate", "download", "status", "issue", "number",
}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could",
    "did", "do", "does", "for", "from", "have", "how", "i", "if", "in", "into",
    "what", "not", "no", "never",
    "is", "it", "its", "may", "my", "of", "on", "or", "should", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "to", "use", "when",
    "where", "which", "who", "why", "will", "with", "would", "you", "your"
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\baadhar\b", "aadhaar", text)
    text = re.sub(r"\badhar\b", "aadhaar", text)
    text = re.sub(r"\bpancard\b", "pan card", text)
    text = re.sub(r"\bpaspot\b", "passport", text)
    text = re.sub(r"\bpasport\b", "passport", text)
    text = re.sub(r"\bpasssport\b", "passport", text)
    text = re.sub(r"\bvoterid\b", "voter id", text)
    text = re.sub(r"\bvotercard\b", "voter card", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [token for token in text.split() if token not in STOPWORDS]
    return " ".join(tokens)


def _tokens(text: str) -> set[str]:
    normalized = _normalize(text)
    return set(normalized.split()) if normalized else set()


@lru_cache(maxsize=1)
def _load_entries() -> list[dict[str, Any]]:
    try:
        with DATA_PATH.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    valid_entries: list[dict[str, Any]] = []
    for item in data:
        try:
            entry = KnowledgeEntry(**item)
        except Exception:
            continue
        valid_entries.append(entry.model_dump(mode="json"))
    return valid_entries


def _entry_search_text(entry: dict[str, Any]) -> str:
    parts: list[str] = [
        str(entry.get("id", "")),
        str(entry.get("title", "")),
        str(entry.get("category", "")),
        str(entry.get("summary", "")),
    ]
    parts.extend(str(keyword) for keyword in entry.get("keywords", []))
    parts.extend(str(document) for document in entry.get("documents_needed", []))
    for step in entry.get("steps", []):
        parts.append(str(step.get("title", "")))
        parts.append(str(step.get("detail", "")))
    for warning in entry.get("warnings", []):
        parts.append(str(warning.get("title", "")))
        parts.append(str(warning.get("message", "")))
    return " ".join(parts)


def _keyword_match_score(normalized_query: str, query_tokens: set[str], entry: dict[str, Any]) -> int:
    best = 0
    meaningful_query_tokens = {t for t in query_tokens if len(t) > 1 and t not in GENERIC_MATCH_TOKENS}
    if not meaningful_query_tokens:
        return 0
    for keyword in entry.get("keywords", []):
        keyword_norm = _normalize(str(keyword))
        if not keyword_norm:
            continue
        keyword_tokens = set(keyword_norm.split())
        meaningful_keyword_tokens = {t for t in keyword_tokens if len(t) > 1 and t not in GENERIC_MATCH_TOKENS}
        if normalized_query == keyword_norm:
            best = max(best, EXACT_KEYWORD_BONUS)
        elif len(normalized_query) > 1 and (
            re.search(rf"\b{re.escape(keyword_norm)}\b", normalized_query)
            or re.search(rf"\b{re.escape(normalized_query)}\b", keyword_norm)
        ):
            best = max(best, TOKEN_KEYWORD_BONUS + 15)
        else:
            overlap = meaningful_query_tokens & meaningful_keyword_tokens
            if overlap:
                best = max(best, TOKEN_KEYWORD_BONUS * len(overlap))
    return best


def _score_entry(normalized_query: str, query_tokens: set[str], entry: dict[str, Any]) -> float:
    lowered_q = normalized_query.lower()
    entry_id = str(entry.get("id", "")).lower()

    # Cross-domain hard isolation: prevent semantic bleed from dominant clusters
    _DOMAIN_CONFLICTS = (
        ({"voter", "epic", "blo", "nvsp", "eci", "electoral", "voting"}, ("pan_", "aadhaar_", "itr_", "loan_", "rbi_", "pf_")),
        ({"credit card", "cibil", "experian", "crif", "foreclosure"}, ("itr_", "pan_", "aadhaar_")),
        ({"tax", "itr", "139 9", "139 5", "139", "defective return", "defective notice", "income tax", "234f"}, ("aadhaar_", "passport_", "consumer_", "epf_")),
        ({"aadhaar", "aadhar", "uidai"}, ("itr_", "passport_", "pan_card", "consumer_")),
        ({"passport", "psk"}, ("aadhaar_", "itr_", "pan_card", "consumer_")),
    )
    for conflict_terms, blocked_prefixes in _DOMAIN_CONFLICTS:
        if any(term in lowered_q for term in conflict_terms):
            if any(entry_id.startswith(p) for p in blocked_prefixes):
                return 0.0

    if any(k in lowered_q for k in ("139 9", "139(9)", "defective", "condonation", "119")):
        if entry_id in ("itr_filing_basics", "file_itr_basics"):
            return 0.0

    title_norm = _normalize(str(entry.get("title", "")))
    summary_norm = _normalize(str(entry.get("summary", "")))
    search_norm = _normalize(_entry_search_text(entry))

    title_score = fuzz.ratio(normalized_query, title_norm)
    summary_score = fuzz.partial_ratio(normalized_query, summary_norm)
    search_score = fuzz.partial_ratio(normalized_query, search_norm)
    combined_score = (title_score * 0.45) + (summary_score * 0.2) + (search_score * 0.35)

    title_tokens = _tokens(str(entry.get("title", "")))
    search_tokens = set(search_norm.split())
    meaningful_query_tokens = {t for t in query_tokens if len(t) > 1 and t not in GENERIC_MATCH_TOKENS}
    meaningful_title_overlap = meaningful_query_tokens & (title_tokens - GENERIC_MATCH_TOKENS)
    overlap_score = (len(meaningful_title_overlap) * 20) + (len(meaningful_query_tokens & search_tokens) * 7)

    keyword_score = _keyword_match_score(normalized_query, query_tokens, entry)
    if keyword_score == 0 and not meaningful_title_overlap:
        return 0

    return combined_score + overlap_score + keyword_score


def find_entry_with_score(query: str) -> tuple[Optional[dict[str, Any]], float]:
    """Return the best matching knowledge entry and its score."""
    if not query or not query.strip():
        return None, 0.0

    normalized_query = _normalize(query)
    if not normalized_query or len(normalized_query) < 2:
        return None, 0.0

    query_tokens = set(normalized_query.split())
    if not any(len(t) > 1 for t in query_tokens):
        return None, 0.0
    best_entry: Optional[dict[str, Any]] = None
    best_score = 0.0

    for entry in _load_entries():
        final_score = _score_entry(normalized_query, query_tokens, entry)
        if final_score > best_score:
            best_score = final_score
            best_entry = entry

    if best_entry is None or best_score < MATCH_THRESHOLD:
        return None, 0.0

    return best_entry, best_score


def find_entry(query: str) -> Optional[dict[str, Any]]:
    """Return the best matching knowledge entry, or None if no good match exists."""
    entry, _ = find_entry_with_score(query)
    return entry


def find_entry_by_id(entry_id: str) -> Optional[dict[str, Any]]:
    """Return the exact knowledge entry matching the ID, or None if not found."""
    if not entry_id:
        return None
    for entry in _load_entries():
        if str(entry.get("id")) == entry_id:
            return entry
    return None


def knowledge_stats() -> dict[str, int]:
    entries = _load_entries()
    verified = sum(1 for entry in entries if entry.get("status") == "verified")
    unverified = sum(1 for entry in entries if entry.get("status") == "unverified")
    return {"total": len(entries), "verified": verified, "unverified": unverified}


__all__ = [
    "find_entry",
    "find_entry_with_score",
    "find_entry_by_id",
    "knowledge_stats",
    "_load_entries",
    "_normalize",
]
