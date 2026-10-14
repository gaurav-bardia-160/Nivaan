"""Read-only retrieval baseline. Not wired into live answers yet."""
from __future__ import annotations

from dataclasses import dataclass

from backend.rag.bm25 import BM25Index, tokenize
from backend.rag.loader import load_corpus
from backend.rag.models import LoadResult, RagDocument, RetrievalHit, RetrievalResult


@dataclass(frozen=True)
class RetrieverConfig:
    lexical_top_k: int = 30
    final_top_k: int = 8
    rrf_k: int = 60

    def __post_init__(self):
        if self.lexical_top_k < 1 or self.final_top_k < 1 or self.rrf_k < 1:
            raise ValueError("retriever config values must be positive")


def _document_text(doc: RagDocument) -> str:
    title_bits = " ".join(f"{source.title} {source.section}" for source in doc.sources)
    return f"{doc.category} {' '.join(doc.tags)} {title_bits} {doc.text}"


class RagRetriever:
    def __init__(self, load_result: LoadResult | None = None, *, config: RetrieverConfig | None = None):
        self.load_result = load_result or load_corpus()
        self.config = config or RetrieverConfig()
        self.documents = self.load_result.documents
        self.index = BM25Index(_document_text(document) for document in self.documents)

    def search(self, query: str, *, category: str | None = None, top_k: int | None = None) -> RetrievalResult:
        clean_query = " ".join((query or "").split())
        if not clean_query:
            return RetrievalResult(query=clean_query, hits=(), status="empty_query", searched_documents=0)
        allowed = None
        if category:
            allowed = {idx for idx, doc in enumerate(self.documents) if doc.category == category}
        hits = self.index.search(clean_query, top_k=self.config.lexical_top_k, allowed_indices=allowed)
        fused = []
        q_terms = set(tokenize(clean_query))
        for rank, hit in enumerate(hits, 1):
            doc = self.documents[hit.index]
            tags = set(doc.tags)
            metadata_overlap = len(q_terms & tags) / max(len(q_terms), 1)
            # RRF keeps rank stable and avoids presenting BM25 score as probability.
            score = 1 / (self.config.rrf_k + rank) + min(metadata_overlap, 1.0) * 0.01
            fused.append(RetrievalHit(
                document=doc,
                score=score,
                rank=rank,
                signals={"bm25_score": hit.score, "rrf": 1 / (self.config.rrf_k + rank), "tag_overlap": metadata_overlap},
            ))
        fused.sort(key=lambda result: (-result.score, result.rank, result.document.id))
        final = tuple(fused[:top_k or self.config.final_top_k])
        return RetrievalResult(
            query=clean_query,
            hits=final,
            status="supported" if final else "insufficient",
            searched_documents=len(allowed) if allowed is not None else len(self.documents),
        )


def search(query: str, *, category: str | None = None, top_k: int = 8) -> RetrievalResult:
    return RagRetriever().search(query, category=category, top_k=top_k)
