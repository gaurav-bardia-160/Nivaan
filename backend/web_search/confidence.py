"""Confidence scoring — maps raw RRF retrieval scores to a normalized [0.0, 1.0] confidence value.

The confidence gate in pipeline.py uses this to decide whether to use the Qdrant/BM25 result
or fall back to live web search / honest refusal.

Multi-Factor Relevance & Confidence Gating (R2):
  Confidence = BaseScore × EntityAlignment × TermOverlap
  - BaseScore: RRF top score normalized against _RRF_HIGH_CONFIDENCE_FLOOR (0.040).
  - EntityAlignment: Enforces statutory anchor alignment (Sections 147-151, 206AA, 114AAA, 234H, etc.).
    If statutory anchors are in the query and the candidate chunk lacks support, confidence is
    penalized strictly below 0.35 (triggering CRAG or honest refusal).
  - TermOverlap: Content word containment factor preventing accidental single-word collisions
    from scoring high confidence.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("web_search.confidence")

# Empirically determined RRF score at which we consider retrieval "high confidence"
_RRF_HIGH_CONFIDENCE_FLOOR = 0.040

_CIVIC_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "what", "how", "when", "where", "which", "who", "why", "did", "does", "have",
    "has", "had", "can", "could", "should", "would", "will", "got", "get", "come",
    "came", "under", "about", "into", "over", "after", "before", "between", "out",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "than", "too", "very", "just", "now", "not", "but",
    "off", "down", "then", "once", "here", "there", "our", "your", "their", "his",
    "her", "its", "you", "they", "i", "we", "my", "me", "us",
}


def _normalize_provision_anchor(raw: str) -> str:
    """Normalize raw statutory entity reference to canonical base provision."""
    cleaned = re.sub(r"[\s\-_]", "", raw.lower())
    # Strip subsection e.g. 148a(b) -> 148a, 149(1)(a) -> 149, 119(2)(b) -> 119(2)(b)
    # For reassessment 148a(b) -> 148a
    if cleaned.startswith("148a"):
        return "148a"
    if cleaned.startswith("149"):
        return "149"
    if cleaned.startswith("147"):
        return "147"
    if cleaned.startswith("151"):
        return "151"
    if cleaned.startswith("206aa"):
        return "206aa"
    if cleaned.startswith("114aaa"):
        return "114aaa"
    if cleaned.startswith("234h"):
        return "234h"
    if cleaned.startswith("139(9)") or cleaned.startswith("139"):
        return "139(9)"
    if cleaned.startswith("119(2)(b)") or cleaned.startswith("119"):
        return "119(2)(b)"
    return cleaned


def extract_statutory_anchors(text: str) -> set[str]:
    """Extract canonical statutory anchors (sections, rules, circulars) from query text."""
    if not text:
        return set()

    anchors = set()
    cleaned = text.lower()

    # 1. Section patterns: "section 148a(b)", "sec. 149", "section 206aa", "section 999xyz"
    sec_matches = re.findall(
        r"\b(?:section|sec\.?|u/s)\s*([0-9]+[a-z]*(?:\([a-z0-9]+\))*)",
        cleaned,
        flags=re.IGNORECASE,
    )
    for m in sec_matches:
        anchors.add(_normalize_provision_anchor(m))

    # 2. Rule patterns: "rule 114aaa"
    rule_matches = re.findall(
        r"\brule\s*([0-9]+[a-z]*(?:\([a-z0-9]+\))*)",
        cleaned,
        flags=re.IGNORECASE,
    )
    for m in rule_matches:
        anchors.add(_normalize_provision_anchor(m))

    # 3. Circular patterns: "circular 03/2023", "circular no. 3 of 2023"
    cir_matches = re.findall(
        r"\bcircular\s*(?:no\.?\s*)?([0-9]+(?:/[0-9]+)?)",
        cleaned,
        flags=re.IGNORECASE,
    )
    for m in cir_matches:
        anchors.add(_normalize_provision_anchor(m))

    # 4. Standalone statutory section tokens if present
    standalone_codes = [
        "148a(b)", "148a", "149", "147", "151",
        "206aa", "114aaa", "234h", "139(9)", "119(2)(b)",
    ]
    for code in standalone_codes:
        pattern = r"(?<![a-z0-9])" + re.escape(code) + r"(?![a-z0-9])"
        if re.search(pattern, cleaned):
            anchors.add(_normalize_provision_anchor(code))

    return anchors


def _build_chunk_text(doc: Any) -> str:
    """Extract comprehensive searchable string from a RagDocument or mock."""
    parts = []
    if hasattr(doc, "id") and isinstance(doc.id, str):
        parts.append(doc.id)
    if hasattr(doc, "title") and isinstance(doc.title, str):
        parts.append(doc.title)
    if hasattr(doc, "section") and isinstance(doc.section, str):
        parts.append(doc.section)
    if hasattr(doc, "text") and isinstance(doc.text, str):
        parts.append(doc.text)

    tags = getattr(doc, "tags", ()) or getattr(doc, "retrieval_tags", ()) or ()
    if isinstance(tags, (list, tuple, set)):
        parts.extend([str(t) for t in tags])

    sources = getattr(doc, "sources", ()) or ()
    if isinstance(sources, (list, tuple)):
        for s in sources:
            if hasattr(s, "title") and isinstance(s.title, str):
                parts.append(s.title)
            if hasattr(s, "section") and isinstance(s.section, str):
                parts.append(s.section)

    return " ".join(parts).lower()


def _is_anchor_in_chunk(anchor: str, chunk_blob: str) -> bool:
    """Verify if a normalized statutory anchor is supported in candidate chunk text."""
    if anchor == "148a":
        return bool(
            re.search(r"(?<![a-z0-9])148a\b", chunk_blob)
            or re.search(r"(?<![a-z0-9])148-a\b", chunk_blob)
            or "148a" in chunk_blob
        )
    if anchor in ("149", "147", "151"):
        return bool(re.search(r"(?<![a-z0-9])" + anchor + r"(?![a-z0-9])", chunk_blob))
    if anchor == "206aa":
        return "206aa" in chunk_blob or "206 aa" in chunk_blob
    if anchor == "114aaa":
        return "114aaa" in chunk_blob or "114 aaa" in chunk_blob
    if anchor == "234h":
        return "234h" in chunk_blob or "234 h" in chunk_blob
    if anchor == "139(9)":
        return "139(9)" in chunk_blob or "139 (9)" in chunk_blob or "139" in chunk_blob
    if anchor == "119(2)(b)":
        return "119(2)(b)" in chunk_blob or "119 (2)(b)" in chunk_blob or "119" in chunk_blob
    if anchor in ("03/2023", "3/2023"):
        return any(
            t in chunk_blob
            for t in ("03/2023", "3/2023", "circular 03", "circular no. 3", "circular no. 03")
        )
    # Generic regex boundary match for arbitrary statutory tokens (e.g. 999xyz)
    pattern = r"(?<![a-z0-9])" + re.escape(anchor) + r"(?![a-z0-9])"
    return bool(re.search(pattern, chunk_blob))


def compute_term_overlap(query: str, chunk_blob: str) -> float:
    """Compute lexical content word overlap ratio between query and chunk."""
    q_words = {
        w for w in re.findall(r"\b[a-z0-9_-]{3,}\b", query.lower())
        if w not in _CIVIC_STOPWORDS and not w.isdigit()
    }
    if not q_words:
        return 1.0

    chunk_words = set(re.findall(r"\b[a-z0-9_-]{3,}\b", chunk_blob.lower()))
    matches = len(q_words & chunk_words)
    target = max(len(q_words) * 0.30, 1.0)
    return min(matches / target, 1.0)


def compute_rag_confidence(
    rag_result: Any,
    query: str | None = None,
) -> float:
    """Compute a multi-factor normalized confidence score in [0.0, 1.0].

    Confidence = BaseScore × EntityAlignment × TermOverlap

    Args:
        rag_result: A RetrievalResult object (from backend.rag.retriever) or None.
        query: Optional user inquiry string to enforce statutory entity alignment
               and lexical overlap. If omitted, returns backward-compatible base score.

    Returns:
        Float in [0.0, 1.0]. Returns 0.0 if rag_result is None or has no hits.
        Penalizes confidence strictly below 0.35 if query statutory anchors lack support.
    """
    if rag_result is None:
        return 0.0

    hits = getattr(rag_result, "hits", None)
    if not hits:
        return 0.0

    top_score: float = 0.0
    try:
        top_score = float(hits[0].score)
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0.0

    if top_score <= 0.0:
        return 0.0

    base_confidence = min(top_score / _RRF_HIGH_CONFIDENCE_FLOOR, 1.0)

    # Backward compatibility: If query is omitted or empty, return base score
    if query is None or not str(query).strip():
        logger.debug("RAG confidence (unconditioned): top_score=%.4f → %.3f", top_score, base_confidence)
        return base_confidence

    doc = getattr(hits[0], "document", None)
    if doc is None:
        return base_confidence

    query_str = str(query).strip()
    chunk_blob = _build_chunk_text(doc)

    # 1. Statutory Entity Alignment
    statutory_anchors = extract_statutory_anchors(query_str)
    entity_alignment = 1.0
    matched_anchors: set[str] = set()

    if statutory_anchors:
        matched_anchors = {
            a for a in statutory_anchors
            if _is_anchor_in_chunk(a, chunk_blob)
        }
        if not matched_anchors:
            # Severe statutory mismatch penalty: ensures confidence < 0.35
            entity_alignment = 0.15
        else:
            entity_alignment = len(matched_anchors) / len(statutory_anchors)

    # 2. Lexical / Term Overlap
    term_overlap = compute_term_overlap(query_str, chunk_blob)

    # Multi-factor score
    confidence = base_confidence * entity_alignment * term_overlap

    # Hard ceiling for statutory mismatch: strictly below 0.35
    if statutory_anchors and not matched_anchors:
        confidence = min(confidence, 0.25)

    confidence = max(0.0, min(confidence, 1.0))
    logger.debug(
        "RAG confidence: base=%.3f, entity_align=%.2f, term_overlap=%.2f → final=%.3f",
        base_confidence, entity_alignment, term_overlap, confidence,
    )
    return confidence


__all__ = ["compute_rag_confidence", "extract_statutory_anchors", "compute_term_overlap"]
