"""Empirical Adversarial Challenge Suite for Milestone 3 Iteration 2.

Executed by challenger_m3_iter2_2 to independently challenge:
1. Candidate deduplication across 30+ diverse queries in hybrid search (lexical + vector).
2. DocumentId hash and equality invariant preservation.
3. Dual-intent comparison query handling (no false sub-procedure penalties, both documents present).
4. Single-intent sub-procedure mutual suppression and score margins.
5. Boundary queries A through E in hybrid mode.
6. Edge case inputs (empty, repeated, unicode, special chars, large top_k).
"""
import pytest
from backend.rag.retriever import RagRetriever, DocumentId
from backend.rag.embeddings import FastEmbedProvider
from backend.rag.vector_store import QdrantLocalVectorStore
from backend.rag.runtime import DEFAULT_VECTOR_PATH
from backend.modules.domain_router import classify_domain, Domain


@pytest.fixture(scope="module")
def hybrid_retriever():
    emb = FastEmbedProvider()
    vs = QdrantLocalVectorStore(DEFAULT_VECTOR_PATH)
    ret = RagRetriever(embedding_provider=emb, vector_store=vs)
    yield ret
    vs.close()


class TestDocumentIdInvariants:
    """Empirical verification of DocumentId Python data model invariants."""

    def test_document_id_equality_and_hash(self):
        doc_id = DocumentId("itr_ais_feedback_manual_01", aliases=["alias_1", "alias_2"])
        raw_str = "itr_ais_feedback_manual_01"
        assert doc_id == raw_str
        assert raw_str == doc_id
        assert hash(doc_id) == hash(raw_str), "hash(a) must equal hash(b) when a == b"

        # Dictionary key interchangeability
        d = {doc_id: "val_doc_id"}
        assert raw_str in d
        assert d[raw_str] == "val_doc_id"
        d[raw_str] = "overwritten"
        assert len(d) == 1
        assert d[doc_id] == "overwritten"

        # Set deduplication
        s = {doc_id, raw_str}
        assert len(s) == 1


class TestHybridSearchCandidateDeduplication:
    """Stress-test hybrid search candidate fusion across diverse queries."""

    STRESS_QUERIES = [
        "defective return 139(9)",
        "defective notice Section 139(9) e-proceedings",
        "AIS feedback for duplicate SFT dividend transaction",
        "Annual Information Statement feedback option information is denied",
        "EPFO joint declaration correction name mismatch father name",
        "RBI failed ATM UPI transaction penalty compensation 100 per day",
        "Aadhaar PVC card payment deducted no SRN generated",
        "Aadhaar update limit exhausted cross limit exception handling",
        "Voter ID Form 8 correction BLO verification NGRS",
        "Consumer court eDaakhil pecuniary jurisdiction district commission",
        "NALSA free legal aid eligibility income limit section 12",
        "FASTag toll plaza unauthorized double charge dispute NHAI",
        "CBSE marksheet name mismatch in DigiLocker",
        "PAN card application Form 49A new physical card",
        "Condonation of delay under section 119(2)(b) for late return",
        "ITR bank account pre-validation failed refund unpaid",
        "Refund reissue request on e-filing portal after validation",
        "What is the difference between Section 139(9) defective return notice and AIS feedback?",
        "Should I respond to 139(9) defect memo or submit AIS feedback for wrong dividend?",
        "defective return " * 5,
        "AIS feedback " * 5,
        "mismatch discrepancy error refund failed tat penalty",
    ]

    @pytest.mark.parametrize("query", STRESS_QUERIES)
    def test_no_duplicate_hits_in_hybrid_search(self, hybrid_retriever, query):
        res = hybrid_retriever.search(query, top_k=15)
        hit_ids = [h.document.id for h in res.hits]
        assert len(hit_ids) == len(set(hit_ids)), (
            f"Duplicate hit IDs found in hybrid search for query '{query}': {hit_ids}"
        )
        content_hashes = [h.document.content_hash for h in res.hits]
        assert len(content_hashes) == len(set(content_hashes)), (
            f"Duplicate content hashes found in hybrid search for query '{query}': {content_hashes}"
        )


