"""Feature-flagged runtime access to the canonical RAG corpus."""
from __future__ import annotations

import os
from functools import lru_cache

from backend.config import DATA_DIR
from backend.rag.embeddings import FastEmbedProvider
from backend.rag.models import RetrievalResult
from backend.rag.retriever import RagRetriever
from backend.rag.vector_store import QdrantLocalVectorStore

_TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_VECTOR_PATH = DATA_DIR / "vector_index" / "qdrant"


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUE_VALUES


def rag_enabled() -> bool:
    return _enabled("RAG_ENABLED")


def vector_enabled() -> bool:
    return _enabled("RAG_VECTOR_ENABLED")


@lru_cache(maxsize=2)
def _get_retriever(use_vectors: bool) -> RagRetriever:
    if not use_vectors:
        return RagRetriever()
    store = QdrantLocalVectorStore(DEFAULT_VECTOR_PATH)
    if not store.health()["ready"]:
        return RagRetriever()
    return RagRetriever(embedding_provider=FastEmbedProvider(), vector_store=store)


def get_retriever() -> RagRetriever:
    """Build and cache the configured read-only retriever once per mode."""
    return _get_retriever(vector_enabled())


def retrieve_if_enabled(query: str, *, top_k: int = 3) -> RetrievalResult | None:
    if not rag_enabled():
        return None
    return get_retriever().search(query, top_k=top_k)


def rag_health() -> dict[str, object]:
    if not rag_enabled():
        return {"enabled": False, "ready": False, "mode": "legacy_only", "vector_requested": vector_enabled()}
    retriever = get_retriever()
    report = retriever.load_result.report
    using_vectors = retriever.embedding_provider is not None
    vector_health = retriever.vector_store.health() if retriever.vector_store is not None else {"ready": False}
    return {
        "enabled": True,
        "ready": report.complete and bool(retriever.documents),
        "mode": "hybrid" if using_vectors else "lexical_candidate_corpus",
        "vector_requested": vector_enabled(),
        "vector_store": vector_health,
        "documents": len(retriever.documents),
        "factual_verification": report.factual_verification,
        "corpus_sha256": report.corpus_sha256,
    }


__all__ = ["get_retriever", "rag_enabled", "rag_health", "retrieve_if_enabled", "vector_enabled"]
