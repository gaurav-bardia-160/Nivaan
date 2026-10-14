from __future__ import annotations

import json
from pathlib import Path

from backend.rag.loader import load_corpus
from backend.rag.retriever import RagRetriever
from backend.rag.bm25 import tokenize
from backend.rag.embeddings import DisabledEmbeddingProvider, EmbeddingsUnavailable
from backend.rag.vector_store import DisabledVectorStore, VectorStoreUnavailable


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
    assert pan.status == "supported"
    assert pan.searched_documents == 269
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