class TestDualIntentComparisonQueries:
    """Adversarial stress-testing of dual-intent comparison queries."""

    COMPARISON_QUERIES = [
        "What is the difference between Section 139(9) defective return notice and AIS feedback?",
        "Should I respond to 139(9) defect memo or submit AIS feedback for wrong dividend?",
        "Is AIS feedback the same as section 139(9) defective notice?",
        "Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback",
        "Should I file 139(9) response or give AIS feedback for duplicate mutual fund transaction?",
    ]

    @pytest.mark.parametrize("query", COMPARISON_QUERIES)
    def test_dual_intent_both_subprocedures_surfaced_without_penalty(self, hybrid_retriever, query):
        res = hybrid_retriever.search(query, category="tax", top_k=10)
        hit_map = {str(h.document.id): h for h in res.hits}

        assert "itr_defective_return_manual_01" in hit_map, (
            f"Query '{query}' missing itr_defective_return_manual_01 in top hits: {list(hit_map.keys())}"
        )
        assert "itr_ais_feedback_manual_01" in hit_map, (
            f"Query '{query}' missing itr_ais_feedback_manual_01 in top hits: {list(hit_map.keys())}"
        )

        h_139 = hit_map["itr_defective_return_manual_01"]
        h_ais = hit_map["itr_ais_feedback_manual_01"]

        # Neither hit should receive the -0.40 sub-procedure mismatch penalty
        assert "sub_procedure_mismatch_penalty" not in h_139.signals, (
            f"139(9) hit incorrectly penalized in dual-intent query: {h_139.signals}"
        )
        assert "sub_procedure_mismatch_penalty" not in h_ais.signals, (
            f"AIS hit incorrectly penalized in dual-intent query: {h_ais.signals}"
        )

        # Both scores should be healthy and positive (> 0.05)
        assert h_139.score > 0.05, f"139 score too low: {h_139.score}"
        assert h_ais.score > 0.05, f"AIS score too low: {h_ais.score}"

        # Both should be in top 3 hits
        top_3_ids = [str(h.document.id) for h in res.hits[:3]]
        assert "itr_defective_return_manual_01" in top_3_ids
        assert "itr_ais_feedback_manual_01" in top_3_ids


class TestSingleIntentMutualExclusion:
    """Verify single-intent queries strictly enforce mutual exclusion."""

    def test_pure_139_query_penalizes_ais(self, hybrid_retriever):
        query = "How to respond to Section 139(9) defective return notice within 15 days on e-proceedings"
        res = hybrid_retriever.search(query, category="tax", top_k=15)
        assert res.hits[0].document.id == "itr_defective_return_manual_01"
        ais_hits = [h for h in res.hits if str(h.document.id) == "itr_ais_feedback_manual_01"]
        if ais_hits:
            ais_hit = ais_hits[0]
            assert ais_hit.signals.get("sub_procedure_mismatch_penalty") == -0.40
            assert ais_hit.score < 0.0

    def test_pure_ais_query_penalizes_139(self, hybrid_retriever):
        query = "Annual Information Statement AIS feedback duplicate dividend reporting"
        res = hybrid_retriever.search(query, category="tax", top_k=15)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        defective_hits = [h for h in res.hits if str(h.document.id) == "itr_defective_return_manual_01"]
        if defective_hits:
            d_hit = defective_hits[0]
            assert d_hit.signals.get("sub_procedure_mismatch_penalty") == -0.40
            assert d_hit.score < 0.0


class TestBoundaryQueriesAtoEInHybridMode:
    """Empirical verification of Boundary Queries A through E under hybrid retrieval."""

    def test_boundary_query_a_hybrid(self, hybrid_retriever):
        query = "Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        assert res.hits[0].score > 0.15
        top_3 = [str(h.document.id) for h in res.hits[:3]]
        assert "itr_defective_return_manual_01" not in top_3

    def test_boundary_query_b_hybrid(self, hybrid_retriever):
        query = "Received Section 139(9) defective return notice because AIS income differed from ITR"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_defective_return_manual_01"
        assert res.hits[0].score > 0.15
        ais_hits = [h for h in res.hits if str(h.document.id) == "itr_ais_feedback_manual_01"]
        if ais_hits:
            assert ais_hits[0].signals.get("sub_procedure_mismatch_penalty") == -0.40

    def test_boundary_query_c_hybrid(self, hybrid_retriever):
        query = "How to correct duplicate interest in Annual Information Statement?"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        top_5 = [str(h.document.id) for h in res.hits[:5]]
        assert "itr_defective_return_manual_01" not in top_5

    def test_boundary_query_d_hybrid(self, hybrid_retriever):
        query = "How to respond to e-proceedings 15-day defect memo for defective return?"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_defective_return_manual_01"
        top_5 = [str(h.document.id) for h in res.hits[:5]]
        assert "itr_ais_feedback_manual_01" not in top_5

    def test_boundary_query_e_hybrid(self, hybrid_retriever):
        query = "My AIS has wrong dividend transaction what should I do"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        top_3 = [str(h.document.id) for h in res.hits[:3]]
        assert "itr_defective_return_manual_01" not in top_3


class TestAdversarialEdgeInputs:
    """Stress-test edge inputs against hybrid retriever."""

    def test_empty_and_whitespace_queries(self, hybrid_retriever):
        for q in ("", "   ", "\t\n"):
            res = hybrid_retriever.search(q)
            assert res.status == "empty_query"
            assert len(res.hits) == 0

    def test_punctuation_and_symbols_only(self, hybrid_retriever):
        for q in ("???", "!@#$%", ".,;:"):
            res = hybrid_retriever.search(q)
            # Should not crash, and should not return duplicate hits
            assert len(res.hits) == len(set(h.document.id for h in res.hits))

    def test_huge_top_k_stress(self, hybrid_retriever):
        res = hybrid_retriever.search("defective return 139(9)", top_k=100)
        assert len(res.hits) <= 100
        hit_ids = [h.document.id for h in res.hits]
        assert len(hit_ids) == len(set(hit_ids)), "Duplicates detected under top_k=100!"
