"""Empirical Adversarial Stress Harness for Milestone M2 Confidence Gating.

Authored by challenger_cases_m2_2 (teamwork_challenger).
Empirically tests:
1. On-topic statutory queries maintain valid high/medium confidence.
2. Mixed compound queries (supported + unsupported statutory sections) are penalized.
3. Pure procedural civic queries without statutory sections are NOT falsely penalized.
4. Real corpus end-to-end retrieval and confidence gating integration.
"""
from __future__ import annotations

import pytest
from backend.modules.explainer import explain_rag_result
from backend.rag.models import RagDocument, RetrievalHit, RetrievalResult, SourceReference
from backend.rag.retriever import RagRetriever
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
    section: str = "Statutory Guidelines",
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


class TestOnTopicStatutoryConfidence:
    """Requirement 1: On-topic statutory queries maintain valid high/medium confidence."""

    @pytest.mark.parametrize(
        "query,statutory_anchor,doc_text",
        [
            (
                "Notice under Section 148A(b) of Income Tax Act reply deadline",
                "148a",
                "Section 148A show cause notice: The reply window must be not less than 7 days up to 30 days.",
            ),
            (
                "Time limit to issue notice under Section 149 for reassessment",
                "149",
                "Section 149 limitation: 3 years normal time limit; extended up to 10 years if escaped income exceeds ₹50 Lakhs.",
            ),
            (
                "Reassessment of escaped income under Section 147",
                "147",
                "Section 147 enables Assessing Officer to assess or reassess income escaping assessment subject to sections 148 to 153.",
            ),
            (
                "Prior sanction required under Section 151 for notice",
                "151",
                "Section 151 sanction of specified authority (Principal CCIT / CCIT) required before issuing notice under section 148.",
            ),
            (
                "Flat 20% TDS deduction under Section 206AA on inoperative PAN",
                "206aa",
                "Section 206AA requires higher rate of 20% TDS deduction where PAN is not provided or inoperative.",
            ),
            (
                "Payment of late fee ₹1000 under Section 234H for Aadhaar PAN linking",
                "234h",
                "Section 234H fee of ₹1,000 must be paid prior to submitting request for PAN Aadhaar linking.",
            ),
            (
                "Consequences of inoperative PAN under Rule 114AAA",
                "114aaa",
                "Rule 114AAA provides that inoperative PAN will result in higher TDS and no tax refund issuance.",
            ),
            (
                "Timeline to reactivate PAN under CBDT Circular 03/2023",
                "03/2023",
                "CBDT Circular 03/2023 specifies that PAN becomes operative within 30 days from date of linking request.",
            ),
            (
                "Notice under Section 139(9) defective return rectification",
                "139(9)",
                "Section 139(9) defective return notice gives 15 days to rectify defects in income tax return.",
            ),
            (
                "Application under Section 119(2)(b) condonation of delay in ITR verification",
                "119(2)(b)",
                "Section 119(2)(b) empowers CBDT to condone delay in filing return or verification claim.",
            ),
        ],
    )
    def test_on_topic_statutory_queries_maintain_high_confidence(
        self, query, statutory_anchor, doc_text
    ):
        anchors = extract_statutory_anchors(query)
        assert statutory_anchor in anchors, f"Expected '{statutory_anchor}' in extracted anchors: {anchors}"

        hit = _make_mock_hit(
            doc_id=f"doc_{statutory_anchor}",
            title=f"Income Tax Act {statutory_anchor.upper()} Provisions",
            text=doc_text,
            score=0.045,  # 0.045 / 0.040 = 1.0 base
        )
        res = RetrievalResult(query=query, hits=(hit,), status="supported", searched_documents=50)

        conf = compute_rag_confidence(res, query=query)
        assert conf >= 0.75, f"Expected HIGH confidence (>= 0.75) for on-topic query, got {conf}"

        ans = explain_rag_result(res, user_question=query)
        assert ans.confidence == "high", f"Expected explainer confidence 'high', got {ans.confidence}"


