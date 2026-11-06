"""Empirical Adversarial Challenge Suite for Milestone 3 (R6).

Executed by challenger_m3_2 to independently stress-test:
1. Qdrant vector database health (1388 points, 384 dims, Cosine distance).
2. Point integrity and valid non-zero embeddings for itr_ais_feedback_manual_01.
3. Score margin and discrimination between Section 139(9) and AIS feedback.
4. Bidirectional -0.40 mismatch penalty suppression.
5. Immunity of AIS document to its own negative statutory disclaimer mentioning 139(9).
6. Adversarial multi-token queries and boundary conditions.
"""
from __future__ import annotations

import numpy as np
import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue

from backend.config import DATA_DIR
from backend.rag.embeddings import FastEmbedProvider
from backend.rag.loader import load_corpus
from backend.rag.retriever import RagRetriever
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


class TestVectorDbHealthAndPointIntegrity:
    """Task 1: Verify Qdrant Vector DB Health and Point Embedding Validity."""

    def test_qdrant_collection_parameters(self, hybrid_retriever):
        """Verify collection govbank_chunks exists with points=1388, dim=384, distance=Cosine."""
        client = hybrid_retriever.vector_store._client
        col_info = client.get_collection("govbank_chunks")
        assert col_info.points_count == 1388, f"Expected 1388 points, got {col_info.points_count}"
        vectors_config = col_info.config.params.vectors
        assert vectors_config.size == 384, f"Expected 384 dimensions, got {vectors_config.size}"
        assert str(vectors_config.distance).lower() in ("distance.cosine", "cosine"), (
            f"Expected Cosine distance, got {vectors_config.distance}"
        )

    def test_ais_document_point_exists_with_valid_embedding(self, hybrid_retriever):
        """Verify itr_ais_feedback_manual_01 is indexed in Qdrant with valid non-zero 384-dim vector."""
        client = hybrid_retriever.vector_store._client
        corpus = load_corpus()
        ais_doc = next((d for d in corpus.documents if any(s.record_id == "itr_ais_feedback_manual_01" for s in d.sources)), None)
        assert ais_doc is not None, "itr_ais_feedback_manual_01 must be present in loaded corpus"

        # Lookup in Qdrant using the canonical document id
        points, _ = client.scroll(
            collection_name="govbank_chunks",
            scroll_filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=ais_doc.id))]),
            with_payload=True,
            with_vectors=True,
            limit=5,
        )
        assert len(points) == 1, f"Expected exactly 1 point for {ais_doc.id}, found {len(points)}"
        p = points[0]
        assert p.payload["category"] == "tax"
        assert "AIS" in p.payload["title"]

        vec = np.array(p.vector, dtype=np.float32)
        assert vec.shape == (384,), f"Vector dimension must be 384, got {vec.shape}"
        assert not np.isnan(vec).any(), "Vector must not contain NaNs"
        assert not np.isinf(vec).any(), "Vector must not contain Infs"
        norm = np.linalg.norm(vec)
        assert norm > 1.0, f"Vector norm must be positive and non-trivial, got {norm}"
        assert np.count_nonzero(vec) == 384, "All dimensions in the embedding must be non-zero"


class TestScoreMarginAndSubProcedureDiscrimination:
    """Task 2: Empirical Score Margin & Discrimination Stress Testing."""

    def test_ais_feedback_clean_query_score_margin(self, hybrid_retriever):
        """Verify AIS query ranks itr_ais_feedback_manual_01 at rank 1 with clean margin over 139(9)."""
        query = "How do I submit feedback for duplicate SFT mutual fund transaction in AIS?"
        res = hybrid_retriever.search(query, category="tax", top_k=20)
        assert res.hits, "Retriever must return hits"
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        assert res.hits[0].score > 0.15

        # Check if 139(9) was considered as candidate; if so, verify -0.40 penalty
        defective_hit = next((h for h in res.hits if h.document.id == "itr_defective_return_manual_01"), None)
        if defective_hit:
            assert defective_hit.signals.get("sub_procedure_mismatch_penalty") == -0.40
            margin = res.hits[0].score - defective_hit.score
            assert margin >= 0.40, f"Expected margin >= 0.40, got {margin}"

    def test_139_9_notice_clean_query_score_margin(self, hybrid_retriever):
        """Verify 139(9) notice query ranks itr_defective_return_manual_01 at rank 1 with clean margin over AIS."""
        query = "How do I respond to Section 139(9) defective return notice on e-proceedings portal?"
        res = hybrid_retriever.search(query, category="tax", top_k=20)
        assert res.hits, "Retriever must return hits"
        assert res.hits[0].document.id == "itr_defective_return_manual_01"
        assert res.hits[0].score > 0.20

        # Check if AIS was considered as candidate; if so, verify -0.40 penalty
        ais_hit = next((h for h in res.hits if h.document.id == "itr_ais_feedback_manual_01"), None)
        if ais_hit:
            assert ais_hit.signals.get("sub_procedure_mismatch_penalty") == -0.40
            margin = res.hits[0].score - ais_hit.score
            assert margin >= 0.40, f"Expected margin >= 0.40, got {margin}"

    def test_boundary_ais_query_with_defect_keyword(self, hybrid_retriever):
        """Verify query 'Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report'."""
        query = "Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report"
        res = hybrid_retriever.search(query, category="tax", top_k=10)
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"
        # Check signals
        assert res.hits[0].signals.get("exact_statutory_boost") == 0.12
        assert res.hits[0].signals.get("symptom_boost") == 0.08

    def test_boundary_139_query_with_ais_keyword(self, hybrid_retriever):
        """Verify query 'Received Section 139(9) defective return notice because AIS income differed from ITR'."""
        query = "Received Section 139(9) defective return notice because AIS income differed from ITR"
        res = hybrid_retriever.search(query, category="tax", top_k=10)
        assert res.hits[0].document.id == "itr_defective_return_manual_01"
        assert res.hits[0].signals.get("exact_statutory_boost") == 0.12
        assert res.hits[0].signals.get("troubleshooting_boost") == 0.05
        assert res.hits[0].signals.get("symptom_boost") == 0.08

    def test_ais_document_immunity_from_self_contamination(self, hybrid_retriever):
        """Verify itr_ais_feedback_manual_01 does not receive negative contamination_penalty despite mentioning 139(9)."""
        query = "Submitting feedback on Annual Information Statement (AIS) for SFT dividend mismatch"
        res = hybrid_retriever.search(query, category="tax", top_k=5)
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_ais_feedback_manual_01"
        # Since has_boost is True, contamination_penalty must NOT be applied
        assert "contamination_penalty" not in top_hit.signals, (
            f"Self-contamination penalty incorrectly applied: {top_hit.signals}"
        )

    def test_tax_three_way_subprocedure_discrimination(self, hybrid_retriever):
        """Verify clean discrimination between: Condonation 119(2)(b), Defective 139(9), and AIS feedback."""
        c_query = "Application for condonation of delay under section 119(2)(b) for late ITR filing"
        c_res = hybrid_retriever.search(c_query, category="tax", top_k=3)
        assert c_res.hits[0].document.id == "itr_condonation_delay_manual_01"

        d_query = "Upload corrected schema response to 139(9) defect memo within 15 days"
        d_res = hybrid_retriever.search(d_query, category="tax", top_k=3)
        assert d_res.hits[0].document.id == "itr_defective_return_manual_01"

        a_query = "Select feedback option Information is duplicate or denied for SFT reporting in AIS"
        a_res = hybrid_retriever.search(a_query, category="tax", top_k=3)
        assert a_res.hits[0].document.id == "itr_ais_feedback_manual_01"
