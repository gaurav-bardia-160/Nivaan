"""Feature-flagged runtime access to the canonical RAG corpus."""
from __future__ import annotations

import os
import re
from functools import lru_cache

from backend.config import DATA_DIR
from backend.rag.embeddings import FastEmbedProvider
from backend.rag.models import RetrievalResult
from backend.rag.retriever import RagRetriever
from backend.rag.vector_store import QdrantLocalVectorStore

_TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_VECTOR_PATH = DATA_DIR / "vector_index" / "qdrant"
_CATEGORY_TERMS = {
    "pan": ("pan", "e-pan", "epan", "form 49a", "form 49aa", "पैन", "पॅन", "પૅન"),
    "aadhaar": ("aadhaar", "aadhar", "uidai", "e-aadhaar", "eaadhaar", "आधार", "આધાર"),
    "civic": (
        "passport", "efrro", "frro", "visa", "voter", "voters", "parivahan",
        "driving license", "driving licence", "driver license", "driver licence", "dl", "rc",
        "ration", "pds", "nfsa", "post office", "ippb", "epf", "epfo",
        "pension", "bhavishya", "pmkisan", "pm-kisan", "kisan", "rti", "pgportal",
        "grievance", "sebi", "rbi", "budget", "gazette", "judiciary", "court",
        "digilocker", "udyam", "msme", "gst", "constitution", "marriage", "ews"
    ),
}
_MULTILINGUAL_QUERY_HINTS = (
    (("आधार",), ("पता", "पते"), ("बदल", "अपडेट"), "online address update process demographic details"),
    (("આધાર",), ("સરનામ",), ("બદલ", "અપડેટ"), "online address update process demographic details"),
)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUE_VALUES


def rag_enabled() -> bool:
    return _enabled("RAG_ENABLED")


def vector_enabled() -> bool:
    return _enabled("RAG_VECTOR_ENABLED")


@lru_cache(maxsize=2)
def _get_retriever(use_vectors: bool) -> RagRetriever:
    lexical_retriever = RagRetriever()
    if not use_vectors:
        return lexical_retriever
    try:
        store = QdrantLocalVectorStore(DEFAULT_VECTOR_PATH)
        health = store.health()
        if not health.get("ready") or health.get("points") != len(lexical_retriever.documents):
            store.close()
            return lexical_retriever
        return RagRetriever(
            load_result=lexical_retriever.load_result,
            embedding_provider=FastEmbedProvider(),
            vector_store=store,
        )
    except (OSError, RuntimeError, ValueError):
        # Local Qdrant uses an exclusive file lock and can also become stale after
        # corpus updates. Lexical retrieval remains a safe, deterministic fallback.
        return lexical_retriever


def get_retriever() -> RagRetriever:
    """Build and cache the configured read-only retriever once per mode."""
    return _get_retriever(vector_enabled())


def supported_category(query: str) -> str | None:
    lowered = query.lower()
    for category, terms in _CATEGORY_TERMS.items():
        if any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered) for term in terms):
            return category
    return None


def expand_retrieval_query(query: str) -> str:
    """Append narrow English retrieval hints for supported Hindi/Gujarati civic intents."""
    normalized = " ".join((query or "").split())
    for identity_terms, subject_terms, action_terms, hint in _MULTILINGUAL_QUERY_HINTS:
        if (
            any(term in normalized for term in identity_terms)
            and any(term in normalized for term in subject_terms)
            and any(term in normalized for term in action_terms)
        ):
            return f"{normalized} {hint}"
    return normalized


def retrieve_if_enabled(query: str, *, top_k: int = 3) -> RetrievalResult | None:
    if not rag_enabled():
        return None
    category = supported_category(query)
    if category is None:
        return None
    expanded_query = expand_retrieval_query(query)
    return get_retriever().search(expanded_query, category=category, top_k=top_k)


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


__all__ = [
    "expand_retrieval_query",
    "get_retriever",
    "rag_enabled",
    "rag_health",
    "retrieve_if_enabled",
    "supported_category",
    "vector_enabled",
]