class TestMixedCompoundQueriesPenalized:
    """Requirement 2: Mixed compound queries (e.g. 148A + unsupported section) are penalized."""

    def test_compound_query_half_supported_penalized_below_high(self):
        """Query with supported Section 148A and unsupported Section 999XYZ must not receive HIGH confidence."""
        q = "What is the reply window under Section 148A(b), and what is the penalty under Section 999XYZ?"
        anchors = extract_statutory_anchors(q)
        assert "148a" in anchors
        assert "999xyz" in anchors

        chunk_text = "Section 148A reply window is minimum 7 days up to 30 days. No information about quantum tokens."
        hit = _make_mock_hit(doc_id="tax_148a_only", title="Section 148A Notice Procedure", text=chunk_text, score=0.060)
        res = RetrievalResult(query=q, hits=(hit,), status="supported", searched_documents=50)

        conf = compute_rag_confidence(res, query=q)
        # Matched 1 of 2 anchors -> entity_alignment = 0.50 -> conf <= 0.50
        assert conf <= 0.50, f"Mixed compound query confidence must be <= 0.50, got {conf}"
        assert conf < 0.75, "Mixed compound query must NOT receive HIGH confidence (>= 0.75)"

        ans = explain_rag_result(res, user_question=q)
        assert ans.confidence in ("medium", "low"), f"Explainer badge must not be 'high', got {ans.confidence}"

    def test_compound_query_mostly_unsupported_penalized_below_web_search_threshold(self):
        """Query with 1 supported section and 2 unsupported sections drops below 0.35."""
        q = "Show cause under Section 148A and penalties under Section 888ABC and Section 777DEF"
        anchors = extract_statutory_anchors(q)
        assert len(anchors) == 3

        chunk_text = "Section 148A show cause procedure under Income Tax Act."
        hit = _make_mock_hit(doc_id="tax_148a_only", title="Section 148A", text=chunk_text, score=0.040)
        res = RetrievalResult(query=q, hits=(hit,), status="supported", searched_documents=50)

        conf = compute_rag_confidence(res, query=q)
        # Matched 1 of 3 anchors -> entity_alignment = 0.333 -> conf <= 0.333 < 0.35
        assert conf < 0.35, f"Expected confidence < 0.35 to trigger CRAG, got {conf}"

        ans = explain_rag_result(res, user_question=q)
        assert ans.confidence == "low", f"Expected explainer badge 'low', got {ans.confidence}"

    def test_inoperative_pan_compound_query_with_unsupported_rule_penalized(self):
        """Query with supported Section 206AA and unsupported Rule 999ZZZ is penalized."""
        q = "TDS deduction under Section 206AA and exemption under Rule 999ZZZ"
        anchors = extract_statutory_anchors(q)
        assert "206aa" in anchors
        assert "999zzz" in anchors

        chunk_text = "Section 206AA requires 20% TDS on inoperative PAN."
        hit = _make_mock_hit(doc_id="tax_206aa_only", title="Section 206AA TDS", text=chunk_text, score=0.050)
        res = RetrievalResult(query=q, hits=(hit,), status="supported", searched_documents=50)

        conf = compute_rag_confidence(res, query=q)
        assert conf <= 0.50, f"Expected confidence <= 0.50, got {conf}"
        assert conf < 0.75, "Must not receive high confidence"


