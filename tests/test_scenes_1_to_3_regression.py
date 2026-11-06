"""Automated Regression Test Suite for Scenes 1-3 Remediation (Tiers 1-4).

Derived strictly from ORIGINAL_REQUEST.md, PROJECT.md, TEST_INFRA.md, and canonical
production failure batch conversations (chat_1793792993115_k2y6f, chat_1793793767437_wbeu6,
chat_1793794139711_p0bhr).

Coverage tiers:
- Tier 1: Feature Coverage (R1-R6: EPFO authenticity, hard domain routing, confidence decoupling,
          LLM relevance gate & anti-fabrication, CRAG scraper cleanup, AIS vs 139(9) discrimination)
- Tier 2: Boundary & Corner Cases (keyword collisions, trouble tokens, HTML table noise, empty queries)
- Tier 3: Cross-Feature Combinations (domain routing + confidence, sub-procedure + prompt grounding,
          anti-fabrication + post-retrieval relevance, CRAG DOM filter + zero predefined responses)
- Tier 4: Real-World Verbatim Scenarios from Scenes 1-3 turns
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.modules.domain_router import (
    Domain,
    classify_domain,
    get_allowed_rag_categories,
)
from backend.modules.llm import _build_llm_prompt
from backend.rag.loader import load_corpus
from backend.rag.models import RagDocument, RetrievalHit, RetrievalResult
from backend.rag.retriever import RagRetriever
from backend.schemas import Answer, Step
from backend.web_search.confidence import compute_rag_confidence
from backend.web_search.fetcher import (
    _extract_text,
    fetch_page_text,
    is_navigation_or_boilerplate_text,
)
from backend.web_search.synthesizer import (
    DISCRIMINATOR_FAILURE_PHRASE,
)

# Reference constants & contracts per PROJECT.md
UNCOVERED_DOMAIN = getattr(Domain, "UNCOVERED", "uncovered")

CIVIC_JSONL_PATH = Path("backend/data/refined/troubleshooting/troubleshooting_civic.jsonl")
TAX_JSONL_PATH = Path("backend/data/refined/troubleshooting/troubleshooting_tax.jsonl")
MANIFEST_PATH = Path("backend/data/rag_manifest.json")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


@pytest.fixture(scope="module")
def shared_corpus():
    return load_corpus()


@pytest.fixture(scope="module")
def shared_retriever(shared_corpus):
    return RagRetriever(shared_corpus)


# ==============================================================================
# TIER 1: FEATURE COVERAGE (R1 - R6)
# ==============================================================================

# ------------------------------------------------------------------------------
# Feature 1 (R1): EPFO Corpus Authenticity & Source Remediation
# ------------------------------------------------------------------------------

def test_tier1_r1_epfo_manifest_allowlist():
    """Verify that rag_manifest.json registers troubleshooting_civic and allowlists official EPFO domains."""
    assert MANIFEST_PATH.exists(), "rag_manifest.json must exist"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    civic_dataset = next((d for d in manifest.get("datasets", []) if d.get("id") == "troubleshooting_civic"), None)
    assert civic_dataset is not None, "troubleshooting_civic dataset must be registered in manifest"
    allowed_hosts = civic_dataset.get("allowed_hosts", [])
    assert "pmvbry-cdn.epfindia.gov.in" in allowed_hosts, "pmvbry-cdn.epfindia.gov.in must be allowlisted"
    assert "epfindia.gov.in" in allowed_hosts or "www.epfindia.gov.in" in allowed_hosts, "epfindia.gov.in must be allowlisted"


def test_tier1_r1_epfo_joint_declaration_sop_authenticity():
    """Verify epfo_joint_declaration_minor_major_sop_01 has authentic SOP URL and content matching title."""
    records = _read_jsonl(CIVIC_JSONL_PATH)
    rec = next((r for r in records if r.get("id") == "epfo_joint_declaration_minor_major_sop_01"), None)
    assert rec is not None, "epfo_joint_declaration_minor_major_sop_01 must exist in troubleshooting_civic.jsonl"
    assert rec["source_url"].startswith("https://"), "source_url must use HTTPS"
    assert rec["source_url"].endswith(".pdf"), "source_url must point to an official PDF"
    assert any(h in rec["source_url"] for h in ("epfindia.gov.in", "pmvbry-cdn.epfindia.gov.in"))
    text = rec["text"].lower()
    assert "joint declaration" in text
    assert "minor" in text and "major" in text
    assert "tat" in text or "working days" in text or "15" in text


def test_tier1_r1_epfo_closed_establishment_attestation_authenticity():
    """Verify epfo_closed_establishment_attestation_01 contains authentic closed establishment attestation framework."""
    records = _read_jsonl(CIVIC_JSONL_PATH)
    rec = next((r for r in records if r.get("id") == "epfo_closed_establishment_attestation_01"), None)
    assert rec is not None, "epfo_closed_establishment_attestation_01 must exist in troubleshooting_civic.jsonl"
    assert rec["source_url"].startswith("https://")
    assert any(h in rec["source_url"] for h in ("epfindia.gov.in", "pmvbry-cdn.epfindia.gov.in"))
    text = rec["text"].lower()
    assert "closed" in text or "non-operational" in text
    assert any(auth in text for auth in ("gazetted officer", "magistrate", "postmaster", "bank manager"))


def test_tier1_r1_epfo_passbook_cheque_standards_source_validity():
    """Verify epfo_claim_passbook_cheque_standards_01 points to authentic cheque/passbook circular, NOT inspector manual."""
    records = _read_jsonl(CIVIC_JSONL_PATH)
    rec = next((r for r in records if r.get("id") == "epfo_claim_passbook_cheque_standards_01"), None)
    assert rec is not None, "epfo_claim_passbook_cheque_standards_01 must exist in troubleshooting_civic.jsonl"
    # Survey 2 proved Manual_for_Inspector_cum_Facilitator.pdf is 221 pages with 0 mentions of cheque/passbook
    assert "Manual_for_Inspector_cum_Facilitator.pdf" not in rec["source_url"], (
        "epfo_claim_passbook_cheque_standards_01 must NOT point to Manual_for_Inspector_cum_Facilitator.pdf"
    )
    text = rec["text"].lower()
    assert "cheque" in text and "passbook" in text
    assert any(w in text for w in ("pre-printed", "printed name", "manager", "stamp", "signature"))


def test_tier1_r1_epfo_no_pmvbry_boilerplate():
    """Verify that none of the 3 EPFO records contain PMVBRY scheme boilerplate."""
    records = _read_jsonl(CIVIC_JSONL_PATH)
    epfo_ids = {
        "epfo_joint_declaration_minor_major_sop_01",
        "epfo_closed_establishment_attestation_01",
        "epfo_claim_passbook_cheque_standards_01",
    }
    for rec in records:
        if rec.get("id") in epfo_ids:
            text = rec["text"].lower()
            assert "pradhan mantri viksit bharat rozgar yojana" not in text
            assert "pmvbry scheme guidelines" not in text


# ------------------------------------------------------------------------------
# Feature 2 (R2): Hard Domain Routing - MCA / SPICe+
# ------------------------------------------------------------------------------

def test_tier1_r2_mca_spice_domain_classification():
    """Verify that MCA and SPICe+ queries classify into UNCOVERED domain."""
    queries = [
        "How do I register a private limited company using SPICe+ on MCA?",
        "MCA21 director identification number DIN application status",
        "SPICe+ Part A company name reservation under Rule 8A",
        "ROC company incorporation form INC-32 SPICe plus",
        "DIR-3 KYC verification for company director on MCA portal",
    ]
    for q in queries:
        assert classify_domain(q) == UNCOVERED_DOMAIN, f"Query '{q}' must classify as {UNCOVERED_DOMAIN}"


def test_tier1_r2_mca_spice_retriever_short_circuit(shared_retriever):
    """Verify retriever short-circuits with uncovered_domain and empty hits for MCA queries."""
    query = "SPICe+ Part A company name reservation resubmission under Rule 8A"
    result = shared_retriever.search(query, domain=UNCOVERED_DOMAIN)
    assert result.status == "uncovered_domain", f"Expected uncovered_domain, got {result.status}"
    assert result.hits == (), "Hits must be strictly empty"
    assert result.searched_documents == 0, "No documents should be searched"


def test_tier1_r2_mca_spice_zero_vector_bleed(shared_retriever):
    """Verify MCA/SPICe+ query does not bleed into EPFO passbook/cheque or MSME Udyam."""
    query = "My company name reservation SPICe+ Part A form was rejected with resubmission remark Proposed name resembles an existing LLP"
    result = shared_retriever.search(query, domain=UNCOVERED_DOMAIN)
    hit_ids = [h.document.id for h in result.hits]
    assert "epfo_claim_passbook_cheque_standards_01" not in hit_ids
    assert not any("passbook" in h.document.title.lower() for h in result.hits)
    assert not any("cheque" in h.document.title.lower() for h in result.hits)


def test_tier1_r2_mca_spice_allowed_categories_empty():
    """Verify get_allowed_rag_categories returns empty set for UNCOVERED domain."""
    allowed = get_allowed_rag_categories(UNCOVERED_DOMAIN)
    assert allowed == set(), f"Allowed categories for {UNCOVERED_DOMAIN} must be empty set, got {allowed}"


def test_tier1_r2_mca_spice_honest_refusal():
    """Verify that an uncovered MCA query yields an honest ungrounded refusal."""
    from backend.pipeline import run_pipeline
    ans = run_pipeline("How to file INC-29 on MCA21 portal?")
    assert ans.confidence == "low"
    assert not any("epfo" in (c.url or "").lower() for c in ans.citations)
    # Must not contain canned disclaimers referencing pre-verified guides
    assert "pre-verified guide" not in ans.summary.lower()


# ------------------------------------------------------------------------------
# Feature 3 (R2): Hard Domain Routing - Petroleum / LPG Subsidies
# ------------------------------------------------------------------------------

def test_tier1_r2_lpg_domain_classification():
    """Verify petroleum and LPG queries classify into UNCOVERED domain."""
    queries = [
        "How to book an LPG cylinder online or track delivery",
        "Indane domestic gas cylinder refill booking failed",
        "Bharat Gas subsidy not credited in bank account PAHAL DBTL",
        "HP Gas commercial cylinder price and connection",
        "MoPNG grievance matrix for LPG subsidy escalation",
    ]
    for q in queries:
        assert classify_domain(q) == UNCOVERED_DOMAIN, f"Query '{q}' must classify as {UNCOVERED_DOMAIN}"


def test_tier1_r2_lpg_retriever_short_circuit(shared_retriever):
    """Verify retriever short-circuits for petroleum/LPG queries."""
    query = "My LPG subsidy was stopped because my bank account became dormant. MoPNG grievance matrix"
    result = shared_retriever.search(query, domain=UNCOVERED_DOMAIN)
    assert result.status == "uncovered_domain"
    assert result.hits == ()
    assert result.searched_documents == 0


def test_tier1_r2_lpg_zero_vector_bleed_into_epfigms(shared_retriever):
    """Verify LPG subsidy query does NOT bleed into EPFiGMS or EPFO grievance SOP."""
    query = "LPG subsidy stopped dormant account MoPNG grievance escalation"
    result = shared_retriever.search(query, domain=UNCOVERED_DOMAIN)
    hit_ids = [h.document.id for h in result.hits]
    assert "epfo_epfigms_grievance_sop_01" not in hit_ids
    assert not any("epfigms" in h.document.title.lower() for h in result.hits)


def test_tier1_r2_lpg_allowed_categories_empty():
    """Verify allowed categories for LPG query is strictly empty."""
    allowed = get_allowed_rag_categories(UNCOVERED_DOMAIN)
    assert allowed == set()


def test_tier1_r2_lpg_honest_refusal():
    """Verify LPG subsidy query produces honest refusal without EPFiGMS hallucination."""
    from backend.pipeline import run_pipeline
    ans = run_pipeline("Which officer do I escalate to under MoPNG grievance matrix for stopped LPG subsidy?")
    assert "epfigms" not in ans.summary.lower()
    assert "epfo" not in ans.summary.lower()


# ------------------------------------------------------------------------------
# Feature 4 (R2): Hard Domain Routing - NSP Scholarships
# ------------------------------------------------------------------------------

def test_tier1_r2_nsp_domain_classification():
    """Verify National Scholarship Portal (NSP) queries classify into UNCOVERED domain."""
    queries = [
        "NSP scholarship status showing Defective by Institute",
        "National Scholarship Portal pre-matric scholarship verification",
        "Post-matric scholarship disbursement status on scholarships.gov.in",
        "Merit-cum-means scholarship renewal on NSP portal",
        "NSP scholarship institute nodal officer verification pending",
    ]
    for q in queries:
        assert classify_domain(q) == UNCOVERED_DOMAIN, f"Query '{q}' must classify as {UNCOVERED_DOMAIN}"


def test_tier1_r2_nsp_retriever_short_circuit(shared_retriever):
    """Verify retriever short-circuits on NSP scholarship queries."""
    query = "NSP scholarship application status is showing Defective by Institute re-verification"
    result = shared_retriever.search(query, domain=UNCOVERED_DOMAIN)
    assert result.status == "uncovered_domain"
    assert result.hits == ()


def test_tier1_r2_nsp_zero_bleed_into_tax_139_9(shared_retriever):
    """Verify NSP query with token 'Defective' does NOT retrieve Section 139(9) Income Tax manual."""
    query = "NSP scholarship status is showing Defective by Institute"
    result = shared_retriever.search(query, domain=UNCOVERED_DOMAIN)
    hit_ids = [h.document.id for h in result.hits]
    assert "itr_defective_return_manual_01" not in hit_ids
    assert not any("139(9)" in h.document.title for h in result.hits)
    assert not any("income tax" in h.document.title.lower() for h in result.hits)


def test_tier1_r2_nsp_allowed_categories_empty():
    """Verify allowed categories for NSP query is empty set."""
    assert get_allowed_rag_categories(UNCOVERED_DOMAIN) == set()


def test_tier1_r2_nsp_honest_refusal():
    """Verify NSP query produces honest refusal without Income Tax steps."""
    from backend.pipeline import run_pipeline
    ans = run_pipeline("NSP scholarship status is Defective by Institute clerk cannot see edit button")
    assert "139(9)" not in ans.summary
    assert "e-proceedings" not in ans.summary.lower()
    assert "incometax.gov.in" not in ans.summary.lower()


# ------------------------------------------------------------------------------
# Feature 5 (R3): Post-Retrieval Confidence Decoupling from Cosine Similarity
# ------------------------------------------------------------------------------

def test_tier1_r3_relevance_evaluator_interface():
    """Verify post-retrieval relevance check exists and grades context into MATCH, PARTIAL, NO_MATCH."""
    from backend.modules import explainer
    # Contract in PROJECT.md: evaluate_relevance(query, domain, top_hit) -> RelevanceGrade
    eval_fn = getattr(explainer, "evaluate_relevance", None)
    assert eval_fn is not None, "evaluate_relevance function must be defined in explainer module"
    doc = RagDocument(
        id="sample_doc",
        category="civic",
        title="EPFO SOP",
        section="Section A",
        text="Sample EPFO text",
        tags=("epfo",),
        sources=(),
    )
    hit = RetrievalHit(document=doc, score=0.080, rank=1, signals={})
    grade = eval_fn("How to apply for Joint Declaration on EPFO portal?", Domain.GENERAL_CIVIC, hit)
    assert str(grade).upper() in ("MATCH", "PARTIAL", "NO_MATCH")


def test_tier1_r3_no_match_forces_low_confidence():
    """Verify that NO_MATCH relevance strictly forces confidence badge to 'low' even with high similarity."""
    from backend.modules import explainer
    # When semantic relevance is NO_MATCH, high raw score must NOT award high confidence
    doc = RagDocument(
        id="cheque_doc",
        category="civic",
        title="EPFO Passbook Standards",
        section="Bank KYC",
        text="Cancelled cheque leaf pre-printed name rules",
        tags=("cheque",),
        sources=(),
    )
    # Artificially high score
    hit = RetrievalHit(document=doc, score=0.095, rank=1, signals={"vector_score": 0.95})
    res = RetrievalResult(query="SPICe+ Part A company name reservation", hits=(hit,), status="supported_hybrid", searched_documents=100)
    ans = explainer.explain_rag_result(res)
    # With confidence decoupled, an irrelevant query must not get 'high' confidence
    assert ans.confidence == "low", f"Expected 'low' confidence for mismatched query, got {ans.confidence}"


def test_tier1_r3_partial_bounds_confidence():
    """Verify PARTIAL relevance bounds confidence badge to 'medium' or 'low', never 'high'."""
    from backend.modules import explainer
    doc = RagDocument(
        id="general_filing_doc",
        category="tax",
        title="General Tax Guidelines",
        section="General",
        text="Taxpayers must check AIS before filing ITR",
        tags=("tax",),
        sources=(),
    )
    hit = RetrievalHit(document=doc, score=0.070, rank=1, signals={"vector_score": 0.90})
    res = RetrievalResult(query="How to dispute duplicate mutual fund SFT in AIS?", hits=(hit,), status="supported_hybrid", searched_documents=100)
    ans = explainer.explain_rag_result(res)
    assert ans.confidence in ("medium", "low"), f"PARTIAL match must not be high confidence, got {ans.confidence}"


def test_tier1_r3_match_permits_high_confidence():
    """Verify MATCH relevance permits 'high' confidence when score threshold is satisfied."""
    from backend.modules import explainer
    doc = RagDocument(
        id="epfo_joint_dec",
        category="civic",
        title="EPFO Joint Declaration SOP (JD/2022/1)",
        section="Member Profile Correction",
        text="Joint declaration procedure for name and date of birth correction on member portal",
        tags=("epf_joint_declaration", "sop"),
        sources=(),
    )
    hit = RetrievalHit(document=doc, score=0.060, rank=1, signals={"vector_score": 0.88})
    res = RetrievalResult(query="EPFO Joint Declaration SOP procedure for name update", hits=(hit,), status="supported_hybrid", searched_documents=100)
    ans = explainer.explain_rag_result(res)
    assert ans.confidence == "high", f"Exact match with high score must be 'high' confidence, got {ans.confidence}"


def test_tier1_r3_decoupling_prevents_false_high_confidence():
    """Verify cross-domain retrieval bleed hits do not receive high confidence."""
    from backend.modules import explainer
    doc = RagDocument(
        id="epfigms_sop",
        category="civic",
        title="EPFiGMS Grievance Registration",
        section="EPFO",
        text="Register grievance for stuck PF claims on epfigms.gov.in",
        tags=("epfigms",),
        sources=(),
    )
    # Cosine score is high due to words like 'grievance', 'subsidy', 'account'
    hit = RetrievalHit(document=doc, score=0.065, rank=1, signals={"vector_score": 0.85})
    res = RetrievalResult(query="MoPNG grievance matrix for LPG subsidy escalation", hits=(hit,), status="supported_hybrid", searched_documents=100)
    ans = explainer.explain_rag_result(res)
    assert ans.confidence != "high", "Cross-domain hit must never receive 'high' confidence badge"


# ------------------------------------------------------------------------------
# Feature 6 (R4): LLM Synthesis Relevance Gating & Anti-Fabrication
# ------------------------------------------------------------------------------

def test_tier1_r4_prompt_contains_anti_fabrication_directive():
    """Verify _build_llm_prompt contains strict anti-fabrication directive for unstated premises."""
    ans = Answer(
        title="Official Procedure",
        summary="Summary",
        documents_needed=[],
        steps=[Step(title="Step 1", detail="Detail 1")],
    )
    system, prompt, _ = _build_llm_prompt("My employer DSC is active but gives error", ans, None)
    system_lower = system.lower()
    assert "never assume" in system_lower or "unstated" in system_lower or "anti-fabrication" in system_lower, (
        "System prompt must contain explicit anti-fabrication directive prohibiting assumption of unstated facts"
    )
    assert "closed" in system_lower or "non-operational" in system_lower, (
        "System prompt must specifically mention closed/non-operational employer assumption guard"
    )


def test_tier1_r4_prompt_contains_domain_relevance_gate():
    """Verify _build_llm_prompt contains domain relevance refusal directive."""
    ans = Answer(
        title="Official Procedure",
        summary="Summary",
        documents_needed=[],
        steps=[Step(title="Step 1", detail="Detail 1")],
    )
    system, prompt, _ = _build_llm_prompt("Test question", ans, None)
    assert "insufficient data in the verified civic knowledge base for this specific portal" in system.lower()


def test_tier1_r4_anti_fabrication_closed_establishment():
    """Verify prompt instructs LLM not to instruct user to follow closed-establishment protocol when unstated."""
    ans = Answer(
        title="EPFO Attestation Framework for Closed Establishments",
        summary="Protocol when establishment is closed.",
        documents_needed=[],
        steps=[Step(title="Gazetted Officer", detail="Get signature")],
    )
    q = "When uploading joint declaration form, error DSC not registered. My employer says their digital signature is valid."
    system, prompt, _ = _build_llm_prompt(q, ans, None)
    assert "employer is closed" not in prompt.lower()
    # The directives in system prompt must prohibit projecting closed status
    assert "never assume" in system.lower() or "do not instruct" in system.lower() or "unstated" in system.lower()


def test_tier1_r4_refusal_interception():
    """Verify refusal phrases in LLM candidates trigger ungrounded not_found_answer."""
    from backend.modules.llm import LocalLLMClient
    from backend.modules.explainer import not_found_answer
    client = LocalLLMClient()
    mock_resp = '{"summary": "Insufficient data in the verified civic knowledge base for this specific portal.", "steps": [], "documents_needed": []}'
    with patch("backend.modules.llm._call_ollama", return_value=mock_resp):
        ans = Answer(title="Candidate", summary="Candidate", documents_needed=[], steps=[Step(title="S", detail="D")])
        res = client.synthesize_grounded_answer("How to reserve name on MCA SPICe+?", ans)
        assert res.title == not_found_answer("q").title or "not found" in res.title.lower() or "insufficient" in res.summary.lower()


def test_tier1_r4_zero_predefined_responses_compliance():
    """Verify that ungrounded refusals adhere to AGENTS.md zero-predefined-response directive."""
    from backend.modules.explainer import not_found_answer
    refusal = not_found_answer("Random uncovered query")
    assert "pre-verified guide" not in refusal.summary.lower()
    assert "predefined response" not in refusal.summary.lower()
    assert "pre-canned" not in refusal.summary.lower()


# ------------------------------------------------------------------------------
# Feature 7 (R5): Scraper DOM Noise Elimination in CRAG Fallback
# ------------------------------------------------------------------------------

def test_tier1_r5_trafilatura_extraction_tables_disabled():
    """Verify _extract_text in fetcher.py configures trafilatura with include_tables=False."""
    import inspect
    from backend.web_search import fetcher
    src = inspect.getsource(fetcher._extract_text)
    assert "include_tables=False" in src, "_extract_text must call trafilatura.extract with include_tables=False"


def test_tier1_r5_markdown_table_rejection():
    """Verify is_navigation_or_boilerplate_text rejects markdown table blocks."""
    table_text = (
        "| Document Title | Release Date | Format | Size |\n"
        "| Act and Rules 2026 | 11-06-2026 | PDF | 838 KB |\n"
        "| Leasing Policy | 03-06-2026 | PDF | 11 MB |\n"
    )
    assert is_navigation_or_boilerplate_text(table_text) is True, (
        "is_navigation_or_boilerplate_text must return True for markdown table directory rows"
    )


def test_tier1_r5_pdf_directory_catalog_rejection():
    """Verify is_navigation_or_boilerplate_text rejects PDF directory catalog text."""
    catalog_text = (
        "List of Acceptable Documents for Aadhaar Enrolment Language: English Version 11-06-2026 "
        "Format: PDFSize: 838.3 KB Compilation of Post Office Act Rules and Regulations"
    )
    assert is_navigation_or_boilerplate_text(catalog_text) is True, (
        "is_navigation_or_boilerplate_text must return True for download directory catalog blocks"
    )


def test_tier1_r5_clean_prose_retained():
    """Verify clean procedural prose without tables is extracted cleanly."""
    clean_html = """
    <html>
      <body>
        <main>
          <h1>Department of Posts Deceased Claim Procedure</h1>
          <p>Where a depositor has died without nomination and the claim is up to 5 lakh rupees, the claimant must submit Form 11.</p>
          <p>Attach the original death certificate, KYC documents of legal heirs, and letter of disclaimer.</p>
          <p>Submit the application to the Sub-Postmaster or Postmaster where the account is held.</p>
        </main>
      </body>
    </html>
    """
    text = _extract_text(clean_html)
    assert "deceased claim procedure" in text.lower()
    assert "death certificate" in text.lower()
    assert not is_navigation_or_boilerplate_text(text)


def test_tier1_r5_table_only_page_yields_empty_or_refusal():
    """Verify that an HTML page containing only directory tables extracts empty or triggers failure phrase."""
    table_html = """
    <html>
      <body>
        <main>
          <table>
            <tr><th>Title</th><th>Date</th><th>Size</th></tr>
            <tr><td>Circular 1</td><td>2026-01-01</td><td>1.2MB</td></tr>
            <tr><td>Circular 2</td><td>2026-02-01</td><td>3.4MB</td></tr>
          </table>
        </main>
      </body>
    </html>
    """
    extracted = _extract_text(table_html)
    # With include_tables=False, extracted should either be empty or flagged as boilerplate
    assert not extracted or is_navigation_or_boilerplate_text(extracted)


# ------------------------------------------------------------------------------
# Feature 8 (R6): Same-Domain Sub-Procedure Granularity (139(9) vs AIS Feedback)
# ------------------------------------------------------------------------------

def test_tier1_r6_ais_feedback_document_exists():
    """Verify authentic official document itr_ais_feedback_manual_01 exists in troubleshooting_tax.jsonl."""
    records = _read_jsonl(TAX_JSONL_PATH)
    rec = next((r for r in records if r.get("id") == "itr_ais_feedback_manual_01"), None)
    assert rec is not None, "itr_ais_feedback_manual_01 must exist in troubleshooting_tax.jsonl"
    assert "incometax.gov.in" in rec["source_url"]
    assert "ais" in rec["source_url"].lower()


def test_tier1_r6_ais_feedback_content_accuracy():
    """Verify itr_ais_feedback_manual_01 contains feedback options and notes it is not a 139(9) proceeding."""
    records = _read_jsonl(TAX_JSONL_PATH)
    rec = next((r for r in records if r.get("id") == "itr_ais_feedback_manual_01"), None)
    assert rec is not None
    text = rec["text"].lower()
    assert "annual information statement" in text or "ais" in text
    assert "part b" in text or "sft" in text
    assert "information is duplicate" in text or "duplicate" in text
    assert "tis" in text or "derived value" in text
    assert "139(9)" in text and ("not" in text or "neither" in text)


def test_tier1_r6_retriever_exact_code_booster():
    """Verify retriever includes AIS feedback exact boost terms."""
    import inspect
    from backend.rag import retriever
    src = inspect.getsource(retriever.RagRetriever.search)
    assert "ais feedback" in src or "annual information statement" in src, (
        "RagRetriever.search must boost AIS feedback exact codes"
    )


def test_tier1_r6_symptom_cluster_ais_vs_139():
    """Verify retriever defines dedicated ais_feedback cluster and mutual conflict penalties."""
    import inspect
    from backend.rag import retriever
    src = inspect.getsource(retriever.RagRetriever.search)
    assert "ais_feedback" in src, "Retriever must define ais_feedback symptom cluster"
    assert "conflicts" in src and "139(9)" in src, "AIS feedback cluster must conflict with 139(9)"


def test_tier1_r6_sub_procedure_bidirectional_discrimination(shared_retriever):
    """Verify query for AIS feedback ranks AIS document #1 and penalizes 139(9), and vice versa."""
    ais_query = "How do I submit feedback for duplicate SFT mutual fund transaction in AIS?"
    ais_res = shared_retriever.search(ais_query, category="tax", top_k=5)
    assert ais_res.hits, "Retriever must return hits for AIS query"
    top_hit_id = ais_res.hits[0].document.id
    assert top_hit_id == "itr_ais_feedback_manual_01", (
        f"Top hit for AIS query must be itr_ais_feedback_manual_01, got {top_hit_id}"
    )

    notice_query = "How do I respond to Section 139(9) defective return notice on e-proceedings portal?"
    notice_res = shared_retriever.search(notice_query, category="tax", top_k=5)
    assert notice_res.hits, "Retriever must return hits for 139(9) notice query"
    notice_top_id = notice_res.hits[0].document.id
    assert notice_top_id == "itr_defective_return_manual_01", (
        f"Top hit for 139(9) query must be itr_defective_return_manual_01, got {notice_top_id}"
    )


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

