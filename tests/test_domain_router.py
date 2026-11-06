"""Unit tests for Domain Router and Hard Domain Routing Bleed Prevention (R2)."""
from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.config import DATA_DIR
from backend.modules.domain_router import (
    Domain,
    _UNCOVERED_DOMAIN_PATTERNS,
    classify_domain,
    entry_matches_domain,
    get_allowed_rag_categories,
)
from backend.modules.unresolved_queue import UNRESOLVED_CSV_PATH
from backend.pipeline import run_pipeline, run_stream
from backend.rag.loader import load_corpus
from backend.rag.retriever import RagRetriever
from backend.rag.runtime import retrieve_if_enabled, supported_category
from backend.schemas import AskRequest


@pytest.fixture(scope="module")
def shared_corpus():
    return load_corpus()


@pytest.fixture(scope="module")
def retriever(shared_corpus):
    return RagRetriever(shared_corpus)


class TestDomainEnum:
    def test_uncovered_enum_exists(self):
        assert hasattr(Domain, "UNCOVERED")
        assert Domain.UNCOVERED == "uncovered"
        assert Domain.UNCOVERED.value == "uncovered"

    def test_domain_equality_with_string(self):
        assert Domain("uncovered") is Domain.UNCOVERED


class TestClassifyDomainUncoveredPatterns:
    @pytest.mark.parametrize(
        "query",
        [
            "How to register a private limited company on MCA portal?",
            "Application status for Director Identification Number (DIN)",
            "SPICe+ Part A company name reservation Rule 8A",
            "ROC incorporation filing INC-32 SPICe plus",
            "DIR-3 KYC verification process on MCA21",
            "Filing MGT-7 annual return on corporate affairs portal",
            "How to check CIN of a company on MCA?",
        ],
    )
    def test_mca_spice_classification(self, query: str):
        assert classify_domain(query) == Domain.UNCOVERED

    @pytest.mark.parametrize(
        "query",
        [
            "How to book an LPG cylinder online through HP Gas?",
            "Indane domestic gas cylinder refill booking failed",
            "Bharat Gas subsidy not credited into bank account under PAHAL",
            "DBTL Aadhaar seeding for subsidized LPG cylinder",
            "Commercial gas cylinder connection price list OMC",
            "Escalation under MoPNG grievance matrix for delayed refill",
            "Surrender domestic LPG connection",
        ],
    )
    def test_petroleum_lpg_classification(self, query: str):
        assert classify_domain(query) == Domain.UNCOVERED

    @pytest.mark.parametrize(
        "query",
        [
            "NSP portal scholarship application status",
            "National Scholarship Portal pre-matric scholarship verification",
            "Post-matric scholarship disbursement tracking on scholarships.gov.in",
            "Merit-cum-means scholarship renewal deadline on NSP",
            "Scholarship scheme nodal officer verification pending on NSP",
        ],
    )
    def test_nsp_scholarships_classification(self, query: str):
        assert classify_domain(query) == Domain.UNCOVERED

    @pytest.mark.parametrize(
        "query,expected_covered_domain",
        [
            ("Passport banne me kitne din lagte hai?", Domain.IDENTITY),
            ("Driving license kitne din me aayega?", Domain.TRANSPORT),
            ("Voter ID card kitne din me banta hai?", Domain.IDENTITY),
            ("Aadhaar card update hone me kitne din lagte hain?", Domain.IDENTITY),
            ("PAN card kitne din me banega?", Domain.IDENTITY),
            ("Spice jet complaint in consumer court", Domain.LEGAL_CONSUMER),
        ],
    )
    def test_hindi_din_and_context_do_not_route_to_uncovered(self, query: str, expected_covered_domain: Domain):
        domain = classify_domain(query)
        assert domain != Domain.UNCOVERED
        assert domain == expected_covered_domain

    @pytest.mark.parametrize(
        "query",
        [
            "how to incorporate a company in India",
            "how to incorporate a new company",
            "company incorporation process",
            "one person company registration",
            "company registration online",
            "llp registration process",
            "cylinder delivery delay",
            "cooking gas connection application",
            "cooking gas subsidy",
            "bharatgas online booking",
            "hpgas booking",
            "pre matric scholarship",
            "post matric scholarship",
            "merit cum means scholarship",
        ],
    )
    def test_expanded_uncovered_variations(self, query: str):
        assert classify_domain(query) == Domain.UNCOVERED

    def test_uncovered_precedence_over_generic_trouble_words(self):
        # Query containing banking, tax, and civic trouble tokens, but addressing MCA/SPICe+
        q = "Payment failed and pending error for SPICe+ filing on MCA portal with defect notice"
        assert classify_domain(q) == Domain.UNCOVERED

    def test_uncovered_precedence_over_banking_terms(self):
        q = "LPG subsidy failed to credit in dormant savings bank account"
        assert classify_domain(q) == Domain.UNCOVERED

    def test_uncovered_precedence_over_tax_terms(self):
        q = "Defective notice on NSP pre-matric scholarship application"
        assert classify_domain(q) == Domain.UNCOVERED


class TestGetAllowedRagCategories:
    def test_uncovered_returns_empty_set(self):
        assert get_allowed_rag_categories(Domain.UNCOVERED) == set()
        assert get_allowed_rag_categories("uncovered") == set()

    def test_covered_domains_return_non_empty(self):
        assert get_allowed_rag_categories(Domain.TRANSPORT) == {"civic"}
        assert get_allowed_rag_categories(Domain.EDUCATION) == {"civic"}
        assert get_allowed_rag_categories(Domain.TAXATION) == {"tax", "civic"}
        assert get_allowed_rag_categories(Domain.IDENTITY) == {"aadhaar", "pan", "civic"}


