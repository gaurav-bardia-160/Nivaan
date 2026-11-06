"""Empirical Adversarial Challenge Suite for Milestone 3 Iteration 2.

Executed by challenger_m3_iter2_1 to empirically verify:
1. Candidate deduplication across hybrid lexical + vector search over 25+ varied queries.
2. Dual-intent comparison query handling (no mutual exclusion penalties, both surface in top hits).
3. Boundary queries A through E precision and discrimination in hybrid and lexical modes.
4. Python data model invariant adherence for DocumentId and candidate keying.
"""
from __future__ import annotations

import pytest
from backend.config import DATA_DIR
from backend.rag.embeddings import FastEmbedProvider
from backend.rag.retriever import DocumentId, RagRetriever
from backend.rag.vector_store import QdrantLocalVectorStore


@pytest.fixture(scope="module")
def hybrid_retriever():
    provider = FastEmbedProvider()
    store = QdrantLocalVectorStore(path=DATA_DIR / "vector_index" / "qdrant")
    retriever = RagRetriever(embedding_provider=provider, vector_store=store)
    yield retriever
    try:
        store._client.close()
    except Exception:
        pass


@pytest.fixture(scope="module")
def lexical_retriever():
    return RagRetriever()


class TestAdversarialDeduplication:
    """Stress-test hybrid search candidate deduplication across diverse queries."""

    STRESS_QUERIES = [
        # Queries matching both lexical and vector heavily
        "defective return 139(9)",
        "How to submit condonation of delay request under Section 119(2)(b) for late ITR verification?",
        "AIS feedback for duplicate dividend transaction",
        "bank account pre-validation failed for income tax refund reissue",
        "Form 8 voter address correction application BLO verification",
        "unsolicited credit card charges RBI integrated ombudsman complaint",
        "consumer court pecuniary jurisdiction district commission edaakhil",
        "free legal aid eligibility criteria section 12 nalsa",
        "Aadhaar PVC card payment deducted but SRN not generated auto-reversal TAT",
        "Aadhaar name update cross limit exception handling gazette notification",
        # Generic & single-token queries
        "refund",
        "tat",
        "error",
        "mismatch",
        "status",
        "reissue",
        "stuck",
        "failed",
        # Multilingual / Hinglish
        "AIS me duplicate transaction kaise hataye feedback portal par",
        "139(9) defective return notice ka reply e-proceedings me kaise kare",
        "bank account validate nahi ho raha refund atka hai",
        # Boundary & edge queries
        "Received Section 139(9) defective return notice because AIS income differed from ITR",
        "Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report",
        "What is the difference between Section 139(9) defective return notice and AIS feedback?",
        "Should I respond to 139(9) defect memo or submit AIS feedback for wrong dividend?",
        "139(9) vs AIS feedback",
    ]

    @pytest.mark.parametrize("query", STRESS_QUERIES)
    def test_no_duplicate_hits_in_hybrid_search(self, hybrid_retriever, query):
        """Verify that hybrid search never returns duplicate document IDs or instances."""
        res = hybrid_retriever.search(query, top_k=20)
        hit_ids = [h.document.id for h in res.hits]
        hit_ptrs = [id(h.document) for h in res.hits]

        assert len(hit_ids) == len(set(hit_ids)), (
            f"Query '{query}' produced duplicate hit document IDs: {hit_ids}"
        )
        assert len(hit_ptrs) == len(set(hit_ptrs)), (
            f"Query '{query}' produced duplicate document object references: {hit_ptrs}"
        )

    def test_rrf_fusion_combines_vector_and_lexical_signals(self, hybrid_retriever):
        """Verify that when a document matches both lexical and vector, signals are unified."""
        query = "defective return 139(9)"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_defective_return_manual_01"
        signals = top_hit.signals
        assert "lexical_rrf" in signals, f"Expected lexical_rrf in signals, got {signals.keys()}"
        assert "vector_rrf" in signals, f"Expected vector_rrf in signals, got {signals.keys()}"
        assert "bm25_score" in signals, f"Expected bm25_score in signals, got {signals.keys()}"
        assert "vector_score" in signals, f"Expected vector_score in signals, got {signals.keys()}"