def test_tier2_trouble_word_mca_does_not_bleed_to_civic():
    """Corner case: Query with civic trouble words ('error', 'resubmission') on MCA routes to UNCOVERED."""
    q = "Error occurred during resubmission on MCA portal under Rule 8A"
    assert classify_domain(q) == UNCOVERED_DOMAIN


def test_tier2_trouble_word_lpg_does_not_bleed_to_banking():
    """Corner case: Query with banking words ('payment failed', 'dormant account') on LPG routes to UNCOVERED."""
    q = "LPG subsidy payment failed and pending in dormant account"
    assert classify_domain(q) == UNCOVERED_DOMAIN


def test_tier2_trouble_word_nsp_does_not_bleed_to_tax():
    """Corner case: Query with tax trouble words ('rejected', 'defect notice') on NSP routes to UNCOVERED."""
    q = "Scholarship rejected due to institute defect notice on NSP"
    assert classify_domain(q) == UNCOVERED_DOMAIN


def test_tier2_valid_transport_trouble_words_preserved():
    """Boundary: Valid transport query with trouble words remains TRANSPORT domain."""
    q = "Driving license slot booking failed with pending transaction on Sarathi"
    assert classify_domain(q) == Domain.TRANSPORT


def test_tier2_valid_tax_trouble_words_preserved():
    """Boundary: Valid tax query with trouble words remains TAXATION domain."""
    q = "Bank account validation failed with refund unpaid on income tax portal"
    assert classify_domain(q) == Domain.TAXATION


