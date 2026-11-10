"""Empirical Adversarial Verification Suite for Milestone M1 - Case 1.

Agent: challenger_cases_m1_1 (critic, specialist)
Mission: Stress-test retriever ranking, anti-hijacking conflict suppression,
statutory precision, and domain routing for Section 148A Reassessment Notice.
"""
from __future__ import annotations

import re
from pathlib import Path
import pytest

from backend.modules.domain_router import Domain, classify_domain
from backend.rag.loader import load_corpus
from backend.rag.retriever import RagRetriever

CASE1_QUERY = (
    "I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 "
    "alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit to issue this "
    "notice expire under the 3-year vs 10-year rule, and how many days do I have to submit my reply?"
)

EXPECTED_DOC_ID = "tax_reassessment_section_148a_149_limitation_procedure"


def is_reassessment_doc(doc) -> bool:
    """Check if document matches the canonical Section 148A reassessment record."""
    if doc.sources and any(s.record_id == EXPECTED_DOC_ID for s in doc.sources):
        return True
    return str(doc.id) == EXPECTED_DOC_ID


def get_doc_label(doc) -> str:
    """Return human-readable document record ID."""
    if doc.sources and doc.sources[0].record_id:
        return doc.sources[0].record_id
    return str(doc.id)


@pytest.fixture(scope="module")
def retriever():
    corpus = load_corpus()
    return RagRetriever(corpus)


class TestEmpiricalCase1RetrieverRanking:
    """1. Confirm that Section 148A queries rank reassessment record at Rank 1."""

    def test_verbatim_case1_query_ranks_reassessment_at_rank1(self, retriever):
        """Verbatim Case 1 query must rank the Section 148A/149 record at Rank 1."""
        res = retriever.search(CASE1_QUERY, top_k=5)
        assert res.hits, "Search must return at least one hit"
        top_hit = res.hits[0]
        assert is_reassessment_doc(top_hit.document), (
            f"Expected Rank 1 to be reassessment document, but got '{get_doc_label(top_hit.document)}' (id: {top_hit.document.id})"
        )
        assert top_hit.rank == 1
        assert top_hit.score > 0.05, f"Score should reflect strong match, got {top_hit.score}"

    @pytest.mark.parametrize(
        "query,desc",
        [
            ("Section 148A(b) reply deadline", "Direct section + sub-clause"),
            ("Section 149 3-year vs 10-year ₹50 Lakhs limit AY 2018-19", "Limitation query with thresholds"),
            ("got 148a notice for 6.5 lakh share trading, is it time barred?", "Informal casing and phrasing"),
            ("income tax section 148a notice aaya hai 6.5 lakh trading ke liye time limit expired", "Hinglish query"),
            ("148A show cause notice procedure and timeline to reply to AO", "Procedural show-cause query"),
            ("Section 148 notice for AY 2018-19 escaped income", "General 148 reassessment notice"),
        ],
    )
    def test_paraphrased_and_informal_queries_rank_at_rank1(self, retriever, query, desc):
        """Paraphrased, informal, and section variants must reliably rank reassessment record at Rank 1."""
        res = retriever.search(query, top_k=5)
        assert res.hits, f"Search returned no hits for: {query}"
        top_hit = res.hits[0]
        assert is_reassessment_doc(top_hit.document), (
            f"Failed on '{desc}': expected reassessment doc at Rank 1, got '{get_doc_label(top_hit.document)}'"
        )


class TestEmpiricalAntiHijackingConflictResistance:
    """2. Stress-test adversarial token mixtures against 139(9) and 119(2)(b) hijacking."""

    @pytest.mark.parametrize(
        "adversarial_query,trap_terms",
        [
            (
                "I received a defective notice under Section 148A(b) alleging defect in unexplained transactions. What is the reply window?",
                ("defective", "defect", "139(9)"),
            ),
            (
                "Notice under Section 148A for escaped income with delayed filing defect and condonation of delay",
                ("condonation", "delayed filing", "119(2)(b)"),
            ),
            (
                "Section 148A reassessment notice for AY 2018-19 ₹6.5 Lakhs delayed reply condonation under 119(2)(b)",
                ("119(2)(b)", "condonation"),
            ),
            (
                "Is Section 148A show cause notice defective if given only 3 days instead of 7 days? Can I file rectification?",
                ("defective", "rectification"),
            ),
            (
                "This is NOT a defective return under Section 139(9), it is a 148A reassessment notice for share trading",
                ("139(9)", "defective return"),
            ),
        ],
    )
    def test_adversarial_token_mixtures_resist_hijacking(self, retriever, adversarial_query, trap_terms):
        """Adversarial queries containing trap words ('defect', 'condonation', '139(9)') must NOT be hijacked."""
        res = retriever.search(adversarial_query, top_k=5)
        assert res.hits, f"Search returned no hits for: {adversarial_query}"

        # Rank 1 MUST be the 148A reassessment document
        top_hit = res.hits[0]
        assert is_reassessment_doc(top_hit.document), (
            f"Hijacked by {get_doc_label(top_hit.document)} for query '{adversarial_query}'. "
            f"Expected {EXPECTED_DOC_ID} at Rank 1."
        )

        # Confirm any 139(9) or 119(2)(b) chunks in candidates received contamination penalties
        # Check that conflicting documents are ranked lower
        for hit in res.hits[1:]:
            label = get_doc_label(hit.document).lower()
            if "139" in label or "condonation" in label:
                penalty = hit.signals.get("contamination_penalty")
                assert penalty == -0.40, (
                    f"Conflicting hit {label} was not penalized with -0.40, got {penalty}"
                )