class TestPureProceduralCivicQueriesNotFalselyPenalized:
    """Requirement 3: Pure procedural civic queries without statutory sections are not falsely penalized."""

    @pytest.mark.parametrize(
        "civic_query,doc_title,doc_text,category",
        [
            (
                "How do I download my driving license online from Parivahan Sewa portal?",
                "Parivahan Driving Licence Download Procedure",
                "To download driving licence from Parivahan Sewa portal: navigate to online services, enter application number and date of birth, verify OTP, and download digital copy.",
                "transport",
            ),
            (
                "How to apply for duplicate voter ID card online on ECI NVSP portal?",
                "Duplicate Voter ID Card Form 8 Application",
                "Citizens can apply for duplicate voter ID card through National Voters Service Portal by submitting Form 8 for replacement without changes.",
                "civic",
            ),
            (
                "What documents are required for fresh adult passport appointment at PSK?",
                "Passport Seva Document Advisor for Fresh Passport",
                "Documents required for fresh adult passport appointment include proof of date of birth, proof of present address, and Annexure E declaration.",
                "identity",
            ),
            (
                "How to update registered mobile number in Aadhaar card at enrollment centre?",
                "Aadhaar Mobile Number Update Process",
                "To update registered mobile number in Aadhaar card, visit nearest Aadhaar Seva Kendra, submit update form, provide biometric verification, and pay fee.",
                "identity",
            ),
            (
                "How to check ration card beneficiary status in NFSA portal?",
                "NFSA Ration Card Beneficiary Status Check",
                "Check ration card beneficiary status online on NFSA portal by entering ration card number or state specific FPS allocation ID.",
                "civic",
            ),
            (
                "How to transfer PF balance from previous company to new member ID on EPFO portal?",
                "EPFO Online Transfer of PF Balance",
                "Transfer PF balance from previous company to new member ID using Online Transfer Claim Portal (OTCP) on EPFO Unified Member Portal.",
                "epfo",
            ),
        ],
    )
    def test_pure_procedural_civic_queries_achieve_high_confidence(
        self, civic_query, doc_title, doc_text, category
    ):
        # 1. Ensure NO false statutory anchors are extracted
        anchors = extract_statutory_anchors(civic_query)
        assert len(anchors) == 0, f"Pure procedural query '{civic_query}' falsely extracted statutory anchors: {anchors}"

        # 2. Candidate hit with good RRF score and high lexical overlap
        hit = _make_mock_hit(
            doc_id=f"civic_doc_{category}",
            title=doc_title,
            text=doc_text,
            category=category,
            score=0.048,  # > 0.040
        )
        res = RetrievalResult(query=civic_query, hits=(hit,), status="supported", searched_documents=50)

        # 3. Confidence must NOT be penalized (< 0.35)
        conf = compute_rag_confidence(res, query=civic_query)
        assert conf >= 0.75, f"Pure procedural query '{civic_query}' falsely penalized: confidence={conf}"

        # 4. Explainer assigns 'high'
        ans = explain_rag_result(res, user_question=civic_query)
        assert ans.confidence == "high", f"Expected 'high' confidence badge, got '{ans.confidence}'"


class TestRealCorpusIntegrationGating:
    """End-to-end integration tests using live RagRetriever on actual corpus."""

    @pytest.fixture(scope="class")
    def retriever(self):
        return RagRetriever()

    def test_real_corpus_case1_query_retrieval_and_confidence(self, retriever):
        """Case 1 query against real corpus retrieves on-topic statutory chunks with medium/high confidence."""
        res = retriever.search(CASE1_QUERY)
        assert len(res.hits) > 0, "Real corpus must return hits for Case 1 query"

        top_hit = res.hits[0]
        from backend.web_search.confidence import _build_chunk_text
        top_text = _build_chunk_text(top_hit.document)
        assert "148a" in top_text or "149" in top_text, f"Top hit must cover 148A/149: {top_hit.document.id}"

        conf = compute_rag_confidence(res, query=CASE1_QUERY)
        assert conf >= 0.35, f"Case 1 query against real corpus must have confidence >= 0.35, got {conf}"
        ans = explain_rag_result(res, user_question=CASE1_QUERY)
        assert ans.confidence in ("high", "medium"), f"Case 1 explainer badge must be high or medium, got {ans.confidence}"

    def test_real_corpus_case2_query_retrieval_and_confidence(self, retriever):
        """Case 2 query against real corpus retrieves on-topic PAN-TDS chunks with medium/high confidence."""
        res = retriever.search(CASE2_QUERY)
        assert len(res.hits) > 0, "Real corpus must return hits for Case 2 query"

        top_hit = res.hits[0]
        from backend.web_search.confidence import _build_chunk_text
        top_text = _build_chunk_text(top_hit.document)
        assert any(term in top_text for term in ("234h", "206aa", "114aaa", "inoperative")), (
            f"Top hit must cover inoperative PAN provisions: {top_hit.document.id}"
        )

        conf = compute_rag_confidence(res, query=CASE2_QUERY)
        assert conf >= 0.35, f"Case 2 query against real corpus must have confidence >= 0.35, got {conf}"
        ans = explain_rag_result(res, user_question=CASE2_QUERY)
        assert ans.confidence in ("high", "medium"), f"Case 2 explainer badge must be high or medium, got {ans.confidence}"