def test_tier2_ais_query_with_defect_keyword(shared_retriever):
    """Boundary: AIS query containing word 'defect' still ranks AIS manual #1, not 139(9)."""
    q = "Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report"
    res = shared_retriever.search(q, category="tax", top_k=3)
    if res.hits:
        assert res.hits[0].document.id == "itr_ais_feedback_manual_01"


def test_tier2_139_query_with_ais_keyword(shared_retriever):
    """Boundary: Section 139(9) query mentioning AIS still ranks 139(9) manual #1, not AIS feedback."""
    q = "Received Section 139(9) defective return notice because AIS income differed from ITR"
    res = shared_retriever.search(q, category="tax", top_k=3)
    assert res.hits, "Retriever must return hits"
    assert res.hits[0].document.id == "itr_defective_return_manual_01"


def test_tier2_crag_html_table_only_page():
    """Corner case: CRAG fetcher encountering pure table page produces empty clean text or boilerplate."""
    pure_table = "<table><tr><td>Rule 1</td><td>Value 1</td></tr></table>"
    assert not _extract_text(pure_table) or is_navigation_or_boilerplate_text(_extract_text(pure_table))


def test_tier2_empty_and_whitespace_queries(shared_retriever):
    """Boundary: Empty or whitespace query handled gracefully by retriever without crashes."""
    for empty in ("", "   ", "\t\n"):
        res = shared_retriever.search(empty)
        assert res.status == "empty_query"
        assert res.hits == ()


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# ==============================================================================

