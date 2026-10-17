"""Feature-flagged runtime access to the canonical RAG corpus."""
from __future__ import annotations

import os
from functools import lru_cache

from backend.rag.models import RetrievalResult
from backend.rag.retriever import RagRetriever

_TRUE_VALUES = {"1", "true", "yes", "on"}


def rag_enabled() -> bool:
    """Return whether candidate-corpus retrieval is enabled for live requests."""
    return os.getenv("RAG_ENABLED", "false").strip().lower() in _TRUE_VALUES


@lru_cache(maxsize=1)
def get_retriever() -> RagRetriever:
    """Build the read-only canonical index once per process."""
    return RagRetriever()


def retrieve_if_enabled(query: str, *, top_k: int = 3) -> RetrievalResult | None:
    if not rag_enabled():
        return None
    return get_retriever().search(query, top_k=top_k)


def rag_health() -> dict[str, object]:
    if not rag_enabled():
        return {"enabled": False, "ready": False, "mode": "legacy_only"}
    retriever = get_retriever()
    report = retriever.load_result.report
    return {
        "enabled": True,
        "ready": report.complete and bool(retriever.documents),
        "mode": "lexical_candidate_corpus",
        "documents": len(retriever.documents),
        "factual_verification": report.factual_verification,
        "corpus_sha256": report.corpus_sha256,
    }


__all__ = ["get_retriever", "rag_enabled", "rag_health", "retrieve_if_enabled"]
