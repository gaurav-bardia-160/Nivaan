"""Empirical Adversarial Stress Harness for Milestone M2 Confidence Gating.

Authored by challenger_cases_m2_1 (teamwork_challenger).
Empirically challenges:
1. Reassessment queries (Sections 148A, 149) paired with off-topic candidate chunks:
   - Section 119(2)(b) condonation of delay
   - Section 139(9) defective return
   - PAN card FAQ (Form 49A corrections)
   - Bank account pre-validation
2. Inoperative PAN queries (Sections 206AA, 234H, Circular 03/2023) paired with off-topic chunks:
   - EPFO passbook & UAN activation
   - Protean paperless application rejection
   - Passport Tatkaal checklist
   - Driving license renewal
3. Extreme RRF score saturation (scores 0.05 to 1.00) under statutory mismatch
4. Explainer confidence badge mapping (strictly 'low', never 'high' or 'medium')
5. Boundary conditions: None query, empty hits, negative scores
6. Positive control: On-topic matching chunks achieve 'high' confidence
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from backend.modules.explainer import explain_rag_result
from backend.rag.models import RagDocument, RetrievalHit, RetrievalResult, SourceReference
from backend.web_search.confidence import (
    compute_rag_confidence,
    compute_term_overlap,
    extract_statutory_anchors,
)

CASE1_QUERY = (
    "I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 "
    "alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit to issue this "
    "notice expire under the 3-year vs 10-year rule, and how many days do I have to submit my reply?"
)

CASE2_QUERY = (
    "My salary credit in August came with a flat 20% TDS deduction because my PAN became 'Inoperative' "
    "for missing the Aadhaar linking deadline. I just paid the ₹1,000 late fee under Section 234H on the portal. "
    "How long before my PAN becomes active, and how do I get my company to refund the excess 20% TDS?"
)


def _make_mock_hit(
    doc_id: str,
    title: str,
    text: str,
    section: str = "Standard Operating Procedure",
    category: str = "tax",
    score: float = 0.050,
) -> RetrievalHit:
    source = SourceReference(
        dataset_id=f"dataset_{category}",
        record_id=doc_id,
        source_url=f"https://official.gov.in/{doc_id}",
        title=title,
        section=section,
        reported_status="verified",
        reported_last_verified="2026-11-09",
        reported_quality_score=1.0,
        reported_verification_method="official_portal",
        reported_source_confidence="official",
    )
    doc = RagDocument(
        id=doc_id,
        content_hash=f"hash_{doc_id}",
        category=category,
        text=text,
        language="en",
        tags=(category,),
        sources=(source,),
        warnings=(),
    )
    return RetrievalHit(document=doc, score=score, rank=1, signals={})


class TestReassessmentOffTopicGating:
    """Case 1: Reassessment query paired with off-topic candidate chunks."""

    @pytest.mark.parametrize(
        "doc_id,title,text",
        [
            (
                "tax_sec_119_2_b_condonation",
                "Section 119(2)(b) Condonation of Delay in Filing ITR-V",
                "CBDT instructions under Section 119(2)(b) for condonation of delay in e-verification of tax returns.",
            ),
            (
                "tax_sec_139_9_defective_return",
                "Section 139(9) Defective Return Notice and Rectification",
                "Procedure to rectify defective return notices under Section 139(9) within 15 days on e-filing portal.",
            ),
            (
                "pan_faq_reprint_card",
                "PAN Card Reprint and Correction via Form 49A",
                "Frequently asked questions on how to reprint lost PAN card or correct surname on Protean TIN-NSDL portal.",
            ),
            (
                "bank_prevalidation_guidelines",
                "Bank Account Pre-Validation for Income Tax Refund",
                "Step-by-step instructions to validate and nominate savings bank account for direct credit of tax refunds.",
            ),
        ],
    )
    def test_reassessment_query_with_offtopic_chunk_strictly_low_confidence(
        self, doc_id, title, text
    ):
        """Off-topic chunks must evaluate to confidence < 0.35 (capped at <= 0.25) and get badge 'low'."""
        hit = _make_mock_hit(doc_id=doc_id, title=title, text=text, score=0.060)
        res = RetrievalResult(query=CASE1_QUERY, hits=(hit,), status="supported_lexical", searched_documents=100)

        # 1. compute_rag_confidence evaluation
        confidence = compute_rag_confidence(res, query=CASE1_QUERY)
        assert confidence < 0.35, f"Expected confidence < 0.35, got {confidence} for {doc_id}"
        assert confidence <= 0.25, f"Expected confidence capped at <= 0.25, got {confidence} for {doc_id}"

        # 2. explain_rag_result confidence badge
        ans = explain_rag_result(res, user_question=CASE1_QUERY)
        assert ans is not None
        assert ans.confidence == "low", f"Expected confidence='low', got {ans.confidence} for {doc_id}"


class TestInoperativePanOffTopicGating:
    """Case 2: Inoperative PAN & TDS query paired with off-topic candidate chunks."""

    @pytest.mark.parametrize(
        "doc_id,title,text,category",
        [
            (
                "epfo_passbook_uan_error",
                "EPFO Unified Member Portal Passbook and UAN Activation",
                "How to activate UAN and resolve Member Passbook invalid credentials or claim rejections.",
                "epfo",
            ),
            (
                "protean_app_biometric_reject",
                "Protean Paperless PAN Application Biometric Authentication Failure",
                "Instructions for resolving UIDAI biometric authentication failure error code 330 during PAN application.",
                "pan",
            ),
            (
                "passport_tatkaal_checklist",
                "Passport Seva Kendra Tatkaal Scheme Document Checklist",
                "List of acceptable annexures and verification certificates required for urgent passport issuance.",
                "identity",
            ),
            (
                "sarathi_dl_renewal_slots",
                "Parivahan Sarathi Driving Licence Renewal and Slot Booking",
                "Procedure to book appointments for biometric capture and driving test for expired driving licences.",
                "transport",
            ),
        ],
    )
    def test_inoperative_pan_query_with_offtopic_chunk_strictly_low_confidence(
        self, doc_id, title, text, category
    ):
        """Off-topic chunks must evaluate to confidence < 0.35 (capped at <= 0.25) and get badge 'low'."""
        hit = _make_mock_hit(doc_id=doc_id, title=title, text=text, category=category, score=0.055)
        res = RetrievalResult(query=CASE2_QUERY, hits=(hit,), status="supported_lexical", searched_documents=100)

        # 1. compute_rag_confidence evaluation
        confidence = compute_rag_confidence(res, query=CASE2_QUERY)
        assert confidence < 0.35, f"Expected confidence < 0.35, got {confidence} for {doc_id}"
        assert confidence <= 0.25, f"Expected confidence capped at <= 0.25, got {confidence} for {doc_id}"

        # 2. explain_rag_result confidence badge
        ans = explain_rag_result(res, user_question=CASE2_QUERY)
        assert ans is not None
        assert ans.confidence == "low", f"Expected confidence='low', got {ans.confidence} for {doc_id}"


class TestAdversarialScoreSaturation:
    """Extreme RRF score attacks attempting to force HIGH confidence on off-topic chunks."""

    @pytest.mark.parametrize("extreme_score", [0.040, 0.080, 0.150, 0.500, 1.000, 10.000])
    def test_extreme_rrf_score_cannot_bypass_statutory_penalty(self, extreme_score):
        """Even with an astronomical RRF score, missing statutory anchors must cap confidence <= 0.25."""
        hit = _make_mock_hit(
            doc_id="unrelated_high_score_doc",
            title="General Income Tax Circulars and Filing Deadlines",
            text="General CBDT filing guidelines for annual financial transactions without statutory details.",
            score=extreme_score,
        )
        res = RetrievalResult(query=CASE1_QUERY, hits=(hit,), status="supported_lexical", searched_documents=50)

        confidence = compute_rag_confidence(res, query=CASE1_QUERY)
        assert confidence < 0.35, f"Extreme score {extreme_score} breached 0.35 threshold: got {confidence}"
        assert confidence <= 0.25, f"Extreme score {extreme_score} breached 0.25 cap: got {confidence}"

        ans = explain_rag_result(res, user_question=CASE1_QUERY)
        assert ans.confidence == "low", f"Extreme score {extreme_score} produced confidence='{ans.confidence}'"


class TestPositiveControlOnTopicChunks:
    """Verify that genuine on-topic chunks with statutory match receive HIGH confidence."""

    def test_on_topic_section_148a_149_chunk_receives_high_confidence(self):
        """Case 1 query with matching Section 148A & 149 chunk must score >= 0.75 and badge 'high'."""
        text = (
            "Section 148A Show Cause Notice Procedure: The Assessing Officer must provide a reply window "
            "of not less than 7 days and up to 30 days. Under Section 149(1)(a), normal limitation expires "
            "after 3 years from the end of the relevant assessment year. Extended 10-year limitation under "
            "Section 149(1)(b) applies only where escaped income is ₹50 Lakhs or more."
        )
        hit = _make_mock_hit(
            doc_id="tax_statutory_148a_149",
            title="Income Tax Act Section 148A Notice and Section 149 Time Limits",
            text=text,
            score=0.060,  # base score 0.060 / 0.040 = 1.0
        )
        res = RetrievalResult(query=CASE1_QUERY, hits=(hit,), status="supported_lexical", searched_documents=100)

        confidence = compute_rag_confidence(res, query=CASE1_QUERY)
        assert confidence >= 0.75, f"Expected high confidence >= 0.75 for on-topic chunk, got {confidence}"

        ans = explain_rag_result(res, user_question=CASE1_QUERY)
        assert ans.confidence == "high", f"Expected confidence='high' for on-topic hit, got {ans.confidence}"

    def test_on_topic_inoperative_pan_circular_03_2023_chunk_receives_high_confidence(self):
        """Case 2 query with matching Rule 114AAA, Circular 03/2023, Section 206AA chunk receives HIGH."""
        text = (
            "CBDT Circular 03/2023 and Rule 114AAA: An inoperative PAN can be made operative within 30 days "
            "of payment of ₹1,000 late fee under Section 234H and submission of Aadhaar linking request. "
            "Under Section 206AA, TDS deducted at 20% on inoperative PAN cannot be refunded by the employer "
            "via payroll; the taxpayer must claim refund by filing an Income Tax Return (ITR)."
        )
        hit = _make_mock_hit(
            doc_id="pan_statutory_cir_03_2023_206aa",
            title="CBDT Circular 03/2023: Consequences of Inoperative PAN and Section 206AA TDS",
            text=text,
            category="pan",
            score=0.060,
        )
        res = RetrievalResult(query=CASE2_QUERY, hits=(hit,), status="supported_lexical", searched_documents=100)

        confidence = compute_rag_confidence(res, query=CASE2_QUERY)
        assert confidence >= 0.75, f"Expected high confidence >= 0.75 for on-topic chunk, got {confidence}"

        ans = explain_rag_result(res, user_question=CASE2_QUERY)
        assert ans.confidence == "high", f"Expected confidence='high' for on-topic hit, got {ans.confidence}"


class TestRobustnessAndBoundaryConditions:
    """Boundary conditions, None handling, and robustness."""

    def test_none_rag_result_returns_zero(self):
        assert compute_rag_confidence(None, query=CASE1_QUERY) == 0.0
        assert compute_rag_confidence(None, query=None) == 0.0

    def test_empty_hits_returns_zero(self):
        empty_res = RetrievalResult(query=CASE1_QUERY, hits=(), status="no_hits", searched_documents=0)
        assert compute_rag_confidence(empty_res, query=CASE1_QUERY) == 0.0

    def test_zero_or_negative_score_returns_zero(self):
        hit_zero = _make_mock_hit("doc0", "Title", "Text", score=0.0)
        res_zero = RetrievalResult(query=CASE1_QUERY, hits=(hit_zero,), status="supported", searched_documents=10)
        assert compute_rag_confidence(res_zero, query=CASE1_QUERY) == 0.0

        hit_neg = _make_mock_hit("doc_neg", "Title", "Text", score=-0.05)
        res_neg = RetrievalResult(query=CASE1_QUERY, hits=(hit_neg,), status="supported", searched_documents=10)
        assert compute_rag_confidence(res_neg, query=CASE1_QUERY) == 0.0

    def test_query_none_preserves_backward_compatible_base_score(self):
        hit = _make_mock_hit("doc_base", "Title", "Text", score=0.020)
        res = RetrievalResult(query="test", hits=(hit,), status="supported", searched_documents=10)
        # 0.020 / 0.040 = 0.50
        conf = compute_rag_confidence(res, query=None)
        assert abs(conf - 0.50) < 1e-4

    def test_query_empty_string_preserves_base_score(self):
        hit = _make_mock_hit("doc_base", "Title", "Text", score=0.020)
        res = RetrievalResult(query="test", hits=(hit,), status="supported", searched_documents=10)
        conf = compute_rag_confidence(res, query="   ")
        assert abs(conf - 0.50) < 1e-4

    def test_extract_statutory_anchors_precision(self):
        # CASE1_QUERY has Section 148A(b)
        anchors1 = extract_statutory_anchors(CASE1_QUERY)
        assert "148a" in anchors1
        assert "149" not in anchors1  # CASE1 query mentions 3-year vs 10-year rule, not section 149 explicitly

        # Query with explicit Section 148A and Section 149
        explicit_q1 = "Notice under Section 148A(b) and time limit under Section 149"
        explicit_anchors1 = extract_statutory_anchors(explicit_q1)
        assert "148a" in explicit_anchors1
        assert "149" in explicit_anchors1

        # CASE2_QUERY has Section 234H
        anchors2 = extract_statutory_anchors(CASE2_QUERY)
        assert "234h" in anchors2
        assert "206aa" not in anchors2  # CASE2 mentions 20% TDS, not section 206AA explicitly

        # Query with explicit Section 206AA, Rule 114AAA, Circular 03/2023, and Section 234H
        explicit_q2 = "Rule 114AAA and Circular 03/2023 fee under Section 234H with Section 206AA TDS"
        explicit_anchors2 = extract_statutory_anchors(explicit_q2)
        assert "206aa" in explicit_anchors2
        assert "234h" in explicit_anchors2
        assert "114aaa" in explicit_anchors2
        assert "03/2023" in explicit_anchors2