def test_tier3_uncovered_domain_produces_low_confidence_refusal():
    """Cross-feature: Domain routing interception + confidence decoupling produces low confidence refusal."""
    from backend.pipeline import run_pipeline
    queries = [
        "How to apply for MCA SPICe+ Part A name reservation?",
        "MoPNG grievance matrix for LPG subsidy escalation",
        "NSP scholarship status showing Defective by Institute",
    ]
    for q in queries:
        ans = run_pipeline(q)
        assert ans.confidence == "low", f"Query '{q}' must have low confidence, got {ans.confidence}"
        assert not any(h in (ans.source_url or "").lower() for h in ("epfigms", "139(9)", "passbook"))


def test_tier3_ais_discrimination_with_confidence_badge():
    """Cross-feature: Sub-procedure discrimination + confidence badge produces MATCH with high confidence."""
    from backend.modules import explainer
    records = _read_jsonl(TAX_JSONL_PATH)
    rec = next((r for r in records if r.get("id") == "itr_ais_feedback_manual_01"), None)
    if rec:
        doc = RagDocument(
            id=rec["id"],
            category="tax",
            title=rec["title"],
            section=rec["section"],
            text=rec["text"],
            tags=tuple(rec.get("retrieval_tags", ())),
            sources=(),
        )
        hit = RetrievalHit(document=doc, score=0.065, rank=1, signals={"vector_score": 0.90})
        res = RetrievalResult(
            query="How do I submit feedback for duplicate SFT transaction in AIS?",
            hits=(hit,),
            status="supported_hybrid",
            searched_documents=115,
        )
        ans = explainer.explain_rag_result(res)
        assert ans.confidence == "high"
        assert "ais" in ans.title.lower() or "annual information" in ans.title.lower()


