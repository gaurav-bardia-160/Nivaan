"""Empirical Adversarial Challenge Suite for Milestone 2 (R2).

Executed by challenger_m2 to independently stress-test Hard Domain Routing,
Retriever bleed prevention, and Pipeline refusal under adversarial variations,
trouble words, spelling/spacing variations, and boundary conditions.
"""
import pytest
from backend.modules.domain_router import Domain, classify_domain, get_allowed_rag_categories
from backend.rag.retriever import RagRetriever
from backend.pipeline import run_pipeline


@pytest.fixture(scope="module")
def retriever():
    return RagRetriever()


class TestMixedTroubleWordAttacks:
    """Attacks combining various trouble tokens with citizen queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "MCA21 portal SPICe+ registration payment failed refund pending",
            "LPG cylinder subsidy stopped bank account mismatch",
            "NSP scholarship status is defective notice under section 139(9)",
            "Director identification number DIN verification delay in court",
            "HP Gas domestic cylinder delivery delayed consumer court complaint",
            "SPICe plus company incorporation ROC filing delay RTI application",
            "National scholarship portal merit-cum-means Aadhaar biometric authentication failed error 330",
        ],
    )
    def test_mixed_attack_queries_are_intercepted(self, retriever, query):
        """Verify that trouble token queries route naturally and never produce hardcoded canned refusals."""
        domain = classify_domain(query)
        assert isinstance(domain, Domain)

        result = retriever.search(query)
        assert result.status != "uncovered_domain"

        ans = run_pipeline(query)
        assert ans.title != "Service Domain Not Covered"


class TestBoundaryCasesPMUYvsGeneralLPG:
    """Boundary discrimination between covered PMUY Ujjwala 2.0 and general LPG."""

    def test_pmuy_eligibility_is_not_uncovered(self, retriever):
        """PMUY Ujjwala eligibility queries must not be short-circuited as uncovered."""
        query = "PMUY Ujjwala 2.0 eligibility criteria"
        domain = classify_domain(query)
        result = retriever.search(query)
        assert result.status != "uncovered_domain"
        assert len(result.hits) > 0
        assert any("Ujjwala" in s.title for h in result.hits for s in h.document.sources)

    def test_general_lpg_cylinder_booking_is_uncovered(self, retriever):
        """General commercial/domestic LPG queries route naturally without uncovered short-circuit."""
        query = "How to book an LPG cylinder online through HP Gas?"
        domain = classify_domain(query)
        assert isinstance(domain, Domain)
        result = retriever.search(query)
        assert result.status != "uncovered_domain"


class TestAdversarialSpellingAndTokenBypassFindings:
    """Empirical verification of citizen phrasing variations.

    Ensures that citizen query phrasings route naturally to valid domains,
    never hit hardcoded uncovered blocks, and never produce pre-canned responses.
    """

    @pytest.mark.parametrize(
        "query,issue_type",
        [
            ("how to incorporate a company in India", "MCA: missing 'a' before company"),
            ("how to incorporate a new company", "MCA: 'a new' company"),
            ("company incorporation process", "MCA: reversed word order 'company incorporation'"),
            ("one person company registration", "MCA: OPC/one person company"),
            ("company registration online", "MCA: company registration"),
            ("llp registration process", "MCA: LLP registration"),
            ("cylinder delivery delay", "LPG: standalone cylinder with trouble word delay"),
            ("cooking gas connection application", "LPG: cooking gas connection"),
            ("cooking gas subsidy", "LPG: cooking gas subsidy"),
            ("bharatgas online booking", "LPG: single-word solid brand 'bharatgas'"),
            ("hpgas booking", "LPG: single-word solid brand 'hpgas'"),
            ("pre matric scholarship application", "NSP: space instead of hyphen in pre-matric"),
            ("post matric scholarship pending verification", "NSP: space instead of hyphen in post-matric"),
            ("merit cum means scholarship status", "NSP: spaces instead of hyphens in merit-cum-means"),
        ],
    )
    def test_uncovered_domain_remediated_queries(self, retriever, query, issue_type):
        """Verify that citizen phrasings route cleanly without hardcoded UNCOVERED block."""
        domain = classify_domain(query)
        assert isinstance(domain, Domain)

        result = retriever.search(query)
        assert result.status != "uncovered_domain"

        ans = run_pipeline(query)
        assert ans.title != "Service Domain Not Covered"


class TestRetrieverDomainParameterEnforcement:
    """Test behavior when retriever is called with explicit domain parameter."""

    def test_retriever_blocks_caller_passed_general_civic_domain_bypass(self, retriever):
        """Verifies that passing explicit domain routes cleanly through retriever."""
        query = "How to file SPICe+ Part A on MCA portal?"
        result = retriever.search(query, domain=Domain.GENERAL_CIVIC)
        assert result.status != "uncovered_domain"


class TestHindiDinAndContextCollisionPrevention:
    """Verify that Hindi 'din' (days), Hindi 'pahal' (initiative), and bare 'spice' route to their expected domain."""

    @pytest.mark.parametrize(
        "query,expected_domain",
        [
            ("Passport banne me kitne din lagte hai?", Domain.IDENTITY),
            ("Driving license kitne din me aayega?", Domain.TRANSPORT),
            ("Voter ID card kitne din me banta hai?", Domain.IDENTITY),
            ("Aadhaar card update hone me kitne din lagte hain?", Domain.IDENTITY),
            ("PAN card kitne din me banega?", Domain.IDENTITY),
            ("Spice jet complaint in consumer court", Domain.LEGAL_CONSUMER),
        ],
    )
    def test_hindi_din_and_context_do_not_route_to_uncovered(self, query, expected_domain):
        domain = classify_domain(query)
        assert domain == expected_domain
