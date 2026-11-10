"""Empirical Adversarial Verification and Stress Test Suite for Case 2.

Agent: challenger_cases_m1_2
Target: Milestone M1 (Corpus Ingestion & Retriever Coverage for Case 2: Inoperative PAN / Section 206AA 20% TDS)

Empirical Challenge Dimensions:
1. Retriever ranking for verbatim Case 2 query and adversarial variations.
2. Dual-category retrieval bringing both Circular 03/2023 and Section 206AA ITR refund records into top hits.
3. Anti-hijacking conflict penalty suppressing Protean TIN-NSDL application rejection from Rank 1.
4. Statutory fact accuracy across Rule 114AAA, Circular 03/2023, Section 234H, and Section 206AA.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.modules.domain_router import (
    Domain,
    classify_domain,
    get_allowed_rag_categories,
)
from backend.rag.loader import load_corpus
from backend.rag.retriever import RagRetriever

CASE2_VERBATIM = (
    "My salary credit in August came with a flat 20% TDS deduction because my PAN became 'Inoperative' "
    "for missing the Aadhaar linking deadline. I just paid the ₹1,000 late fee under Section 234H on the portal. "
    "How long before my PAN becomes active, and how do I get my company to refund the excess 20% TDS?"
)

CIRCULAR_DOC_ID = "pan_inoperative_aadhaar_linking_circular_03_2023"
REFUND_DOC_ID = "tax_tds_section_206aa_inoperative_pan_refund_workflow"
PROTEAN_DOC_ID = "pan_protean_application_troubleshooting_01"


@pytest.fixture(scope="module")
def retriever():
    corpus = load_corpus()
    return RagRetriever(corpus)


def _get_hit_record_id(hit) -> str:
    if hit.document.sources and hit.document.sources[0].record_id:
        return hit.document.sources[0].record_id
    return str(hit.document.id)


class TestVerbatimCase2Empirical:
    """Empirical verification of verbatim Case 2 query ranking and category balance."""

    def test_verbatim_case2_retrieves_both_statutory_documents_in_top_hits(self, retriever: RagRetriever):
        result = retriever.search(CASE2_VERBATIM, top_k=5)
        assert result.hits, "Retriever returned no hits for verbatim Case 2 query"

        hit_record_ids = [_get_hit_record_id(hit) for hit in result.hits]
        hit_categories = {hit.document.category for hit in result.hits}

        # Assert both required documents are in top hits
        assert CIRCULAR_DOC_ID in hit_record_ids, (
            f"Circular 03/2023 document ({CIRCULAR_DOC_ID}) missing from top hits: {hit_record_ids}"
        )
        assert REFUND_DOC_ID in hit_record_ids, (
            f"Section 206AA refund document ({REFUND_DOC_ID}) missing from top hits: {hit_record_ids}"
        )

        # Assert dual-category retrieval works
        assert "pan" in hit_categories, f"'pan' category missing from retrieved hits: {hit_categories}"
        assert "tax" in hit_categories, f"'tax' category missing from retrieved hits: {hit_categories}"

        # Assert top 2 hits are the two target statutory documents
        top2_ids = hit_record_ids[:2]
        assert CIRCULAR_DOC_ID in top2_ids, f"{CIRCULAR_DOC_ID} is not in top 2 hits: {hit_record_ids}"
        assert REFUND_DOC_ID in top2_ids, f"{REFUND_DOC_ID} is not in top 2 hits: {hit_record_ids}"

    def test_verbatim_case2_penalizes_protean_rejection(self, retriever: RagRetriever):
        result = retriever.search(CASE2_VERBATIM, top_k=10)
        assert result.hits

        # Top hit must NOT be Protean rejection
        top_rec_id = _get_hit_record_id(result.hits[0])
        assert top_rec_id != PROTEAN_DOC_ID, (
            f"Protean rejection hijacked Rank 1 for Case 2 query! Top hit: {top_rec_id}"
        )
        assert "protean" not in top_rec_id.lower()

        # If Protean is retrieved in candidates, verify conflict penalty was applied
        for hit in result.hits:
            if hit.document.id == PROTEAN_DOC_ID:
                assert "conflict_penalty" in hit.signals or hit.signals.get("conflict_penalty", 0) < 0, (
                    f"Protean hit did not receive negative conflict penalty: {hit.signals}"
                )


class TestAdversarialQueryVariations:
    """Stress-test retriever ranking across adversarial variations and natural queries."""

    ADVERSARIAL_CASES = [
        (
            "Natural conversational without section citations",
            "My PAN became inoperative because I forgot to link Aadhaar. August salary got 20% TDS deduction. "
            "I paid the 1000 rupee late fee. When will it become operative and how can I get my company to refund?",
            True,  # expect both docs
        ),
        (
            "Concise query",
            "inoperative PAN 20% salary TDS refund and reactivation timeline 1000 fee",
            True,
        ),
        (
            "Taxpayer asking about employer payroll adjustment",
            "Can employer refund or adjust 20% TDS deducted under Section 206AA on salary due to inoperative PAN?",
            False,  # primarily refund doc, circular may or may not be top 2
        ),
        (
            "Taxpayer asking about reactivation timeline and fee only",
            "How long before inoperative PAN becomes active after paying 1000 penalty under Section 234H Circular 03/2023?",
            False,  # primarily circular doc
        ),
        (
            "Hinglish / informal conversational query",
            "Mera PAN inoperative ho gaya aur salary me se 20% TDS cut ho gaya. 1000 fees pay kar di. "
            "Kab tak PAN active hoga aur 20% TDS refund kaise milega company se?",
            True,
        ),
        (
            "Adversarial bait mentioning Protean and tracking",
            "Protean TIN-NSDL paperless application status inoperative PAN 20% TDS refund Aadhaar link",
            True,
        ),
        (
            "Bank FD interest 20% TDS deduction on inoperative PAN",
            "Bank deducted 20% TDS on FD interest under Section 206AA because PAN is inoperative. How to refund?",
            False,
        ),
    ]

    @pytest.mark.parametrize("desc,query,expect_both", ADVERSARIAL_CASES)
    def test_adversarial_queries_ranking_and_anti_hijacking(
        self, retriever: RagRetriever, desc: str, query: str, expect_both: bool
    ):
        result = retriever.search(query, top_k=5)
        assert result.hits, f"Retriever returned no hits for '{desc}'"

        top_rec_id = _get_hit_record_id(result.hits[0])
        assert top_rec_id != PROTEAN_DOC_ID, (
            f"Protean rejection hijacked Rank 1 for '{desc}'! Query: {query}, Top hit: {top_rec_id}"
        )
        assert "protean" not in top_rec_id.lower()

        hit_ids = [_get_hit_record_id(hit) for hit in result.hits]
        if expect_both:
            assert CIRCULAR_DOC_ID in hit_ids, (
                f"For '{desc}', expected {CIRCULAR_DOC_ID} in top hits: {hit_ids}"
            )
            assert REFUND_DOC_ID in hit_ids, (
                f"For '{desc}', expected {REFUND_DOC_ID} in top hits: {hit_ids}"
            )
        else:
            # At least one of the target statutory documents must be in top 2 hits
            assert any(doc_id in hit_ids[:2] for doc_id in (CIRCULAR_DOC_ID, REFUND_DOC_ID)), (
                f"For '{desc}', neither statutory doc is in top 2 hits: {hit_ids[:2]}"
            )


class TestDomainRoutingAndDualCategoryAccess:
    """Verify domain router and category resolution contracts for Case 2."""

    def test_verbatim_query_routing_and_category_expansion(self):
        domain = classify_domain(CASE2_VERBATIM)
        assert domain in (Domain.TAXATION, Domain.IDENTITY), f"Unexpected domain: {domain}"

        allowed = get_allowed_rag_categories(domain, query=CASE2_VERBATIM)
        assert allowed is not None
        assert "pan" in allowed, f"'pan' not in allowed categories: {allowed}"
        assert "tax" in allowed, f"'tax' not in allowed categories: {allowed}"

    @pytest.mark.parametrize(
        "query",
        [
            "inoperative PAN salary 20% TDS deduction refund",
            "Section 206AA flat 20% TDS on inoperative PAN refund via ITR",
            "Rule 114AAA Circular 03/2023 inoperative PAN 30 days reactivation Section 234H",
            "Company deducted 20% TDS because PAN became inoperative for not linking Aadhaar",
        ],
    )
    def test_query_variants_receive_dual_category_access(self, query: str):
        domain = classify_domain(query)
        allowed = get_allowed_rag_categories(domain, query=query)
        assert allowed is not None
        assert "tax" in allowed, f"Query '{query}' did not get 'tax' category: {allowed}"
        assert "pan" in allowed, f"Query '{query}' did not get 'pan' category: {allowed}"


class TestLegalGroundTruthIntegrity:
    """Empirically inspect canonical documents to confirm statutory fact correctness."""

    def test_circular_03_2023_canonical_facts(self):
        pan_path = Path("backend/data/refined/troubleshooting/troubleshooting_pan.jsonl")
        records = [json.loads(line) for line in pan_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        circular_rec = next((r for r in records if r["id"] == CIRCULAR_DOC_ID), None)

        assert circular_rec is not None, f"Document {CIRCULAR_DOC_ID} not found in {pan_path}"
        text = circular_rec["text"].lower()

        # 1. Circular citation and Rule 114AAA
        assert "03/2023" in text or "circular no. 03" in text, "Missing Circular 03/2023 reference"
        assert "114aaa" in text, "Missing Rule 114AAA reference"

        # 2. 30-day reactivation timeline
        assert "30 days" in text or "thirty (30) days" in text, "Missing 30-day reactivation timeline"

        # 3. Section 234H and Rs 1,000 late fee
        assert "234h" in text, "Missing Section 234H reference"
        assert "1,000" in text or "1000" in text, "Missing Rs 1,000 fee reference"

        # 4. Section 206AA higher rate TDS consequence
        assert "206aa" in text, "Missing Section 206AA consequence reference"
        assert "20%" in text or "twenty" in text or "higher rate" in text, "Missing 20% TDS rate"

    def test_section_206aa_refund_canonical_facts(self):
        tax_path = Path("backend/data/refined/troubleshooting/troubleshooting_tax.jsonl")
        records = [json.loads(line) for line in tax_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        refund_rec = next((r for r in records if r["id"] == REFUND_DOC_ID), None)

        assert refund_rec is not None, f"Document {REFUND_DOC_ID} not found in {tax_path}"
        text = refund_rec["text"].lower()

        # 1. Section 206AA and flat 20% TDS
        assert "206aa" in text, "Missing Section 206AA citation"
        assert "20%" in text, "Missing 20% TDS rate"

        # 2. Employer cannot refund deposited TDS
        assert "cannot refund" in text or "no refund by employer" in text, (
            "Must state employer cannot refund deposited TDS via payroll"
        )

        # 3. Employee remedy: ITR filing
        assert "itr" in text or "income tax return" in text, "Must specify refund is claimed via ITR"
        assert "26as" in text or "ais" in text, "Must specify checking Form 26AS / AIS"
        assert "143(1)" in text, "Must specify CPC processing under Section 143(1)"