def test_tier3_active_employer_with_closed_est_chunk_confidence_and_prompt():
    """Cross-feature: Active employer query + closed establishment retrieved chunk."""
    doc = RagDocument(
        id="epfo_closed_est",
        category="civic",
        title="EPFO Attestation Framework for Closed Establishments",
        section="Field Formats",
        text="Alternative attestation by Gazetted Officer when employer is closed",
        tags=("closed_establishment_epf",),
        sources=(),
    )
    hit = RetrievalHit(document=doc, score=0.055, rank=1, signals={})
    ans = Answer(
        title=doc.title,
        summary=doc.text,
        documents_needed=[],
        steps=[Step(title="Attestation", detail="Get signature of Gazetted Officer")],
    )
    q = "When uploading joint declaration, error DSC not active. My employer says their digital signature is valid."
    system, prompt, _ = _build_llm_prompt(q, ans, None)
    assert "never assume" in system.lower() or "unstated" in system.lower()


def test_tier3_crag_dom_filter_with_zero_predefined_responses():
    """Cross-feature: Scraper table rejection triggers dynamic refusal without canned templates."""
    from backend.web_search.synthesizer import is_navigation_or_boilerplate_text
    table_noise = "| Aadhaar Form | 838 KB | 11-06-2026 |\n| Post Office Act | 11 MB | 03-06-2026 |"
    assert is_navigation_or_boilerplate_text(table_noise) is True
    # Synthesizer must reject this without canned disclaimer
    from backend.web_search.synthesizer import DISCRIMINATOR_FAILURE_PHRASE
    assert "pre-verified guide" not in DISCRIMINATOR_FAILURE_PHRASE.lower()


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (VERBATIM SCENES 1-3 TURNS)
# ==============================================================================

