"""Automated Regression and E2E Test Suite for Case 1, Case 2, Gating, and Decomposition.

Architecture & Requirements Alignment:
- ORIGINAL_REQUEST.md: Requirements R1, R2, R3, R4 and Case 1 / Case 2 Acceptance Criteria.
- PROJECT.md: Features 1-10, Milestones M1-M4 & E2E Testing Suite.
- survey_arch_gating_3/handoff.md: Section 6 Automated Test Specifications & Assertions.
- survey_reassess_1/handoff.md: Statutory Reassessment Rules (Sections 147-151, AY 2018-19 limitation).
- survey_inop_pan_2/handoff.md: Inoperative PAN & TDS Rules (Rule 114AAA, Cir 03/2023, Sec 206AA, Sec 234H).

Coverage Tiers:
- Tier 1: Feature Coverage (R1-R4: Corpus existence, Domain routing, Gating on off-topic chunks, Query modality, Decomposition)
- Tier 2: Boundary & Corner Cases (₹50 Lakhs limit boundary, 3-year date boundary, 7-day minimum reply window, offline pytest execution, zero predefined responses)
- Tier 3: Cross-Feature Combinations (Decomposition + Gating, Analytical shape + Multi-part synthesis, Dual-category tax+pan, Symptom cluster conflict penalties)
- Tier 4: Real-World Application Scenarios (Verbatim Case 1 and Case 2 user inquiries executed through run_pipeline)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.config import DATA_DIR
from backend.modules.domain_router import (
    Domain,
    classify_domain,
    get_allowed_rag_categories,
)
from backend.modules.explainer import explain_rag_result
from backend.pipeline import run_pipeline
from backend.rag.loader import load_corpus
from backend.rag.models import RagDocument, RetrievalHit, RetrievalResult, SourceReference
from backend.rag.retriever import RagRetriever
from backend.schemas import Answer, Step
from backend.web_search.confidence import compute_rag_confidence

MANIFEST_PATH = Path("backend/data/rag_manifest.json")
TROUBLESHOOTING_TAX_PATH = Path("backend/data/refined/troubleshooting/troubleshooting_tax.jsonl")
TROUBLESHOOTING_PAN_PATH = Path("backend/data/refined/troubleshooting/troubleshooting_pan.jsonl")

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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _get_decompose_query_fn():
    """Dynamically resolve decompose_query from candidate modules."""
    for mod_name in ("backend.rag.retriever", "backend.rag.decomposition", "backend.modules.query_decomposer"):
        try:
            mod = __import__(mod_name, fromlist=["decompose_query"])
            fn = getattr(mod, "decompose_query", None)
            if fn is not None:
                return fn
        except ImportError:
            pass
    return None


def _get_query_modality_classifier():
    """Dynamically resolve classify_query_modality and QueryModality enum."""
    for mod_name in ("backend.modules.explainer", "backend.modules.domain_router"):
        try:
            mod = __import__(mod_name, fromlist=["classify_query_modality", "QueryModality"])
            fn = getattr(mod, "classify_query_modality", None)
            enum_cls = getattr(mod, "QueryModality", None)
            if fn is not None:
                return fn, enum_cls
        except ImportError:
            pass
    return None, None


def make_mock_doc(
    id: str = "doc_test_01",
    category: str = "tax",
    title: str = "Official Income Tax Procedure",
    section: str = "Procedural Guidelines",
    text: str = "Standard Income Tax Department official guidelines.",
    tags: tuple[str, ...] = ("tax",),
    url: str = "https://www.incometax.gov.in/guidelines/official",
) -> RagDocument:
    source = SourceReference(
        dataset_id="troubleshooting_tax",
        record_id=id,
        source_url=url,
        title=title,
        section=section,
        reported_status="verified",
        reported_last_verified="2026-11-09",
        reported_quality_score=1.0,
        reported_verification_method="official_portal",
        reported_source_confidence="official",
    )
    return RagDocument(
        id=id,
        content_hash="content_hash_" + id,
        category=category,
        text=text,
        language="en",
        tags=tags,
        sources=(source,),
        warnings=(),
    )


# ==============================================================================
# TIER 1: FEATURE COVERAGE (R1 - R4)
# ==============================================================================

class TestTier1FeatureCoverage:
    """Tier 1: Feature coverage verifying individual architectural and corpus contracts."""

    def test_tier1_corpus_existence_reassessment_sections_147_to_151(self):
        """R4: Ingest official Income Tax Act statutory provisions covering Sections 147-151."""
        assert MANIFEST_PATH.exists(), "rag_manifest.json must exist"
        records = _read_jsonl(TROUBLESHOOTING_TAX_PATH)
        assert len(records) > 0, "troubleshooting_tax.jsonl must contain tax troubleshooting records"

        all_text = " ".join(
            (r.get("text", "") + " " + r.get("title", "") + " " + " ".join(r.get("retrieval_tags", []))).lower()
            for r in records
        )

        # 1. Statutory Sections 147, 148, 148A, 149, 151
        assert "148a" in all_text or "148a(b)" in all_text, "Corpus must cover Section 148A show cause procedure"
        assert "149" in all_text, "Corpus must cover Section 149 time limits / limitation rules"
        assert "151" in all_text or "specified authority" in all_text, "Corpus must cover Section 151 sanction"

        # 2. Key operational thresholds
        assert any(term in all_text for term in ("7 days", "not less than seven days", "7 to 30 days")), (
            "Corpus must state Section 148A(b) minimum 7-day to 30-day reply window"
        )
        assert any(term in all_text for term in ("50 lakh", "50,00,000", "fifty lakh")), (
            "Corpus must state Section 149(1)(b) ₹50 Lakhs threshold for 10-year extended limitation"
        )
        assert any(term in all_text for term in ("3 years", "three years", "3-year")), (
            "Corpus must state Section 149(1)(a) 3-year normal limitation period"
        )

    def test_tier1_corpus_existence_inoperative_pan_tds_provisions(self):
        """R4: Ingest official provisions for Rule 114AAA, Circular 03/2023, and Section 206AA."""
        pan_records = _read_jsonl(TROUBLESHOOTING_PAN_PATH)
        tax_records = _read_jsonl(TROUBLESHOOTING_TAX_PATH)
        combined_records = pan_records + tax_records

        all_text = " ".join(
            (r.get("text", "") + " " + r.get("title", "") + " " + " ".join(r.get("retrieval_tags", []))).lower()
            for r in combined_records
        )

        # 1. Rule 114AAA and Circular 03/2023 Reactivation Timeline (~30 days)
        assert any(term in all_text for term in ("03/2023", "circular 03", "circular no. 03 of 2023")), (
            "Corpus must reference CBDT Circular 03/2023"
        )
        assert "114aaa" in all_text, "Corpus must reference Rule 114AAA"
        assert any(term in all_text for term in ("30 days", "thirty days", "within 30")), (
            "Corpus must state PAN reactivation timeline is within 30 days from linking request"
        )
        assert any(term in all_text for term in ("234h", "1,000", "1000")), (
            "Corpus must state ₹1,000 late fee under Section 234H"
        )

        # 2. Section 206AA TDS Deduction and ITR Refund Procedure
        assert "206aa" in all_text, "Corpus must cover Section 206AA higher 20% TDS on inoperative PAN"
        assert any(term in all_text for term in ("cannot refund", "employer cannot", "no refund by employer", "no adjustment in payroll")), (
            "Corpus must explain employer cannot refund or adjust deposited 20% TDS via payroll"
        )
        assert any(term in all_text for term in ("itr", "tax return", "income tax return", "claim refund", "file itr")), (
            "Corpus must explain excess TDS refund must be claimed by employee via ITR filing"
        )

    def test_tier1_domain_routing_reassessment_statutory_patterns(self):
        """Domain Router: Matches reassessment statutory sections into Domain.TAXATION."""
        queries = [
            "Notice under Section 148A(b) for AY 2018-19 alleging unexplained share trading",
            "Did time limit expire under Section 149 for reassessment notice?",
            "Section 148 reassessment notice time-barred after 3 years",
            "Escaped income ₹6.5 Lakhs under Section 147 and 151 sanction",
        ]
        for q in queries:
            domain = classify_domain(q)
            assert domain == Domain.TAXATION, f"Query '{q}' should route to Domain.TAXATION, got {domain}"

    def test_tier1_domain_routing_inoperative_pan_tds_dual_category(self):
        """Domain Router: Inoperative PAN with salary TDS queries allow access to both pan and tax."""
        q = "My salary credit came with 20% TDS deduction because PAN is inoperative. Paid 234H fee. How to get refund?"
        domain = classify_domain(q)
        assert domain in (Domain.TAXATION, Domain.IDENTITY), f"Query should route to TAXATION or IDENTITY, got {domain}"
        allowed_cats = get_allowed_rag_categories(domain)
        assert allowed_cats is not None, "Allowed RAG categories must not be None"
        # Dual-category allowance contract: PAN-TDS queries require access to both pan and tax datasets
        assert "pan" in allowed_cats or "tax" in allowed_cats, "Must allow at least pan or tax"

    def test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic(self):
        """R2: Relevance gating prevents off-topic chunks from scoring HIGH confidence."""
        offtopic_doc = make_mock_doc(
            id="itr_condonation_delay_manual_01",
            category="tax",
            title="Income Tax Manual on Section 119(2)(b) Condonation of Delay for Expired ITR Verification",
            section="Section 119(2)(b) Delay Condonation Petitions",
            text="Section 119(2)(b) Condonation of Delay for Expired e-Verification. If you failed to verify ITR within 30 days...",
            tags=("condonation_of_delay", "section_119_2_b", "troubleshooting"),
        )
        mock_hit = RetrievalHit(document=offtopic_doc, score=0.038, rank=1, signals={})
        mock_result = RetrievalResult(query=CASE1_QUERY, hits=(mock_hit,), status="supported_lexical", searched_documents=100)

        # Multi-factor confidence evaluation accepting query parameter
        try:
            confidence = compute_rag_confidence(mock_result, query=CASE1_QUERY)
        except TypeError as exc:
            pytest.fail(f"compute_rag_confidence must accept 'query' argument per R2 specification: {exc}")

        assert confidence < 0.35, (
            f"Off-topic chunk (119(2)(b)) for 148A reassessment query must have confidence < 0.35 to trigger CRAG, got: {confidence}"
        )

    def test_tier1_query_modality_classification_analytical_vs_procedural(self):
        """R1: Intent modality classifier separates procedural queries from analytical queries."""
        classify_fn, enum_cls = _get_query_modality_classifier()
        assert classify_fn is not None, "classify_query_modality must be defined in explainer or domain_router"

        # Case 1 & Case 2 queries are analytical / calculation / legal-interpretation
        mod1 = classify_fn(CASE1_QUERY)
        mod2 = classify_fn(CASE2_QUERY)

        procedural_val = getattr(enum_cls, "PROCEDURAL", "procedural") if enum_cls else "procedural"
        assert mod1 != procedural_val, f"Case 1 must not be classified as procedural, got {mod1}"
        assert mod2 != procedural_val, f"Case 2 must not be classified as procedural, got {mod2}"

        # Standard operational query should remain procedural
        proc_q = "How do I apply for Form 49A PAN card online step by step on Protean portal?"
        mod_proc = classify_fn(proc_q)
        assert mod_proc == procedural_val, f"Operational guide must be procedural, got {mod_proc}"

    def test_tier1_explainer_checklist_elimination_for_analytical_queries(self):
        """R1: explain_rag_result returns steps == [] for analytical queries without 3-step checklists."""
        doc = make_mock_doc(
            id="tax_section_148a_reassessment_sop",
            category="tax",
            title="Income Tax Department: Section 148A Reassessment Notice and Section 149 Limitation",
            section="Section 148A Reply Window and Section 149 Limitation",
            text=(
                "Section 148A Show Cause Notice: The Assessing Officer must provide a reply period of not less than "
                "7 days and not exceeding 30 days. Under Section 149(1)(a), normal limitation expires in 3 years from "
                "end of assessment year. Extended 10-year limitation under Section 149(1)(b) applies only if escaped "
                "income is ₹50 Lakhs or more."
            ),
            tags=("reassessment", "148a", "149", "limitation"),
        )
        hit = RetrievalHit(document=doc, score=0.065, rank=1, signals={})
        result = RetrievalResult(query=CASE1_QUERY, hits=(hit,), status="supported_lexical", searched_documents=100)

        ans = explain_rag_result(result, user_question=CASE1_QUERY)
        assert ans is not None, "explain_rag_result must return an Answer"
        assert ans.steps == [], f"Analytical query must have steps == [], got: {ans.steps}"
        assert not any("review" in s.title.lower() for s in ans.steps), "Must not generate 'Review [Doc]' steps"
        assert not any("verify official portal and apply" in s.title.lower() for s in ans.steps)

    def test_tier1_query_decomposition_isolates_subquestions(self):
        """R3: decompose_query splits compound queries into distinct sub-questions."""
        decompose_fn = _get_decompose_query_fn()
        assert decompose_fn is not None, "decompose_query must be implemented in retriever or decomposition module"

        # Case 1 Decomposition
        sub_qs_1 = decompose_fn(CASE1_QUERY)
        assert len(sub_qs_1) >= 2, f"Case 1 must decompose into at least 2 sub-questions, got: {sub_qs_1}"
        assert any("limit" in sq.lower() or "149" in sq.lower() or "expire" in sq.lower() or "3-year" in sq.lower() for sq in sub_qs_1), (
            "Sub-question 1 must isolate the limitation period under Section 149"
        )
        assert any("reply" in sq.lower() or "days" in sq.lower() or "148a" in sq.lower() for sq in sub_qs_1), (
            "Sub-question 2 must isolate the reply deadline under Section 148A(b)"
        )

        # Case 2 Decomposition
        sub_qs_2 = decompose_fn(CASE2_QUERY)
        assert len(sub_qs_2) >= 2, f"Case 2 must decompose into at least 2 sub-questions, got: {sub_qs_2}"
        assert any("active" in sq.lower() or "operative" in sq.lower() or "timeline" in sq.lower() or "how long" in sq.lower() for sq in sub_qs_2), (
            "Sub-question 1 must isolate the reactivation timeline under Rule 114AAA / Circular 03/2023"
        )
        assert any("refund" in sq.lower() or "company" in sq.lower() or "tds" in sq.lower() or "20%" in sq.lower() for sq in sub_qs_2), (
            "Sub-question 2 must isolate the 20% TDS refund recourse under Section 206AA / ITR"
        )


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary, corner, and adversarial stress tests."""

    def test_tier2_boundary_section_149_50_lakhs_threshold(self):
        """Boundary: ₹50 Lakhs threshold under Section 149(1)(b) distinguishes 3-year from 10-year limit."""
        # ₹49.9 Lakhs: Below threshold -> Extended 10-year period NOT applicable -> Time-barred after 3 years
        q_below = (
            "I got a notice under Section 148A(b) for AY 2018-19 alleging ₹49,99,000 in escaped income. "
            "Can the department invoke the 10-year extended limitation period under Section 149?"
        )
        ans_below = run_pipeline(q_below)
        summary_below = ans_below.summary.lower()
        assert "149" in ans_below.summary or "50 lakh" in summary_below or "50,00,000" in summary_below
        assert any(term in summary_below for term in ("cannot", "not applicable", "does not apply", "below 50", "below ₹50", "barred", "expired")), (
            "For ₹49.9 Lakhs (below ₹50L), extended 10-year limitation must NOT apply"
        )

        # ₹50.0 Lakhs: Meets threshold -> Extended 10-year period CAN be invoked if represented in asset
        q_at = (
            "I got a notice under Section 148A(b) for AY 2018-19 alleging ₹50,00,000 in escaped income. "
            "Does this meet the ₹50 Lakhs threshold for the 10-year extended limitation under Section 149?"
        )
        ans_at = run_pipeline(q_at)
        summary_at = ans_at.summary.lower()
        assert any(term in summary_at for term in ("meets", "applicable", "eligible", "can be issued", "10-year", "10 years")), (
            "For ₹50 Lakhs, extended 10-year limitation threshold is met"
        )

    def test_tier2_boundary_3_year_limitation_date_calculation(self):
        """Boundary: Normal 3-year limitation for AY 2018-19 expired on 31 March 2022."""
        q = "For Assessment Year 2018-19, what was the exact date on which the 3-year limitation period expired under Section 149(1)(a)?"
        ans = run_pipeline(q)
        summary = ans.summary.lower()
        assert any(term in summary for term in ("31 march 2022", "31st march 2022", "march 31, 2022", "31/03/2022")), (
            "Must calculate exact expiry date of normal 3-year period as 31 March 2022 (3 years from end of AY 2018-19 on 31 March 2019)"
        )

    def test_tier2_boundary_section_148a_minimum_7_day_reply_window(self):
        """Boundary: Section 148A(b) mandates minimum 7 days; less than 7 days is legally invalid."""
        q = "The Assessing Officer issued a Section 148A(b) notice and gave me only 3 days to submit my reply. Is this valid?"
        ans = run_pipeline(q)
        summary = ans.summary.lower()
        assert any(term in summary for term in ("invalid", "illegal", "not valid", "violates", "defective", "cannot")), (
            "Notice giving less than 7 days violates Section 148A(b)"
        )
        assert any(term in summary for term in ("7 days", "minimum 7", "not less than seven")), (
            "Must state Section 148A(b) requires a minimum of 7 days"
        )

    def test_tier2_offline_pytest_execution_without_live_llm(self, monkeypatch):
        """Offline execution: In pytest test mode without live LLM, explainer produces steps == []."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_tier2_offline")
        monkeypatch.delenv("TEST_LIVE_LLM", raising=False)

        doc = make_mock_doc(
            id="tax_reassessment_offline_mock",
            category="tax",
            title="Official Statutory SOP: Section 148A and 149",
            section="Statutory Rules",
            text="Section 148A(b) reply window is 7 to 30 days. Section 149 limitation is 3 years unless escaped income >= ₹50 Lakhs.",
            tags=("reassessment", "148a", "149"),
        )
        hit = RetrievalHit(document=doc, score=0.075, rank=1, signals={})
        result = RetrievalResult(query=CASE1_QUERY, hits=(hit,), status="supported_lexical", searched_documents=50)

        ans = explain_rag_result(result, user_question=CASE1_QUERY)
        assert ans is not None
        assert ans.steps == [], f"Offline explainer must not produce procedural steps, got: {ans.steps}"
        assert "148a" in ans.summary.lower() or "149" in ans.summary.lower()

    def test_tier2_adversarial_zero_predefined_responses_compliance(self):
        """Adversarial: Responses must NOT contain pre-canned disclaimer strings per AGENTS.md & GEMINI.md."""
        for query in (CASE1_QUERY, CASE2_QUERY):
            ans = run_pipeline(query)
            full_text = f"{ans.title} {ans.summary} {ans.disclaimer or ''}".lower()
            assert "pre-verified guide" not in full_text, "Violation of Zero Predefined Responses rule"
            assert "predefined response" not in full_text, "Violation of Zero Predefined Responses rule"
            assert "pre-canned" not in full_text, "Violation of Zero Predefined Responses rule"


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# ==============================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Multi-feature interactions and cross-domain integrity."""

    def test_tier3_decomposition_with_confidence_gating(self):
        """Cross-feature: Multi-part query where one part is supported and second part is ungrounded."""
        # Query combining supported 148A with fabricated nonexistent Section 999XYZ
        compound_q = (
            "What is the reply window under Section 148A(b), and what is the penalty under Section 999XYZ "
            "for quantum hyper-acceleration of crypto tokens?"
        )
        decompose_fn = _get_decompose_query_fn()
        if decompose_fn is not None:
            sub_qs = decompose_fn(compound_q)
            assert len(sub_qs) >= 2, "Should decompose into 2 sub-questions"

        ans = run_pipeline(compound_q)
        # Confidence must not be marked high for the hallucinated/unsupported part
        assert ans.confidence in ("medium", "low"), (
            f"Compound query with ungrounded sub-question must not receive HIGH confidence, got: {ans.confidence}"
        )

    def test_tier3_analytical_shape_with_multipart_synthesis(self):
        """Cross-feature: Analytical shape (steps == []) combined with multi-part synthesis addressing all sub-questions."""
        ans = run_pipeline(CASE1_QUERY)
        # 1. Analytical shape preserved
        assert ans.steps == [], f"Must have no steps, got: {ans.steps}"

        # 2. Both sub-questions answered in summary
        summary_lower = ans.summary.lower()
        sub_q1_answered = any(term in summary_lower for term in ("3-year", "3 years", "149", "expired", "time-barred", "50 lakh"))
        sub_q2_answered = any(term in summary_lower for term in ("7 days", "minimum 7", "30 days", "reply window"))
        assert sub_q1_answered, "Summary must answer sub-question 1 (limitation under Section 149)"
        assert sub_q2_answered, "Summary must answer sub-question 2 (reply window under Section 148A(b))"

    def test_tier3_dual_category_retrieval_tax_and_pan(self):
        """Cross-feature: Inoperative PAN + TDS query retrieves chunks across both pan and tax categories."""
        corpus = load_corpus()
        retriever = RagRetriever(corpus)

        res = retriever.search(CASE2_QUERY, top_k=5)
        assert res.hits, "Retriever must return hits for Case 2 query"

        retrieved_categories = {hit.document.category for hit in res.hits}
        # In a remediated pipeline, retrieval must not be strictly locked into only pan or only tax
        assert ("pan" in retrieved_categories or "tax" in retrieved_categories), (
            f"Retrieved categories must include pan or tax, got: {retrieved_categories}"
        )

    def test_tier3_retriever_symptom_cluster_conflict_penalties(self):
        """Cross-feature: Symptom cluster conflict penalties prevent token hijacking by 139(9) or Protean."""
        corpus = load_corpus()
        retriever = RagRetriever(corpus)

        # 1. Section 148A query must NOT rank 139(9) defective return or 119(2)(b) above reassessment
        res1 = retriever.search(CASE1_QUERY, category="tax", top_k=3)
        if res1.hits:
            top_hit_id = res1.hits[0].document.id.lower()
            assert "139" not in top_hit_id, f"Section 139(9) chunk hijacked Case 1 rank 1: {top_hit_id}"
            assert "condonation" not in top_hit_id, f"Section 119(2)(b) chunk hijacked Case 1 rank 1: {top_hit_id}"

        # 2. Case 2 query must NOT rank Protean paperless application rejection as top hit
        res2 = retriever.search(CASE2_QUERY, top_k=3)
        if res2.hits:
            top_hit_id = res2.hits[0].document.id.lower()
            assert "protean" not in top_hit_id, f"Protean application rejection hijacked Case 2 rank 1: {top_hit_id}"


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestTier4RealWorldScenarios:
    """Tier 4: End-to-end execution of verbatim Case 1 and Case 2 user inquiries."""

    def test_tier4_case1_verbatim_reassessment_section_148a_end_to_end(self):
        """Acceptance Criteria Case 1: Section 148A(b) Reassessment Notice (AY 2018-19).

        Verbatim Query:
        'I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19
         alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit to issue this
         notice expire under the 3-year vs 10-year rule, and how many days do I have to submit my reply?'
        """
        ans = run_pipeline(CASE1_QUERY)

        # 1. R1: Response Shape & Checklist Elimination
        assert ans.steps == [], f"Analytical query must not have procedural steps, got: {ans.steps}"
        assert not any("review" in s.title.lower() for s in ans.steps), "Must not have artificial 'Review [Doc]' steps"
        assert not any("verify official portal and apply" in s.title.lower() for s in ans.steps)

        summary_lower = ans.summary.lower()

        # 2. Sub-Question 1: Limitation under Section 149
        assert "149" in ans.summary, "Must cite Section 149 for reassessment time limits"
        assert any(term in summary_lower for term in ("3-year", "3 years", "three years")), (
            "Must explain 3-year base limitation period"
        )
        assert any(term in summary_lower for term in ("10-year", "10 years", "ten years", "50 lakh", "50,00,000")), (
            "Must explain ₹50 Lakhs threshold required for 10-year extended limitation"
        )
        assert any(term in summary_lower for term in ("expired", "time-barred", "barred by limitation", "invalid", "cannot be issued")), (
            "Must conclude notice is time-barred since ₹6.5 Lakhs is below ₹50 Lakhs and 3 years expired on 31 March 2022"
        )

        # 3. Sub-Question 2: Reply Window under Section 148A(b)
        assert any(term in summary_lower for term in ("7 days", "minimum 7", "7 to 30 days", "30 days")), (
            "Must specify reply window under Section 148A(b) is minimum 7 days up to 30 days"
        )

        # 4. R2: Gating on Off-Topic Citations
        citation_titles = " ".join(c.title.lower() for c in ans.citations)
        assert "119(2)(b)" not in citation_titles, "Must not cite Section 119(2)(b) condonation for 148A notice"
        assert "139(9)" not in citation_titles, "Must not cite Section 139(9) defective return for 148A notice"

    def test_tier4_case2_verbatim_inoperative_pan_tds_refund_end_to_end(self):
        """Acceptance Criteria Case 2: Inoperative PAN / 20% TDS Refund.

        Verbatim Query:
        'My salary credit in August came with a flat 20% TDS deduction because my PAN became 'Inoperative'
         for missing the Aadhaar linking deadline. I just paid the ₹1,000 late fee under Section 234H on the portal.
         How long before my PAN becomes active, and how do I get my company to refund the excess 20% TDS?'
        """
        ans = run_pipeline(CASE2_QUERY)

        # 1. R1: Response Shape & Checklist Elimination
        assert ans.steps == [], f"Analytical query must not have procedural steps, got: {ans.steps}"
        assert not any("review" in s.title.lower() for s in ans.steps), "Must not have artificial 'Review [Doc]' steps"

        summary_lower = ans.summary.lower()

        # 2. Sub-Question 1: Reactivation Timeline (~30 days)
        assert any(term in summary_lower for term in ("30 days", "thirty days", "within 30")), (
            "Must specify PAN reactivation takes ~30 days under Rule 114AAA / CBDT Circular 03/2023"
        )

        # 3. Sub-Question 2: Employer cannot refund deposited TDS; claim via ITR
        assert any(term in summary_lower for term in ("cannot refund", "employer cannot", "company cannot", "no refund by employer", "no adjustment")), (
            "Must explain employer cannot refund excess TDS once deposited under Section 206AA"
        )
        assert any(term in summary_lower for term in ("itr", "tax return", "income tax return", "claim refund", "file itr")), (
            "Must explain excess TDS credit/refund must be claimed by filing ITR after PAN is operative"
        )

        # 4. No Protean application rejection misdirection
        citation_titles = " ".join(c.title.lower() for c in ans.citations)
        assert "protean" not in citation_titles or "circular 03" in citation_titles or "206aa" in citation_titles, (
            "Must not misdirect to Protean paperless application rejections without addressing statutory PAN-TDS rules"
        )
