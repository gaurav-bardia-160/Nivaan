"""Confidence scoring — maps raw RRF retrieval scores to a normalized [0.0, 1.0] confidence value.

The confidence gate in pipeline.py uses this to decide whether to use the Qdrant result
or fall back to web search.

RRF (Reciprocal Rank Fusion) scores are small floats (typically 0.005–0.065).
Empirical calibration from Nivaan's RAG corpus (1,353 chunks):
  - High confidence hits: top_score ≥ 0.040  → normalized ≈ 1.0
  - Medium confidence:    top_score ≈ 0.020  → normalized ≈ 0.50
  - Low confidence:       top_score < 0.010  → normalized < 0.25
  - Already gated by MIN_RRF_CONFIDENCE_THRESHOLD = 0.010 in pipeline.py
"""
from __future__ import annotations

import logging

logger = logging.getLogger("web_search.confidence")

# Empirically determined RRF score at which we consider retrieval "high confidence"
_RRF_HIGH_CONFIDENCE_FLOOR = 0.040


def compute_rag_confidence(rag_result) -> float:
    """Compute a normalized confidence score from a RAG retrieval result.

    Args:
        rag_result: A RetrievalResult object (from backend.rag.retriever) or None.

    Returns:
        Float in [0.0, 1.0]. Returns 0.0 if rag_result is None or has no hits.
        Returns 1.0 if the top hit score equals or exceeds _RRF_HIGH_CONFIDENCE_FLOOR.
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

    # Linear normalization: score / floor, clamped to [0.0, 1.0]
    normalized = min(top_score / _RRF_HIGH_CONFIDENCE_FLOOR, 1.0)
    logger.debug("RAG confidence: top_score=%.4f → normalized=%.3f", top_score, normalized)
    return normalized


__all__ = ["compute_rag_confidence"]