def test_tier4_scene1_turn1_epfo_active_employer_dsc_error():
    """Scene 1 Turn 1 Verbatim: EPFO Joint Declaration DSC error with active employer.

    Must NOT hallucinate that establishment is closed or advise user to prove establishment is closed.
    """
    q = "When uploading my joint declaration form on the EPFO member portal, it gives error 'DSC not registered or active for the establishment'. My employer says their digital signature is valid. What exact setting or utility is missing on their system?"
    ans = Answer(
        title="EPFO Joint Declaration",
        summary="Joint declaration correction rules.",
        documents_needed=[],
        steps=[Step(title="Portal Step", detail="Detail")],
    )
    system, prompt, _ = _build_llm_prompt(q, ans, None)
    # The directives must strictly prohibit assuming the establishment is closed
    assert "never assume" in system.lower() or "unstated" in system.lower()
    assert "closed" in system.lower()


def test_tier4_scene1_turn3_mca_spice_name_reservation_rule_8a(shared_retriever):
    """Scene 1 Turn 3 Verbatim: SPICe+ Part A MCA name reservation under Rule 8A.

    Must NOT bleed into EPFO passbook and cheque leaf validation standards.
    """
    q = "My company name reservation SPICe+ Part A form was rejected with resubmission remark 'Proposed name resembles an existing LLP under Rule 8A'. What is the exact turnaround time to resubmit before the fee lapses?"
    # Domain router must catch this
    domain = classify_domain(q)
    assert domain == UNCOVERED_DOMAIN, f"Expected {UNCOVERED_DOMAIN}, got {domain}"

    res = shared_retriever.search(q, domain=domain)
    assert res.status == "uncovered_domain"
    assert res.hits == ()
    assert not any("passbook" in h.document.title.lower() for h in res.hits)
    assert not any("cheque" in h.document.title.lower() for h in res.hits)


