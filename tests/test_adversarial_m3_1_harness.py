"""Empirical Adversarial Challenge Suite for Milestone 3 (R6).

Executed by challenger_m3_1 to independently verify Same-Domain Sub-Procedure Granularity (R6),
focusing on boundary discrimination between Section 139(9) Defective Returns and AIS Feedback,
symptom cluster boosts/penalties, bidirectional sub-procedure conflict penalties, and end-to-end pipeline citation isolation.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.modules.domain_router import Domain, classify_domain
from backend.rag.retriever import RagRetriever
from backend.pipeline import run_pipeline


@pytest.fixture(scope="module")
def retriever():
    return RagRetriever()


class TestEmpiricalBoundaryQueriesAtoE:
    """Core empirical verification queries required by Milestone 3 challenger protocol."""

    def test_boundary_query_a_discrepancy_defect_in_ais(self, retriever):
        """Boundary Query A: 'Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report'.

        Contains the word 'defect' alongside AIS terms. Must rank AIS manual #1 and suppress 139(9).
        """
        query = "Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report"
        res = retriever.search(query, category="tax")
        assert len(res.hits) > 0, "Retriever must return hits for Query A"
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_ais_feedback_manual_01", (
            f"Query A expected rank 1 to be itr_ais_feedback_manual_01, got {top_hit.document.id}"
        )
        assert top_hit.score > 0.15
        assert top_hit.signals.get("symptom_boost") == 0.08
        # Ensure 139(9) is not in the top 3 hits
        top_ids = [h.document.id for h in res.hits[:3]]
        assert "itr_defective_return_manual_01" not in top_ids, (
            f"139(9) defective return must not bleed into top hits: {top_ids}"
        )

    def test_boundary_query_b_defective_notice_due_to_ais_mismatch(self, retriever):
        """Boundary Query B: 'Received Section 139(9) defective return notice because AIS income differed from ITR'.

        Contains 'AIS' within a 139(9) notice context. Must rank 139(9) manual #1 and penalize AIS feedback.
        """
        query = "Received Section 139(9) defective return notice because AIS income differed from ITR"
        res = retriever.search(query, category="tax", top_k=50)
        assert len(res.hits) > 0, "Retriever must return hits for Query B"
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_defective_return_manual_01", (
            f"Query B expected rank 1 to be itr_defective_return_manual_01, got {top_hit.document.id}"
        )
        # Find AIS feedback hit and verify bidirectional mismatch penalty (-0.40)
        ais_hits = [h for h in res.hits if h.document.id == "itr_ais_feedback_manual_01"]
        assert len(ais_hits) > 0, "AIS hit must be present among candidates to verify penalty"
        ais_hit = ais_hits[0]
        assert ais_hit.signals.get("sub_procedure_mismatch_penalty") == -0.40, (
            f"AIS hit should receive -0.40 sub-procedure penalty, got {ais_hit.signals}"
        )
        assert ais_hit.score < 0.0, f"AIS hit score must be depressed below 0, got {ais_hit.score}"
        margin = top_hit.score - ais_hit.score
        assert margin >= 0.35, f"Expected margin >= 0.35, got {margin}"

    def test_query_c_correct_duplicate_interest_in_ais(self, retriever):
        """Query C: 'How to correct duplicate interest in Annual Information Statement?'.

        Must rank AIS manual #1 and prevent 139(9) defective return from contaminating results.
        """
        query = "How to correct duplicate interest in Annual Information Statement?"
        res = retriever.search(query, category="tax")
        assert len(res.hits) > 0
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_ais_feedback_manual_01", (
            f"Query C expected itr_ais_feedback_manual_01 at rank 1, got {top_hit.document.id}"
        )
        top_ids = [h.document.id for h in res.hits[:5]]
        assert "itr_defective_return_manual_01" not in top_ids

    def test_query_d_respond_to_e_proceedings_15_day_defect_memo(self, retriever):
        """Query D: 'How to respond to e-proceedings 15-day defect memo for defective return?'.

        Must rank 139(9) manual #1 and prevent AIS feedback from contaminating results.
        """
        query = "How to respond to e-proceedings 15-day defect memo for defective return?"
        res = retriever.search(query, category="tax")
        assert len(res.hits) > 0
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_defective_return_manual_01", (
            f"Query D expected itr_defective_return_manual_01 at rank 1, got {top_hit.document.id}"
        )
        top_ids = [h.document.id for h in res.hits[:5]]
        assert "itr_ais_feedback_manual_01" not in top_ids

    def test_query_e_ambiguous_ais_wrong_dividend_transaction(self, retriever):
        """Query E (Ambiguous): 'My AIS has wrong dividend transaction what should I do'.

        Must retrieve AIS feedback without 139(9) bleeding:
        1. AIS manual ranks #1.
        2. Top 3 production hits contain NO 139(9) defective return.
        3. If 139(9) was scored as candidate due to lexical 'AIS' in text, it receives -0.40 mismatch penalty.
        4. Pipeline citations have zero 139(9) bleeding.
        """
        query = "My AIS has wrong dividend transaction what should I do"
        res = retriever.search(query, category="tax", top_k=3)
        assert len(res.hits) > 0
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_ais_feedback_manual_01", (
            f"Query E expected itr_ais_feedback_manual_01 at rank 1, got {top_hit.document.id}"
        )
        top_3_ids = [h.document.id for h in res.hits]
        assert "itr_defective_return_manual_01" not in top_3_ids, (
            f"139(9) must not bleed into top 3 production hits: {top_3_ids}"
        )

        # In expanded search (top_k=10), verify that if 139(9) appeared, it was heavily penalized below 0
        res_expanded = retriever.search(query, category="tax", top_k=10)
        defective_hits = [h for h in res_expanded.hits if h.document.id == "itr_defective_return_manual_01"]
        if defective_hits:
            defective_hit = defective_hits[0]
            assert defective_hit.signals.get("sub_procedure_mismatch_penalty") == -0.40
            assert defective_hit.score < 0.0, f"Expected score < 0.0 due to penalty, got {defective_hit.score}"



class TestAdversarialStressScenarios:
    """Adversarial stress-testing of same-domain discrimination across domain routing and pipeline."""

    @pytest.mark.parametrize(
        "query,expected_doc_id",
        [
            ("Annual Information Statement feedback for interest received on income tax refund", "itr_ais_feedback_manual_01"),
            ("How to dispute SFT-005 transaction in AIS", "itr_ais_feedback_manual_01"),
            ("AIS feedback status says modified derived value in TIS", "itr_ais_feedback_manual_01"),
            ("Notice under Section 139(9) for mismatch between TDS claimed and 26AS", "itr_defective_return_manual_01"),
            ("CPC 2.0 defective return rectification utility error in JSON schema", "itr_defective_return_manual_01"),
            ("15 days deadline passed for defective return notice under section 139(9)", "itr_defective_return_manual_01"),
        ],
    )
    def test_end_to_end_sub_procedure_retrieval_without_category_hint(self, retriever, query, expected_doc_id):
        """Verify queries route through Domain.TAXATION automatically and retrieve correct sub-procedure."""
        domain = classify_domain(query)
        assert domain == Domain.TAXATION, f"Query '{query}' classified as {domain}, expected Domain.TAXATION"
        res = retriever.search(query)
        assert len(res.hits) > 0
        assert res.hits[0].document.id == expected_doc_id

    @pytest.mark.parametrize(
        "query,expected_doc_id",
        [
            ("AIS me duplicate transaction kaise hataye feedback portal par", "itr_ais_feedback_manual_01"),
            ("139(9) defective return notice ka reply e-proceedings me kaise kare", "itr_defective_return_manual_01"),
        ],
    )
    def test_multilingual_phrasings_retrieve_correct_sub_procedure(self, retriever, query, expected_doc_id):
        """Verify Hinglish mixed-language phrasings accurately resolve to the correct sub-procedure."""
        res = retriever.search(query)
        assert len(res.hits) > 0
        assert res.hits[0].document.id == expected_doc_id

    def test_pipeline_citation_isolation(self):
        """Verify run_pipeline() produces high-confidence answers with clean isolated citations."""
        res_ais = run_pipeline("Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report")
        assert res_ais.confidence == "high"
        ais_citations = [c.title for c in res_ais.citations]
        assert any("Annual Information Statement" in t or "AIS" in t for t in ais_citations)
        assert not any("139(9)" in t or "Defective Return" in t for t in ais_citations)

        res_139 = run_pipeline("Received Section 139(9) defective return notice because AIS income differed from ITR")
        assert res_139.confidence == "high"
        notice_citations = [c.title for c in res_139.citations]
        assert any("139(9)" in t or "Defective Return" in t for t in notice_citations)
        assert not any("Annual Information Statement" in t for t in notice_citations)

    def test_ais_document_immunity_from_self_contamination(self, retriever):
        """Verify itr_ais_feedback_manual_01 does not receive negative contamination_penalty despite mentioning 139(9)."""
        query = "Submitting feedback on Annual Information Statement (AIS) for SFT dividend mismatch"
        res = retriever.search(query, category="tax", top_k=5)
        top_hit = res.hits[0]
        assert top_hit.document.id == "itr_ais_feedback_manual_01"
        # Since has_boost is True, contamination_penalty must NOT be applied
        assert "contamination_penalty" not in top_hit.signals, (
            f"Self-contamination penalty incorrectly applied: {top_hit.signals}"
        )

    def test_ais_document_integrity_and_anti_bleeding_clauses(self):
        """Verify the official AIS document in troubleshooting_tax.jsonl contains all required statutory clauses."""
        path = Path("backend/data/refined/troubleshooting/troubleshooting_tax.jsonl")
        assert path.exists()
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        ais_record = next((r for r in records if r.get("id") == "itr_ais_feedback_manual_01"), None)
        assert ais_record is not None, "itr_ais_feedback_manual_01 must be present in troubleshooting_tax.jsonl"
        text = ais_record["text"].lower()

        # Check official portal domain and feedback categories
        assert "incometax.gov.in" in ais_record.get("source_url", "")
        assert "information is correct" in text
        assert "information is not fully correct" in text
        assert "information is denied" in text
        assert "information is duplicate" in text
        assert "derived value" in text
        assert "tis" in text

        # Check explicit negative boundary disclaimer
        assert "ais feedback is not a section 139(9) defective return proceeding" in text
