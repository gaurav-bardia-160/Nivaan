"""Unit tests for Domain Router and Domain Classification."""
from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.config import DATA_DIR
from backend.modules.domain_router import (
    Domain,
    classify_domain,
    entry_matches_domain,
    get_allowed_rag_categories,
)
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
    def test_domain_enum_members(self):
        assert Domain.TRANSPORT == "transport"
        assert Domain.EDUCATION == "education"
        assert Domain.IDENTITY == "identity"
        assert Domain.TAXATION == "taxation"
        assert Domain.BANKING == "banking"
        assert Domain.AGRICULTURE == "agriculture"
        assert Domain.LEGAL_CONSUMER == "legal_consumer"
        assert Domain.GENERAL_CIVIC == "general_civic"
        assert Domain.UNKNOWN == "unknown"
        # UNCOVERED has been completely removed
        assert not hasattr(Domain, "UNCOVERED")

    def test_domain_equality_with_string(self):
        assert Domain("banking") is Domain.BANKING
        assert Domain("transport") is Domain.TRANSPORT


class TestClassifyDomainStandardPatterns:
    @pytest.mark.parametrize(
        "query,expected_domain",
        [
            ("Passport banne me kitne din lagte hai?", Domain.IDENTITY),
            ("Driving license kitne din me aayega?", Domain.TRANSPORT),
            ("Voter ID card kitne din me banta hai?", Domain.IDENTITY),
            ("Aadhaar card update hone me kitne din lagte hain?", Domain.IDENTITY),
            ("PAN card kitne din me banega?", Domain.IDENTITY),
            ("Spice jet complaint in consumer court", Domain.LEGAL_CONSUMER),
            ("How to check FASTag balance and dispute toll charge", Domain.TRANSPORT),
            ("Section 138 cheque bounce legal notice limitation period", Domain.LEGAL_CONSUMER),
            ("ITR defective notice 139(9) correction procedure", Domain.TAXATION),
            ("Savings bank account minimum balance charges RBI guidelines", Domain.BANKING),
        ],
    )
    def test_domain_classification(self, query: str, expected_domain: Domain):
        domain = classify_domain(query)
        assert domain == expected_domain

    @pytest.mark.parametrize(
        "query",
        [
            "How to register a private limited company on MCA portal?",
            "Application status for Director Identification Number (DIN)",
            "SPICe+ Part A company name reservation Rule 8A",
            "ROC incorporation filing INC-32 SPICe plus",
            "How to book an LPG cylinder online through HP Gas?",
            "Indane domestic gas cylinder refill booking failed",
            "NSP portal scholarship application status",
            "National Scholarship Portal pre-matric scholarship verification",
        ],
    )
    def test_previously_uncovered_queries_do_not_raise_and_route_naturally(self, query: str):
        # With Domain.UNCOVERED removed, queries route naturally to covered or unknown domain without crashing
        domain = classify_domain(query)
        assert isinstance(domain, Domain)
        assert domain != "uncovered"


class TestGetAllowedRagCategories:
    def test_covered_domains_return_expected_categories(self):
        assert get_allowed_rag_categories(Domain.TRANSPORT) == {"civic"}
        assert get_allowed_rag_categories(Domain.EDUCATION) == {"civic"}
        assert get_allowed_rag_categories(Domain.TAXATION) == {"tax", "civic"}
        assert get_allowed_rag_categories(Domain.IDENTITY) == {"aadhaar", "pan", "civic"}
        assert get_allowed_rag_categories(Domain.BANKING) == {"banking", "civic"}


class TestEntryMatchesDomain:
    def test_matches_valid_entry(self):
        assert entry_matches_domain("pan_card_new", "pan", Domain.IDENTITY)
        assert entry_matches_domain("fastag_toll_dispute_refund", "civic", Domain.TRANSPORT)
        assert entry_matches_domain("itr_filing_basics", "tax", Domain.TAXATION)

    def test_rejects_cross_domain_entry(self):
        assert not entry_matches_domain("pan_card_new", "pan", Domain.TRANSPORT)