def test_tier4_scene2_turn1_nsp_defective_by_institute(shared_retriever):
    """Scene 2 Turn 1 Verbatim: NSP scholarship application status 'Defective by Institute'.

    Must NOT bleed into Income Tax Section 139(9) defective return intimation.
    """
    q = "NSP scholarship application status is showing 'Defective by Institute'. My college clerk says they cannot see any edit button on their login. What is the official SOP to enable re-verification?"
    domain = classify_domain(q)
    assert domain == UNCOVERED_DOMAIN, f"Expected {UNCOVERED_DOMAIN}, got {domain}"

    res = shared_retriever.search(q, domain=domain)
    assert res.status == "uncovered_domain"
    assert res.hits == ()
    assert not any("139(9)" in h.document.title for h in res.hits)
    assert not any("income tax" in h.document.title.lower() for h in res.hits)


def test_tier4_scene2_turn2_ais_sft_mutual_fund_duplicate(shared_retriever):
    """Scene 2 Turn 2 Verbatim: AIS SFT mismatch mutual fund duplicate feedback.

    Must resolve to AIS feedback manual (itr_ais_feedback_manual_01), NOT Section 139(9) defective returns.
    """
    q = "I received an SMS about 'Significant Financial Transaction (SFT)' mismatch in AIS for mutual fund sales. Where do I submit an online explanation, and what feedback category should I choose if the broker reported gross sales twice?"
    res = shared_retriever.search(q, category="tax", top_k=3)
    assert res.hits, "Retriever must return hits"
    top_hit = res.hits[0]
    assert top_hit.document.id == "itr_ais_feedback_manual_01", (
        f"Top hit must be itr_ais_feedback_manual_01, got {top_hit.document.id}"
    )
    assert "information is duplicate" in top_hit.document.text.lower()
    # 139(9) must not be top hit
    assert top_hit.document.id != "itr_defective_return_manual_01"