class TestDualIntentComparisonQueries:
    """Stress-test dual-intent queries asking to compare or choose between 139(9) and AIS."""

    COMPARISON_QUERIES = [
        "What is the difference between Section 139(9) defective return notice and AIS feedback?",
        "Difference between 139(9) defective return notice and AIS feedback",
        "Should I respond to 139(9) defect memo or submit AIS feedback for wrong dividend?",
        "Compare CPC 2.0 defective return rectification vs AIS feedback on SFT report",
        "139(9) defective return or AIS feedback which one to file?",
    ]

    @pytest.mark.parametrize("query", COMPARISON_QUERIES)
    def test_both_sub_procedures_surface_without_penalties(self, hybrid_retriever, query):
        """Verify comparison queries retain both sub-procedures in top results without mutual penalties."""
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        top_doc_ids = [h.document.id for h in res.hits[:4]]

        assert "itr_ais_feedback_manual_01" in top_doc_ids, (
            f"itr_ais_feedback_manual_01 missing from top 4 hits for '{query}': {top_doc_ids}"
        )
        assert "itr_defective_return_manual_01" in top_doc_ids, (
            f"itr_defective_return_manual_01 missing from top 4 hits for '{query}': {top_doc_ids}"
        )

        for h in res.hits:
            if h.document.id in ("itr_ais_feedback_manual_01", "itr_defective_return_manual_01"):
                assert "sub_procedure_mismatch_penalty" not in h.signals, (
                    f"Hit {h.document.id} incorrectly received sub_procedure_mismatch_penalty: {h.signals}"
                )
                assert h.score > 0.01, f"Hit {h.document.id} score should be positive, got {h.score}"

    @pytest.mark.parametrize("query", COMPARISON_QUERIES)
    def test_both_sub_procedures_surface_in_lexical_mode(self, lexical_retriever, query):
        """Verify comparison queries retain both sub-procedures in top 4 in lexical mode."""
        res = lexical_retriever.search(query, category="tax", top_k=5)
        top_doc_ids = [h.document.id for h in res.hits[:4]]

        assert "itr_ais_feedback_manual_01" in top_doc_ids, (
            f"itr_ais_feedback_manual_01 missing from top 4 hits in lexical mode for '{query}': {top_doc_ids}"
        )
        assert "itr_defective_return_manual_01" in top_doc_ids, (
            f"itr_defective_return_manual_01 missing from top 4 hits in lexical mode for '{query}': {top_doc_ids}"
        )


class TestBoundaryQueriesPrecision:
    """Verify precision on the official boundary queries A through E in hybrid mode."""

    def test_boundary_query_a_hybrid(self, hybrid_retriever):
        query = "Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        top_3_ids = [h.document.id for h in res.hits[:3]]
        assert "itr_defective_return_manual_01" not in top_3_ids

    def test_boundary_query_b_hybrid(self, hybrid_retriever):
        query = "Received Section 139(9) defective return notice because AIS income differed from ITR"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_defective_return_manual_01"
        ais_hit = next((h for h in res.hits if h.document.id == "itr_ais_feedback_manual_01"), None)
        if ais_hit:
            assert ais_hit.signals.get("sub_procedure_mismatch_penalty") == -0.40
            assert ais_hit.score < 0.0

    def test_boundary_query_c_hybrid(self, hybrid_retriever):
        query = "How to correct duplicate interest in Annual Information Statement?"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        top_5_ids = [h.document.id for h in res.hits[:5]]
        assert "itr_defective_return_manual_01" not in top_5_ids

    def test_boundary_query_d_hybrid(self, hybrid_retriever):
        query = "How to respond to e-proceedings 15-day defect memo for defective return?"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_defective_return_manual_01"
        top_5_ids = [h.document.id for h in res.hits[:5]]
        assert "itr_ais_feedback_manual_01" not in top_5_ids

    def test_boundary_query_e_hybrid(self, hybrid_retriever):
        query = "My AIS has wrong dividend transaction what should I do"
        res = hybrid_retriever.search(query, category="tax", top_k=3)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        top_3_ids = [h.document.id for h in res.hits]
        assert "itr_defective_return_manual_01" not in top_3_ids


class TestDocumentIdDataModelInvariant:
    """Verify that DocumentId maintains Python data model invariants."""

    def test_document_id_string_equality_and_hash(self):
        d1 = DocumentId("itr_ais_feedback_manual_01", ["itr_ais_feedback_manual_01", "rag_123"])
        d2 = DocumentId("itr_ais_feedback_manual_01")
        s = "itr_ais_feedback_manual_01"

        assert d1 == d2
        assert d1 == s
        assert hash(d1) == hash(d2)
        assert hash(d1) == hash(s)

        # Invariant: a == b implies hash(a) == hash(b)
        assert hash(d1) == hash(s)

        # Test set membership
        hash_set = {d1}
        assert s in hash_set
        assert d2 in hash_set

        # Test dict lookup
        lookup = {d1: "found"}
        assert lookup[s] == "found"
        assert lookup[d2] == "found"

    def test_document_id_does_not_falsely_equate_to_aliases(self):
        """Verify that DocumentId does not break hash invariant by equating to non-identical strings."""
        d = DocumentId("itr_ais_feedback_manual_01", ["itr_ais_feedback_manual_01", "rag_alias_456"])
        # d must NOT be == to an alias that has a different string value!
        assert (d == "rag_alias_456") is False
        assert "rag_alias_456" in d._aliases
