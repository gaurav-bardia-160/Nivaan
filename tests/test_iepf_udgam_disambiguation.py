import pytest
from backend.modules.domain_router import Domain, classify_domain, get_allowed_rag_categories
from backend.rag.bm25 import tokenize
from backend.pipeline import run_pipeline
from backend.schemas import AskRequest


def test_bm25_acronym_disambiguation():
    """Verify IEPF and EPF tokens are treated as distinct entities."""
    t_iepf = tokenize("450 Reliance shares in IEPF, folio number, unpaid dividends")
    t_epf = tokenize("EPF UAN activation and member passbook download")

    assert "iepf" in t_iepf
    assert "epf" not in t_iepf
    assert "epfo" not in t_iepf

    assert "epf" in t_epf
    assert "iepf" not in t_epf


def test_domain_routing_iepf_not_intercepted_by_mca_spice():
    """Verify IEPF queries on MCA portal are routed to BANKING and not blocked by mca_spice."""
    q1 = "450 Reliance shares in IEPF, folio number, unpaid dividends"
    q2 = "RTA Entitlement Letter for IEPF claim on MCA portal"
    q3 = "How to file Form IEPF-5 on MCA21 for unpaid dividend refund"

    for q in (q1, q2, q3):
        domain = classify_domain(q)
        assert domain != Domain.UNCOVERED, f"Query '{q}' was falsely classified as UNCOVERED"
        assert domain == Domain.BANKING, f"Query '{q}' expected BANKING, got {domain}"


def test_domain_routing_udgam_dea_fund():
    """Verify UDGAM and RBI DEA Fund queries are routed to BANKING."""
    q1 = "How is interest calculated on unclaimed bank deposits in RBI DEA Fund"
    q2 = "Search unclaimed savings account on UDGAM portal"

    for q in (q1, q2):
        domain = classify_domain(q)
        assert domain != Domain.UNCOVERED, f"Query '{q}' was falsely classified as UNCOVERED"
        assert domain == Domain.BANKING, f"Query '{q}' expected BANKING, got {domain}"


def test_scene1_q1_iepf_retrieval_no_epf_bleed():
    """Scene 1, Q1: 450 Reliance shares in IEPF -> Must retrieve IEPF, never EPF/e-SHRAM."""
    req = AskRequest(question="I have 450 Reliance shares in IEPF with folio number, how do I claim unpaid dividends?")
    ans = run_pipeline(req)

    # Must find authoritative guidance
    assert ans.confidence in ("high", "medium"), f"Expected high/medium confidence, got {ans.confidence}"

    # Must contain IEPF citations
    citation_urls = [str(c.url).lower() for c in ans.citations]
    citation_titles = [c.title.lower() for c in ans.citations]

    # Verify no EPF / e-SHRAM / UAN bleeding
    for url in citation_urls:
        assert "epfindia" not in url, f"EPFO bleed in IEPF citation URL: {url}"
        assert "eshram" not in url, f"e-SHRAM bleed in IEPF citation URL: {url}"

    import re
    for title in citation_titles:
        assert not re.search(r"\bepfo?\b", title), f"EPFO bleed in IEPF citation title: {title}"
        assert "e-shram" not in title, f"e-SHRAM bleed in IEPF citation title: {title}"

    # At least one citation must be official IEPF or MCA
    assert any("iepf.gov.in" in u or "mca.gov.in" in u for u in citation_urls), f"No IEPF/MCA citation found: {citation_urls}"


def test_scene1_q3_rta_entitlement_letter_no_pan_bleed():
    """Scene 1, Q3: RTA Entitlement Letter for IEPF -> Must retrieve IEPF, never UTIITSL PAN."""
    req = AskRequest(question="How do I get the RTA Entitlement Letter for my IEPF-5 claim?")
    ans = run_pipeline(req)

    assert ans.confidence in ("high", "medium")
    citation_urls = [str(c.url).lower() for c in ans.citations]
    citation_titles = [c.title.lower() for c in ans.citations]

    # Verify no UTIITSL PAN bleeding
    for url in citation_urls:
        assert "utiitsl" not in url, f"UTIITSL PAN bleed in citation URL: {url}"
    for title in citation_titles:
        assert "pan" not in title or "iepf" in title, f"UTIITSL PAN bleed in citation title: {title}"

    # Must be official IEPF or MCA
    assert any("iepf.gov.in" in u or "mca.gov.in" in u for u in citation_urls)


def test_scene2_q3_rbi_dea_fund_interest_no_iepf_confusion():
    """Scene 2, Q3: Interest on RBI DEA Fund deposits -> RBI DEA Fund / UDGAM, not IEPF/EPFO."""
    req = AskRequest(question="How is interest calculated on unclaimed deposits transferred to the RBI DEA Fund?")
    ans = run_pipeline(req)

    assert ans.confidence in ("high", "medium")
    citation_urls = [str(c.url).lower() for c in ans.citations]

    # Must be RBI official guidance
    assert any("rbi.org.in" in u for u in citation_urls), f"Expected RBI citation, got {citation_urls}"

    # Summary must NOT hallucinate 'Income Escrow and Payment Fund'
    summary_lower = ans.summary.lower()
    assert "income escrow" not in summary_lower, "Hallucinated 'Income Escrow and Payment Fund' in summary"