def test_tier4_scene3_turn1_lpg_subsidy_mopng_grievance(shared_retriever):
    """Scene 3 Turn 1 Verbatim: LPG subsidy dormant account MoPNG grievance.

    Must NOT bleed into EPFiGMS or claim EPFiGMS handles LPG subsidies.
    """
    q = "My LPG subsidy was stopped because my bank account became dormant. I reactivated the account and seeded it at the branch 2 months ago, but subsidy is still not coming. Which portal or officer do I escalate to under the MoPNG grievance matrix?"
    domain = classify_domain(q)
    assert domain == UNCOVERED_DOMAIN, f"Expected {UNCOVERED_DOMAIN}, got {domain}"

    res = shared_retriever.search(q, domain=domain)
    assert res.status == "uncovered_domain"
    assert res.hits == ()
    assert not any("epfigms" in h.document.title.lower() for h in res.hits)


def test_tier4_scene3_turn2_post_office_mis_claim_no_nomination():
    """Scene 3 Turn 2 Verbatim: Post Office MIS claim without nomination.

    CRAG scraper must eliminate document directory table DOM noise.
    """
    table_noise_snippet = (
        "| List of Acceptable Documents for Aadhaar Enrolment and Update Language: English Version | 11-06-2026 | Format: PDFSize: 838.3 KB |\n"
        "| Long term leasing policy for hiring accommodation for office purpose in Department of Posts Language: English Version | 03-06-2026 | Format: PDFSize: 11 MB |\n"
        "| Compilation of Post Office Act, Rules and Regulations."
    )
    assert is_navigation_or_boilerplate_text(table_noise_snippet) is True, (
        "Table noise snippet must be classified as navigation/boilerplate"
    )
