"""Hybrid lexical and vector retrieval over the canonical corpus."""
from __future__ import annotations

from dataclasses import dataclass

from backend.rag.bm25 import BM25Index, tokenize
from backend.rag.embeddings import EmbeddingProvider
from backend.rag.loader import load_corpus
from backend.rag.models import LoadResult, RagDocument, RetrievalHit, RetrievalResult
from backend.rag.vector_store import VectorStore


@dataclass(frozen=True)
class RetrieverConfig:
    lexical_top_k: int = 30
    vector_top_k: int = 30
    final_top_k: int = 8
    rrf_k: int = 60

    def __post_init__(self):
        if min(self.lexical_top_k, self.vector_top_k, self.final_top_k, self.rrf_k) < 1:
            raise ValueError("retriever config values must be positive")


def document_text(doc: RagDocument) -> str:
    title_bits = " ".join(f"{source.title} {source.section}" for source in doc.sources)
    return f"{doc.category} {' '.join(doc.tags)} {title_bits} {doc.text}"


class RagRetriever:
    def __init__(
        self,
        load_result: LoadResult | None = None,
        *,
        config: RetrieverConfig | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ):
        if (embedding_provider is None) != (vector_store is None):
            raise ValueError("embedding_provider and vector_store must be configured together")
        self.load_result = load_result or load_corpus()
        self.config = config or RetrieverConfig()
        self.documents = self.load_result.documents
        self.documents_by_id = {document.id: document for document in self.documents}
        self.index = BM25Index(document_text(document) for document in self.documents)
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def search(self, query: str, *, category: str | None = None, top_k: int | None = None) -> RetrievalResult:
        clean_query = " ".join((query or "").split())
        requested_top_k = self.config.final_top_k if top_k is None else top_k
        if requested_top_k < 1:
            raise ValueError("top_k must be positive")
        if not clean_query:
            return RetrievalResult(query=clean_query, hits=(), status="empty_query", searched_documents=0)

        allowed = None
        if category:
            allowed = {
                idx for idx, doc in enumerate(self.documents)
                if doc.category == category
            }

        lexical_hits = self.index.search(clean_query, top_k=self.config.lexical_top_k, allowed_indices=allowed)
        candidates: dict[str, dict[str, float]] = {}
        lexical_ranks: dict[str, int] = {}
        q_terms = set(tokenize(clean_query))
        for rank, hit in enumerate(lexical_hits, 1):
            document = self.documents[hit.index]
            lexical_ranks[document.id] = rank
            signals = candidates.setdefault(document.id, {})
            signals["bm25_score"] = hit.score
            signals["lexical_rrf"] = 1 / (self.config.rrf_k + rank)

        if self.embedding_provider is not None and self.vector_store is not None:
            query_vector = self.embedding_provider.embed_texts((clean_query,))[0]
            for rank, hit in enumerate(
                self.vector_store.search(query_vector, top_k=self.config.vector_top_k, category=category),
                1,
            ):
                if hit.document_id not in self.documents_by_id:
                    continue
                signals = candidates.setdefault(hit.document_id, {})
                signals["vector_score"] = hit.score
                signals["vector_rrf"] = 1 / (self.config.rrf_k + rank)

        _TROUBLE_TOKENS = {
            "failed", "fail", "failure", "fails", "stuck", "pending", "rejected", "rejection", "error",
            "cancelled", "cancel", "mismatch", "refund", "reissue", "delay", "delayed", "delays",
            "issue", "problem", "dispute", "ombudsman", "grievance", "escalate", "escalation",
            "deducted", "deduct", "debited", "debit", "srn", "arn", "adverse", "reversal",
            "exhausted", "limit", "crossed", "unpaid", "unvalidated", "correction", "defective",
            "tat", "overdue", "exceeded", "atki", "atke", "radd", "shikayat", "kat", "kata", "kaat",
            "unsolicited", "foreclosure", "prepayment", "cibil", "experian", "crif",
            "cheque", "passbook", "fvr", "blo", "aero", "ero",
            "nalsa", "edaakhil", "dcdrc", "scdrc", "ncdrc", "mbu",
            "condonation", "330",
        }
        is_trouble_query = bool(q_terms & _TROUBLE_TOKENS)

        fused: list[RetrievalHit] = []
        for document_id, signals in candidates.items():
            document = self.documents_by_id[document_id]
            doc_tags = set(document.tags)
            metadata_overlap = len(q_terms & doc_tags) / max(len(q_terms), 1)
            signals["tag_overlap"] = metadata_overlap
            score = signals.get("lexical_rrf", 0.0) + signals.get("vector_rrf", 0.0) + min(metadata_overlap, 1.0) * 0.01

            # Exact statutory & error code boost: ensures statutory sections & error codes surface to rank 1
            lowered_doc = (document.text + " " + " ".join(document.tags)).lower()
            _EXACT_CODES = ("330", "119(2)(b)", "119", "139(9)", "139", "44ad", "44ada", "44ae", "234f", "form 16", "26as", "ais", "tis", "form 19", "form 10c", "form 49a", "joint declaration", "edaakhil", "cibil")
            for code in _EXACT_CODES:
                if code in clean_query.lower() and code in lowered_doc:
                    score += 0.08
                    signals["exact_statutory_boost"] = 0.08
                    break

            # Troubleshooting boost: prioritize authoritative SOP & escalation guidelines when user reports a failure
            # Strictly scoped to the query's matching domain category to prevent cross-domain leakage
            if is_trouble_query and (category is None or document.category == category) and any(tag in doc_tags for tag in ("troubleshooting", "escalation", "sop", "manual")):
                score += 0.05
                signals["troubleshooting_boost"] = 0.05

            fused.append(
                RetrievalHit(
                    document=document,
                    score=score,
                    rank=lexical_ranks.get(document_id, self.config.vector_top_k + 1),
                    signals=signals,
                )
            )

        fused.sort(key=lambda result: (-result.score, result.rank, result.document.id))
        final = tuple(fused[:requested_top_k])
        mode = "hybrid" if self.embedding_provider is not None else "lexical"
        return RetrievalResult(
            query=clean_query,
            hits=final,
            status=f"supported_{mode}" if final else "insufficient",
            searched_documents=len(allowed) if allowed is not None else len(self.documents),
        )


def search(query: str, *, category: str | None = None, top_k: int = 8) -> RetrievalResult:
    return RagRetriever().search(query, category=category, top_k=top_k)


__all__ = ["RagRetriever", "RetrieverConfig", "document_text", "search"]