class TestEmpiricalStatutoryContentFidelity:
    """3. Verify statutory accuracy of the retrieved chunk."""

    def test_statutory_thresholds_and_dates_in_chunk(self, retriever):
        """The retrieved chunk must contain all critical statutory provisions required for Case 1."""
        doc = retriever.documents_by_id.get(EXPECTED_DOC_ID)
        assert doc is not None, f"Document '{EXPECTED_DOC_ID}' not found in corpus"

        source = doc.sources[0]
        full_text = f"{source.title} {source.section} {doc.text}".lower()

        # 1. Section 148A(b) Reply Window: 7 to 30 days
        assert "7 to 30 days" in full_text or ("not less than seven days" in full_text and "thirty days" in full_text)
        assert "less than 7 days is legally invalid" in full_text or "invalid" in full_text

        # 2. Section 149(1)(a) Normal 3-Year Limitation
        assert "3 years" in full_text or "3-year" in full_text
        assert "31 march 2022" in full_text, "Chunk must explicitly specify 31 March 2022 expiry for AY 2018-19"

        # 3. Section 149(1)(b) Extended 10-Year Limitation & ₹50 Lakhs Threshold
        assert "10 years" in full_text or "10-year" in full_text
        assert "50 lakh" in full_text or "50,00,000" in full_text

        # 4. Explicit application to ₹6.5 Lakhs
        assert "6.5 lakh" in full_text
        assert "time-barred" in full_text or "barred by limitation" in full_text

        # 5. Section 151 Sanction by Specified Authority
        assert "151" in full_text
        assert "specified authority" in full_text

        # 6. Official Portal Provenance
        assert any("incometax.gov.in" in (s.source_url or "") for s in doc.sources)
        assert doc.category == "tax"


class TestEmpiricalDomainRoutingPrecision:
    """4. Verify Domain Router maps all Case 1 variations into Domain.TAXATION."""

    @pytest.mark.parametrize(
        "query",
        [
            CASE1_QUERY,
            "Notice under Section 148A(b) for AY 2018-19 alleging unexplained share trading",
            "Did time limit expire under Section 149 for reassessment notice?",
            "Section 148 reassessment notice time-barred after 3 years",
            "Escaped income ₹6.5 Lakhs under Section 147 and 151 sanction",
            "148a show cause notice reply days",
            "section 148a(d) order passed by assessing officer",
        ],
    )
    def test_domain_router_routes_to_taxation(self, query):
        domain = classify_domain(query)
        assert domain == Domain.TAXATION, f"Query '{query}' expected Domain.TAXATION, got {domain}"


class TestEmpiricalScoreMarginAndSignals:
    """5. Verify score safety margin between Rank 1 and nearest distractor."""

    def test_rank1_signals_and_safety_margin(self, retriever):
        """Rank 1 must have substantial positive score margin over Rank 2."""
        res = retriever.search(CASE1_QUERY, top_k=5)
        assert len(res.hits) >= 2, "Expected at least 2 hits"
        rank1 = res.hits[0]
        rank2 = res.hits[1]

        # Verify boost signals on Rank 1
        assert rank1.signals.get("exact_statutory_boost") == 0.12, (
            f"Expected exact_statutory_boost == 0.12, got {rank1.signals.get('exact_statutory_boost')}"
        )
        assert rank1.signals.get("symptom_boost") == 0.08, (
            f"Expected symptom_boost == 0.08, got {rank1.signals.get('symptom_boost')}"
        )

        margin = rank1.score - rank2.score
        # Reassessment doc must dominate nearest distractor
        assert margin >= 0.15, (
            f"Safety margin between Rank 1 ({rank1.score:.4f}) and Rank 2 ({rank2.score:.4f}) "
            f"is {margin:.4f}, expected >= 0.15"
        )

    def test_reassessment_query_without_explicit_section_number(self, retriever):
        """Query describing facts (reassessment, escaped income, AY 2018-19, 6.5 lakh) without citing section numbers."""
        q = "reassessment notice for FY 2017-18 AY 2018-19 alleging unexplained share trading 6.5 lakh after 4 years, can AO reopen assessment?"
        res = retriever.search(q, top_k=5)
        assert res.hits, "Search returned no hits"
        top_hit = res.hits[0]
        assert is_reassessment_doc(top_hit.document), (
            f"Expected reassessment document at Rank 1 even without explicit section number, got '{get_doc_label(top_hit.document)}'"
        )