class TestEntryMatchesDomain:
    def test_uncovered_never_matches_any_entry(self):
        assert not entry_matches_domain("pan_card_new", "pan", Domain.UNCOVERED)
        assert not entry_matches_domain("fastag_toll_dispute_refund", "civic", Domain.UNCOVERED)
        assert not entry_matches_domain("itr_filing_basics", "tax", Domain.UNCOVERED)


class TestRetrieverShortCircuit:
    def test_short_circuit_with_explicit_domain_enum(self, retriever):
        mock_vs = MagicMock()
        retriever_with_mock = RagRetriever(
            retriever.load_result,
            embedding_provider=MagicMock(),
            vector_store=mock_vs,
        )
        res = retriever_with_mock.search(
            "How to file SPICe+ Part A on MCA portal?",
            domain=Domain.UNCOVERED,
        )
        assert res.status == "uncovered_domain"
        assert res.hits == ()
        assert res.searched_documents == 0
        # Mock vector store must NOT have been called
        mock_vs.search.assert_not_called()

    def test_short_circuit_with_domain_string(self, retriever):
        res = retriever.search(
            "Indane gas cylinder booking failed",
            domain="uncovered",
        )
        assert res.status == "uncovered_domain"
        assert res.hits == ()
        assert res.searched_documents == 0

    def test_short_circuit_with_implicit_classification(self, retriever):
        # Even without domain argument, query classifies as UNCOVERED and short-circuits
        res = retriever.search("Pre-matric scholarship disbursement status on NSP portal")
        assert res.status == "uncovered_domain"
        assert res.hits == ()
        assert res.searched_documents == 0

    def test_caller_passed_domain_cannot_bypass_uncovered(self, retriever):
        # Caller passing domain=Domain.GENERAL_CIVIC or "general_civic" must not bypass uncovered short-circuit
        res = retriever.search(
            "How to file SPICe+ Part A on MCA portal?",
            domain=Domain.GENERAL_CIVIC,
        )
        assert res.status == "uncovered_domain"
        assert res.hits == ()
        assert res.searched_documents == 0

        res_str = retriever.search(
            "Bharat Gas subsidy not credited into bank account under PAHAL",
            domain="general_civic",
        )
        assert res_str.status == "uncovered_domain"
        assert res_str.hits == ()
        assert res_str.searched_documents == 0


class TestRuntimeUncoveredIsolation:
    def test_supported_category_returns_none_for_uncovered(self):
        assert supported_category("NSP pre-matric scholarship verification") is None
        assert supported_category("LPG cylinder refill booking on HP Gas") is None
        assert supported_category("MCA SPICe+ company registration") is None

    def test_retrieve_if_enabled_returns_none_for_uncovered(self):
        assert retrieve_if_enabled("NSP scholarship status pending") is None
        assert retrieve_if_enabled("LPG cylinder refill booking", domain=Domain.UNCOVERED) is None
        assert retrieve_if_enabled("MCA SPICe+ incorporation", domain="uncovered") is None


class TestPipelineUncoveredRefusal:
    def test_run_pipeline_uncovered_refusal(self):
        q = "How do I file Form INC-32 SPICe+ on the MCA21 portal?"
        ans = run_pipeline(q)
        assert ans.confidence == "low"
        assert ans.citations == []
        assert ans.source_url is None
        # Summary must be an honest refusal explaining lack of canonical knowledge
        assert "not covered" in ans.summary.lower()
        # Strictly no canned "pre-verified guide" disclaimers
        assert "pre-verified guide" not in ans.summary.lower()
        assert "pre-canned" not in ans.summary.lower()
        # Must not cross-bleed into unrelated domains
        assert "epfo" not in ans.summary.lower()
        assert "139(9)" not in ans.summary

    @pytest.mark.parametrize(
        "query,expected_domain_fragment,unexpected_domain_fragment",
        [
            (
                "What is the NSP scholarship application process?",
                "National Scholarship Portal",
                "Ministry of Corporate Affairs",
            ),
            (
                "NSP scholarship pending verification",
                "National Scholarship Portal",
                "Ministry of Corporate Affairs",
            ),
            (
                "How to apply for LPG cylinder under the new procedure?",
                "Petroleum and LPG cylinder",
                "Ministry of Corporate Affairs",
            ),
        ],
    )
    def test_refusal_labels_domain_accurately_without_substring_collision(
        self,
        query: str,
        expected_domain_fragment: str,
        unexpected_domain_fragment: str,
    ):
        ans = run_pipeline(query)
        assert expected_domain_fragment in ans.summary
        assert unexpected_domain_fragment not in ans.summary

    def test_run_stream_uncovered_refusal(self):
        q = "How to surrender domestic LPG gas cylinder connection?"
        events = list(run_stream(AskRequest(question=q)))
        event_types = [e["event"] for e in events]
        assert "meta" in event_types
        assert "token" in event_types
        assert "done" in event_types

        done_event = next(e for e in events if e["event"] == "done")
        ans_data = done_event["data"]["answer"]
        assert ans_data["confidence"] == "low"
        assert "not covered" in ans_data["summary"].lower()

    def test_unresolved_queries_logged(self, tmp_path):
        q = "Test unique query for MCA Director Identification Number DIN verification"
        run_pipeline(q)
        # Verify it was appended to unresolved_queries.csv
        assert UNRESOLVED_CSV_PATH.exists()
        content = UNRESOLVED_CSV_PATH.read_text(encoding="utf-8")
        assert "uncovered_domain" in content
        assert "Director Identification Number" in content
