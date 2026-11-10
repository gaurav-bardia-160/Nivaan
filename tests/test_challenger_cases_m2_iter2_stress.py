"""Empirical Adversarial Stress Test Suite for Milestone M2 Iteration 2 Remediation.

Authored by challenger_cases_m2_iter2 / challenger_cases_m2_iter2_rep.
Empirically challenges:
1. Confidence boundary tests for pipeline.run():
   - confidence < 0.35 (e.g. 0.00, 0.15, 0.25, 0.34, 0.3499) strictly triggers not_found_answer
   - confidence in [0.35, 0.75) (e.g. 0.35, 0.50, 0.74) proceeds to synthesis without premature refusal
   - confidence >= 0.75 proceeds to synthesis
2. Confidence boundary tests for pipeline.run_stream():
   - confidence < 0.35 yields not_found_answer in meta / done events
   - confidence >= 0.35 proceeds to grounded synthesis
3. Off-topic statutory queries (Section 148A against Section 119(2)(b); Section 206AA against DL renewal)
   strictly evaluate to confidence < 0.35 and trigger refusal in end-to-end pipeline.run().
4. Low RRF threshold gate (top_hit.score < 0.010) strictly triggers not_found_answer regardless of confidence.
5. Multi-turn context resolution passes contextual rag_query into confidence scoring, preventing false refusal.
6. Loan Guidelines title enhancement conforms to contracts without violating Zero Predefined Responses.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.schemas import AskRequest, Answer
from backend.rag.models import RagDocument, RetrievalHit, RetrievalResult, SourceReference
from backend.web_search.confidence import compute_rag_confidence
import backend.pipeline as pipeline


def _create_mock_hit(
    doc_id: str = "doc_test_101",
    title: str = "Test Procedure Manual",
    text: str = "Standard procedure text for official citizen inquiry.",
    score: float = 0.035,
    category: str = "tax",
) -> RetrievalHit:
    source = SourceReference(
        dataset_id=f"dataset_{category}",
        record_id=doc_id,
        source_url=f"https://official.gov.in/{doc_id}",
        title=title,
        section="Procedures",
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
        tags=(category, "procedure"),
        sources=(source,),
        warnings=(),
    )
    return RetrievalHit(
        document=doc,
        score=score,
        rank=1,
        signals={"dense": 0.8, "bm25": 12.0},
    )


class TestConfidenceBoundaryPipelineRun:
    """Empirical verification that [0.35, 0.75) proceeds to synthesis while < 0.35 is refused."""

    @pytest.mark.parametrize("simulated_confidence", [0.0, 0.15, 0.25, 0.34, 0.3499])
    def test_run_strictly_refuses_when_confidence_below_0_35(self, simulated_confidence: float):
        """Pipeline run() must return not_found_answer whenever confidence < 0.35."""
        hit = _create_mock_hit(score=0.035)
        mock_result = RetrievalResult(
            query="test query",
            hits=(hit,),
            status="supported_dense",
            searched_documents=50,
        )

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result), \
             patch("backend.web_search.confidence.compute_rag_confidence", return_value=simulated_confidence):
            
            req = AskRequest(question="How do I resolve this issue?")
            ans = pipeline.run(req)

            assert isinstance(ans, Answer)
            assert ans.title == "No verified guide found", (
                f"Expected 'No verified guide found' for confidence {simulated_confidence}, got title '{ans.title}'"
            )
            assert ans.confidence == "low"
            assert "I could not find" in ans.summary or "not found" in ans.summary.lower()

    @pytest.mark.parametrize("simulated_confidence", [0.35, 0.3501, 0.50, 0.74, 0.7499, 0.75, 0.95])
    def test_run_proceeds_to_synthesis_when_confidence_at_least_0_35(self, simulated_confidence: float):
        """Pipeline run() must NOT return not_found_answer when confidence >= 0.35."""
        hit = _create_mock_hit(score=0.035)
        mock_result = RetrievalResult(
            query="test query",
            hits=(hit,),
            status="supported_dense",
            searched_documents=50,
        )

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result), \
             patch("backend.web_search.confidence.compute_rag_confidence", return_value=simulated_confidence), \
             patch("backend.pipeline.classify_domain", return_value="tax"):

            req = AskRequest(question="How do I resolve this issue?")
            ans = pipeline.run(req)

            assert isinstance(ans, Answer)
            assert ans.title != "No verified guide found", (
                f"Confidence {simulated_confidence} prematurely refused with 'No verified guide found'"
            )
            assert ans.summary != ""
            assert len(ans.citations) > 0


class TestConfidenceBoundaryPipelineRunStream:
    """Empirical verification that run_stream respects the 0.35 boundary."""

    def test_run_stream_refuses_when_confidence_below_0_35(self):
        """Streaming run_stream must yield not_found_answer when confidence < 0.35."""
        hit = _create_mock_hit(score=0.035)
        mock_result = RetrievalResult(
            query="test query",
            hits=(hit,),
            status="supported_dense",
            searched_documents=50,
        )

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result), \
             patch("backend.web_search.confidence.compute_rag_confidence", return_value=0.34):

            req = AskRequest(question="How do I resolve this issue?")
            events = list(pipeline.run_stream(req))
            done_events = [e for e in events if e.get("event") == "done"]
            assert len(done_events) == 1
            ans_data = done_events[0]["data"]["answer"]
            assert ans_data["title"] == "No verified guide found"
            assert ans_data["confidence"] == "low"

    def test_run_stream_proceeds_when_confidence_at_least_0_35(self):
        """Streaming run_stream must yield synthesized answer when confidence >= 0.35."""
        hit = _create_mock_hit(score=0.035)
        mock_result = RetrievalResult(
            query="test query",
            hits=(hit,),
            status="supported_dense",
            searched_documents=50,
        )

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result), \
             patch("backend.web_search.confidence.compute_rag_confidence", return_value=0.45), \
             patch("backend.pipeline.classify_domain", return_value="tax"):

            req = AskRequest(question="How do I resolve this issue?")
            events = list(pipeline.run_stream(req))
            done_events = [e for e in events if e.get("event") == "done"]
            assert len(done_events) == 1
            ans_data = done_events[0]["data"]["answer"]
            assert ans_data["title"] != "No verified guide found"
            assert "Test Procedure Manual" in ans_data["title"]


class TestOffTopicStatutoryRefusalGating:
    """Empirical verification that off-topic statutory queries evaluate < 0.35 and trigger pipeline refusal."""

    def test_section_148a_query_with_119_2_b_chunk_strictly_refuses(self):
        """Section 148A query against Section 119(2)(b) chunk must evaluate to < 0.35 and trigger refusal."""
        query = (
            "I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 "
            "alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit expire?"
        )
        offtopic_hit = _create_mock_hit(
            doc_id="tax_119_2_b",
            title="Section 119(2)(b) Condonation of Delay in Filing ITR-V",
            text="CBDT instructions under Section 119(2)(b) for condonation of delay in e-verification of tax returns.",
            score=0.038,
            category="tax",
        )
        mock_result = RetrievalResult(query=query, hits=(offtopic_hit,), status="supported_dense", searched_documents=50)

        # 1. Direct confidence computation must be < 0.35
        conf = compute_rag_confidence(mock_result, query=query)
        assert conf < 0.35, f"Expected confidence < 0.35 for statutory mismatch, got {conf}"

        # 2. Pipeline run() must return not_found_answer
        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result):
            req = AskRequest(question=query)
            ans = pipeline.run(req)
            assert ans.title == "No verified guide found"
            assert ans.confidence == "low"

    def test_section_206aa_query_with_dl_chunk_strictly_refuses(self):
        """Section 206AA / 234H query against Driving Licence chunk must evaluate to < 0.35 and refuse."""
        query = (
            "My salary credit in August came with a flat 20% TDS deduction because my PAN became Inoperative. "
            "I paid late fee under Section 234H. When will PAN activate and how to get refund under Section 206AA?"
        )
        offtopic_hit = _create_mock_hit(
            doc_id="transport_dl_renewal",
            title="Parivahan Sarathi Driving Licence Renewal and Slot Booking",
            text="Procedure to book appointments for biometric capture and driving test for expired driving licences.",
            score=0.039,
            category="transport",
        )
        mock_result = RetrievalResult(query=query, hits=(offtopic_hit,), status="supported_dense", searched_documents=50)

        conf = compute_rag_confidence(mock_result, query=query)
        assert conf < 0.35, f"Expected confidence < 0.35 for statutory mismatch, got {conf}"

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result):
            req = AskRequest(question=query)
            ans = pipeline.run(req)
            assert ans.title == "No verified guide found"
            assert ans.confidence == "low"

    def test_unsupported_statutory_code_refuses(self):
        """Unsupported imaginary section 999XYZ must evaluate < 0.35 and refuse."""
        query = "Notice issued under Section 999XYZ of Income Tax Act"
        chunk = _create_mock_hit(
            doc_id="tax_general",
            title="General Income Tax Guidelines",
            text="General guidelines for income tax filings and assessments.",
            score=0.035,
            category="tax",
        )
        mock_result = RetrievalResult(query=query, hits=(chunk,), status="supported_dense", searched_documents=50)

        conf = compute_rag_confidence(mock_result, query=query)
        assert conf < 0.35, f"Expected confidence < 0.35, got {conf}"

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result):
            req = AskRequest(question=query)
            ans = pipeline.run(req)
            assert ans.title == "No verified guide found"
            assert ans.confidence == "low"


class TestLowRrfThresholdGate:
    """Empirical verification that low RRF score (< 0.010) triggers refusal regardless of confidence."""

    def test_low_rrf_score_refuses_even_if_confidence_high(self):
        """If top_hit.score < 0.010, pipeline must refuse."""
        hit = _create_mock_hit(score=0.008)  # < 0.010
        mock_result = RetrievalResult(
            query="test query",
            hits=(hit,),
            status="supported_dense",
            searched_documents=50,
        )

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result), \
             patch("backend.web_search.confidence.compute_rag_confidence", return_value=0.85):

            req = AskRequest(question="How do I resolve this issue?")
            ans = pipeline.run(req)
            assert ans.title == "No verified guide found"
            assert ans.confidence == "low"


class TestMultiTurnContextAwareConfidence:
    """Empirical verification that multi-turn queries pass rag_query to compute_rag_confidence."""

    def test_anaphoric_followup_incorporates_context_topic_into_confidence(self):
        """Multi-turn follow-up with context topic avoids 0.0 overlap and achieves >= 0.35."""
        hit = _create_mock_hit(
            doc_id="pan_application_guidelines",
            title="Application for Allotment of Permanent Account Number Form 49A",
            text="Documents required for PAN application include proof of identity, proof of address, and proof of date of birth.",
            score=0.038,
            category="pan",
        )
        mock_result = RetrievalResult(
            query="PAN Application Form 49A What documents do I need for that?",
            hits=(hit,),
            status="supported_dense",
            searched_documents=50,
        )

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result):
            req = AskRequest(
                question="What documents do I need for that?",
                context_topic="Relevant official material: PAN Application Form 49A",
                conversation_id="conv_test_123",
            )
            ans = pipeline.run(req)
            assert ans.title != "No verified guide found", "Multi-turn follow-up was incorrectly refused"
            assert "PAN" in ans.title or "Documents" in ans.summary or len(ans.citations) > 0


class TestLoanGuidelinesCitationTitleConformity:
    """Empirical verification of loan guidelines citation title alignment."""

    def test_mudra_loan_citation_title_enhancement(self):
        """Loan query retrieving MUDRA guidelines appends (Loan Guidelines) without hardcoding."""
        hit = _create_mock_hit(
            doc_id="dfs_mudra",
            title="Pradhan Mantri MUDRA Yojana - Department of Financial Services",
            text="Guidelines for collateral-free business loans up to 10 lakhs under Shishu, Kishore, and Tarun.",
            score=0.038,
            category="finance",
        )
        mock_result = RetrievalResult(
            query="loan agreement guidelines mudra",
            hits=(hit,),
            status="supported_dense",
            searched_documents=50,
        )

        with patch("backend.pipeline.retrieve_if_enabled", return_value=mock_result), \
             patch("backend.web_search.confidence.compute_rag_confidence", return_value=0.55):

            req = AskRequest(question="What are the guidelines for MUDRA loan agreement?")
            ans = pipeline.run(req)

            assert "(Loan Guidelines)" in ans.title
            assert "loan" in ans.title.lower() or "rbi" in ans.title.lower()
            # Verify no canned response - citations and synthesis are present
            assert len(ans.citations) > 0
            assert ans.title != "No verified guide found"
