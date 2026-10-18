from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.rag.loader import load_corpus
from backend.rag.retriever import RagRetriever
from backend.rag.bm25 import tokenize
from backend.rag.embeddings import DisabledEmbeddingProvider, EmbeddingsUnavailable
from backend.rag.runtime import expand_retrieval_query
from backend.rag.vector_store import DisabledVectorStore, QdrantLocalVectorStore, VectorHit, VectorStoreUnavailable


def test_tokenizer_preserves_civic_exact_terms():
    tokens = tokenize("How to download e-PAN, Aadhaar VID and Form 49A?")
    assert "pan" in tokens
    assert "aadhaar" in tokens
    assert "vid" in tokens
    assert "49a" in tokens


def test_disabled_provider_contracts_are_explicit():
    embeddings = DisabledEmbeddingProvider()
    assert embeddings.info.provider == "disabled"
    try:
        embeddings.embed_texts(("hello",))
    except EmbeddingsUnavailable as exc:
        assert str(exc) == "embedding_provider_not_configured"
    else:
        raise AssertionError("disabled embeddings must not silently return vectors")

    store = DisabledVectorStore()
    assert store.health() == {"provider": "disabled", "ready": False}
    try:
        store.search((0.1,), top_k=1)
    except VectorStoreUnavailable as exc:
        assert str(exc) == "vector_store_not_configured"
    else:
        raise AssertionError("disabled vector store must not silently search")


def test_lexical_retriever_handles_empty_and_category_filter():
    retriever = RagRetriever(load_corpus())
    empty = retriever.search("   ")
    assert empty.status == "empty_query"
    assert empty.hits == ()

    pan = retriever.search("download e-PAN card", category="pan", top_k=3)
    assert pan.status == "supported_lexical"
    assert pan.searched_documents == 242
    assert pan.hits
    assert all(hit.document.category == "pan" for hit in pan.hits)
    assert "pan" in (pan.hits[0].document.text + " " + " ".join(pan.hits[0].document.tags)).lower()


def test_lexical_eval_questions_hit_expected_category_and_terms():
    retriever = RagRetriever(load_corpus())
    questions = json.loads(Path("tests/fixtures/rag_eval_questions.json").read_text(encoding="utf-8"))
    failures = []
    for case in questions:
        result = retriever.search(case["question"], category=case["category"], top_k=5)
        joined = "\n".join(hit.document.text for hit in result.hits).lower()
        if not result.hits or any(term.lower() not in joined for term in case["must_match"]):
            failures.append({"question": case["question"], "status": result.status, "hits": [h.document.id for h in result.hits]})
        assert all(hit.document.category == case["category"] for hit in result.hits)
    assert failures == []


def test_multilingual_address_queries_expand_to_canonical_retrieval_terms():
    hindi = expand_retrieval_query("आधार कार्ड में पता कैसे बदलें?")
    gujarati = expand_retrieval_query("આધાર કાર્ડમાં સરનામું કેવી રીતે બદલવું?")
    unrelated = expand_retrieval_query("आधार कार्ड डाउनलोड करें")

    assert hindi.endswith("online address update process demographic details")
    assert gujarati.endswith("online address update process demographic details")
    assert unrelated == "आधार कार्ड डाउनलोड करें"


def test_expanded_hindi_address_query_retrieves_address_update_material():
    retriever = RagRetriever(load_corpus())
    query = expand_retrieval_query("आधार कार्ड में पता कैसे बदलें?")
    result = retriever.search(query, category="aadhaar", top_k=3)
    evidence = " ".join(
        f"{source.title} {source.section} {hit.document.text}"
        for hit in result.hits
        for source in hit.document.sources[:1]
    ).lower()

    assert result.hits
    assert "address update" in evidence


class _FakeEmbeddingProvider:
    def embed_texts(self, texts):
        return tuple((1.0, 0.0, 0.0) for _ in texts)


class _FakeVectorStore:
    def __init__(self, document_id):
        self.document_id = document_id

    def search(self, query_vector, *, top_k, category=None):
        return (VectorHit(document_id=self.document_id, score=0.95),)

    def health(self):
        return {"provider": "fake", "ready": True}


def test_hybrid_retriever_fuses_vector_and_lexical_signals():
    loaded = load_corpus()
    target = next(document for document in loaded.documents if document.category == "aadhaar")
    retriever = RagRetriever(
        loaded,
        embedding_provider=_FakeEmbeddingProvider(),
        vector_store=_FakeVectorStore(target.id),
    )

    result = retriever.search("zzzxxyy qqqvvv", top_k=3)
    assert result.status == "supported_hybrid"
    assert result.hits[0].document.id == target.id
    assert result.hits[0].signals["vector_score"] == 0.95


def test_qdrant_local_store_persists_and_filters_canonical_documents(tmp_path):
    pytest.importorskip("qdrant_client")
    documents = load_corpus().documents[:3]
    vectors = ((1.0, 0.0), (0.0, 1.0), (0.5, 0.5))
    store = QdrantLocalVectorStore(tmp_path / "qdrant", collection="test_chunks")
    store.rebuild(documents, vectors)

    assert store.health()["points"] == 3
    hits = store.search(vectors[0], top_k=1, category=documents[0].category)
    assert hits
    assert hits[0].document_id == documents[0].id
