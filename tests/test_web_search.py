"""Tests for the web search fallback pipeline (Phase 1).

Tests are designed to run without network access — all external calls are mocked.
"""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── allowlist tests ───────────────────────────────────────────────────────────

class TestIsAllowlistedUrl:
    def test_gov_in_domains_allowed(self):
        from backend.web_search.allowlist import is_allowlisted_url
        assert is_allowlisted_url("https://incometax.gov.in/iec/foportal/")
        assert is_allowlisted_url("https://parivahan.gov.in/parivahan/")
        assert is_allowlisted_url("https://uidai.gov.in/en/")
        assert is_allowlisted_url("https://epfindia.gov.in/site_en/")
        assert is_allowlisted_url("https://passport.gov.in/")
        assert is_allowlisted_url("https://cbse.gov.in/")
        assert is_allowlisted_url("https://rbi.org.in/Scripts/FAQView.aspx")
        assert is_allowlisted_url("https://npci.org.in/what-we-do/upi/circular")
        assert is_allowlisted_url("https://vahan.nic.in/nrservices/")
        assert is_allowlisted_url("https://voters.eci.gov.in/")

    def test_non_gov_domains_blocked(self):
        from backend.web_search.allowlist import is_allowlisted_url
        assert not is_allowlisted_url("https://example.com/tax-refund")
        assert not is_allowlisted_url("https://legaltax.in/itr-filing")
        assert not is_allowlisted_url("https://taxmanager.co.in/")
        assert not is_allowlisted_url("https://google.com/search?q=fastag")
        assert not is_allowlisted_url("http://parivahan.in/")  # .in not in allowlist
        assert not is_allowlisted_url("")
        assert not is_allowlisted_url("not_a_url")

    def test_subdomain_of_allowlisted_domain_allowed(self):
        from backend.web_search.allowlist import is_allowlisted_url
        assert is_allowlisted_url("https://onlineservices.uidai.gov.in/")
        assert is_allowlisted_url("https://unifiedportal-mem.epfindia.gov.in/")
        assert is_allowlisted_url("https://echallan.parivahan.gov.in/")

    def test_gov_in_subdomain_not_in_explicit_list_still_allowed(self):
        from backend.web_search.allowlist import is_allowlisted_url
        # Any *.gov.in should be allowed since "gov.in" is in the allowlist
        assert is_allowlisted_url("https://someportal.gov.in/path/")
        assert is_allowlisted_url("https://digilocker.gov.in/")


# ─── confidence scoring tests ──────────────────────────────────────────────────

class TestComputeRagConfidence:
    def test_none_returns_zero(self):
        from backend.web_search.confidence import compute_rag_confidence
        assert compute_rag_confidence(None) == 0.0

    def test_empty_hits_returns_zero(self):
        from backend.web_search.confidence import compute_rag_confidence
        mock_result = MagicMock()
        mock_result.hits = []
        assert compute_rag_confidence(mock_result) == 0.0

    def test_high_score_returns_near_one(self):
        from backend.web_search.confidence import compute_rag_confidence
        mock_result = MagicMock()
        mock_hit = MagicMock()
        mock_hit.score = 0.045  # well above 0.040 threshold
        mock_result.hits = [mock_hit]
        confidence = compute_rag_confidence(mock_result)
        assert confidence == 1.0

    def test_mid_score_returns_partial(self):
        from backend.web_search.confidence import compute_rag_confidence
        mock_result = MagicMock()
        mock_hit = MagicMock()
        mock_hit.score = 0.020  # = 0.020/0.040 = 0.5
        mock_result.hits = [mock_hit]
        confidence = compute_rag_confidence(mock_result)
        assert abs(confidence - 0.5) < 0.01

    def test_very_low_score_returns_near_zero(self):
        from backend.web_search.confidence import compute_rag_confidence
        mock_result = MagicMock()
        mock_hit = MagicMock()
        mock_hit.score = 0.005
        mock_result.hits = [mock_hit]
        confidence = compute_rag_confidence(mock_result)
        assert confidence < 0.15

    def test_zero_score_returns_zero(self):
        from backend.web_search.confidence import compute_rag_confidence
        mock_result = MagicMock()
        mock_hit = MagicMock()
        mock_hit.score = 0.0
        mock_result.hits = [mock_hit]
        assert compute_rag_confidence(mock_result) == 0.0


# ─── audit log tests ───────────────────────────────────────────────────────────

class TestLogPendingIngestion:
    def test_writes_valid_jsonl(self, tmp_path, monkeypatch):
        from backend.web_search import audit_log
        test_path = tmp_path / "pending_ingestion.jsonl"
        monkeypatch.setattr(audit_log, "PENDING_INGESTION_PATH", test_path)
        monkeypatch.setattr(audit_log, "ETL_DIR", tmp_path)

        from backend.web_search.audit_log import log_pending_ingestion
        log_pending_ingestion({
            "query": "How to get FASTag refund?",
            "url": "https://parivahan.gov.in/fastag/",
            "domain": "transport",
            "timestamp": "2026-11-02T17:00:00Z",
            "snippet": "FASTag dispute resolution via IHMCL",
        })

        assert test_path.exists()
        lines = test_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["query"] == "How to get FASTag refund?"
        assert record["url"] == "https://parivahan.gov.in/fastag/"
        assert record["domain"] == "transport"

    def test_thread_safe_concurrent_writes(self, tmp_path, monkeypatch):
        from backend.web_search import audit_log
        test_path = tmp_path / "pending_ingestion.jsonl"
        monkeypatch.setattr(audit_log, "PENDING_INGESTION_PATH", test_path)
        monkeypatch.setattr(audit_log, "ETL_DIR", tmp_path)

        from backend.web_search.audit_log import log_pending_ingestion
        errors = []

        def write_record(i):
            try:
                log_pending_ingestion({
                    "query": f"Query {i}",
                    "url": f"https://gov.in/page/{i}",
                    "domain": "tax",
                    "timestamp": "2026-11-02T17:00:00Z",
                    "snippet": f"Snippet {i}",
                })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_record, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        lines = test_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 20
        # All lines should be valid JSON
        for line in lines:
            record = json.loads(line)
            assert "query" in record

    def test_silently_handles_write_error(self, monkeypatch):
        """Audit log should never crash the live pipeline on write errors."""
        from backend.web_search import audit_log
        monkeypatch.setattr(audit_log, "PENDING_INGESTION_PATH", Path("/nonexistent_dir_xyz/test.jsonl"))
        monkeypatch.setattr(audit_log, "ETL_DIR", Path("/nonexistent_dir_xyz"))

        from backend.web_search.audit_log import log_pending_ingestion
        # Should not raise
        log_pending_ingestion({
            "query": "test",
            "url": "https://gov.in/",
            "domain": "tax",
            "timestamp": "2026-11-02T17:00:00Z",
            "snippet": "test",
        })


# ─── allowlist query builder tests ────────────────────────────────────────────

class TestBuildAllowlistQuery:
    def test_universal_site_suffix_on_all_queries(self):
        from backend.modules.domain_router import Domain
        from backend.web_search.allowlist import build_allowlist_query, _UNIVERSAL_SITE_SUFFIX
        q1 = build_allowlist_query("RC chassis mismatch correction", Domain.TRANSPORT)
        assert _UNIVERSAL_SITE_SUFFIX in q1
        assert "RC chassis mismatch correction" in q1

        q2 = build_allowlist_query("ITR defective notice 139(9)", Domain.TAXATION)
        assert _UNIVERSAL_SITE_SUFFIX in q2

        q3 = build_allowlist_query("some query", Domain.UNKNOWN)
        assert _UNIVERSAL_SITE_SUFFIX in q3

    def test_allowlist_domains_derived_from_tld_and_non_tld(self):
        from backend.web_search.allowlist import CIVIC_ALLOWLIST_DOMAINS, CIVIC_TLD_SUFFIXES, NON_TLD_OFFICIAL_DOMAINS
        assert CIVIC_ALLOWLIST_DOMAINS == CIVIC_TLD_SUFFIXES + NON_TLD_OFFICIAL_DOMAINS

    def test_verified_railway_domains_allowlisted(self):
        from backend.web_search.allowlist import is_allowlisted_url
        assert is_allowlisted_url("https://irctc.co.in/nget/train-search")
        assert is_allowlisted_url("https://rvnl.org/home")
        assert is_allowlisted_url("https://www.ircon.org/")
        assert is_allowlisted_url("https://cris.org.in/")


# ─── pipeline integration tests (mocked network) ─────────────────────────────

class TestPipelineWebSearchFallback:
    """Test that the pipeline correctly routes to web search when RAG confidence is low."""

    def test_web_search_not_triggered_when_disabled(self):
        """When WEB_SEARCH_ENABLED=False, web search is never invoked."""
        import backend.pipeline as pipeline_mod
        with patch.object(pipeline_mod, "WEB_SEARCH_ENABLED", False):
            with patch("backend.web_search.searcher.search_duckduckgo") as mock_search:
                from backend.schemas import AskRequest
                request = AskRequest(question="Hello", conversation_id="test-ws-off")
                try:
                    pipeline_mod.run(request)
                except Exception:
                    pass
                mock_search.assert_not_called()

    def test_web_search_triggered_when_confidence_low(self):
        """When WEB_SEARCH_ENABLED=True and RAG returns None, web search is triggered."""
        import backend.pipeline as pipeline_mod
        from backend.schemas import AskRequest

        mock_web_result = MagicMock()
        mock_web_result.url = "https://parivahan.gov.in/rc-correction"
        mock_web_result.title = "RC Correction Guide"
        mock_web_result.snippet = "Steps to correct chassis mismatch"

        with patch.object(pipeline_mod, "WEB_SEARCH_ENABLED", True):
            with patch.object(pipeline_mod, "WEB_SEARCH_CONFIDENCE_THRESHOLD", 0.75):
                with patch("backend.rag.runtime.retrieve_if_enabled", return_value=None):
                    with patch("backend.web_search.searcher.search_duckduckgo", return_value=[mock_web_result]) as mock_search:
                        with patch("backend.web_search.fetcher.fetch_page_text", return_value="RC chassis mismatch correction steps at RTO") as mock_fetch:
                            with patch("backend.web_search.synthesizer.synthesize_from_web") as mock_synth:
                                from backend.schemas import Answer
                                mock_synth.return_value = Answer(
                                    title="RC Correction",
                                    summary="Visit RTO for chassis correction.",
                                    last_verified=date.today(),
                                    confidence="low",
                                )
                                with patch("backend.web_search.audit_log.log_pending_ingestion"):
                                    request = AskRequest(
                                        question="How to fix RC chassis mismatch at Parivahan?",
                                        conversation_id="test-ws-trigger",
                                    )
                                    result = pipeline_mod.run(request)
                                    mock_search.assert_called_once()
                                    mock_fetch.assert_called_once_with(mock_web_result.url)
                                    mock_synth.assert_called_once()
                                    assert result.confidence == "low"


# ─── Deep link prioritization tests ──────────────────────────────────────────

class TestDeepLinkPrioritization:
    def test_deep_procedural_links_ranked_before_homepage(self):
        from backend.web_search.searcher import WebSearchResult, prioritize_deep_links

        results = [
            WebSearchResult(url="https://parivahan.gov.in/", title="Home", snippet="Welcome"),
            WebSearchResult(url="https://parivahan.gov.in/en", title="English Home", snippet="Welcome"),
            WebSearchResult(url="https://parivahan.gov.in/en/node/155", title="Alteration of Vehicle", snippet="Steps to change details"),
            WebSearchResult(url="https://parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml", title="Vahan Portal", snippet="Online service"),
        ]
        sorted_results = prioritize_deep_links(results)
        # Deep links must come first
        assert sorted_results[0].url == "https://parivahan.gov.in/en/node/155"
        assert sorted_results[1].url == "https://parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml"
        # Shallow portals must follow
        assert sorted_results[2].url == "https://parivahan.gov.in/"
        assert sorted_results[3].url == "https://parivahan.gov.in/en"


# ─── Boilerplate & DOM noise detection tests ──────────────────────────────────

class TestBoilerplateDetection:
    def test_identifies_navigation_noise(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        noisy_text = (
            "Skip to navigation Screen Reader Access Parivahan Front Page PopUp "
            "Driving License Related Services Various services Font size increase Copyright © All rights reserved"
        )
        assert is_navigation_or_boilerplate_text(noisy_text) is True

    def test_preserves_procedural_content(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        procedural_text = (
            "Step 1: Visit the official zonal RTO office with Form 29 and Form 30.\n"
            "Step 2: Submit physical chassis inspection report and verify engine pencil print.\n"
            "Step 3: Pay the required correction fee of Rs 300 and receive acknowledgment."
        )
        assert is_navigation_or_boilerplate_text(procedural_text) is False

    def test_identifies_markdown_table_directory_noise(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        table_text = (
            "| List of Acceptable Documents for Aadhaar Enrolment and Update Language: English Version | "
            "11-06-2026 | Format: PDFSize: 838.3 KB | | | Long term leasing policy for hiring accommodation "
            "for office purpose in Department of Posts Language: English Version | 03-06-2026 | "
            "Format: PDFSize: 11 MB | | | Compilation of Post Office Act, Rules and Regulations."
        )
        assert is_navigation_or_boilerplate_text(table_text) is True

    def test_identifies_pipeless_document_catalog_noise(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        catalog_text = (
            "List of Acceptable Documents for Aadhaar Enrolment Language: English Version 11-06-2026 "
            "Format: PDFSize: 838.3 KB Compilation of Post Office Act Rules and Regulations"
        )
        assert is_navigation_or_boilerplate_text(catalog_text) is True

    def test_preserves_numbered_steps_with_file_size(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        numbered_with_size = (
            "1. Download Form 29 (PDF, 50 KB) from the portal.\n"
            "2. Fill out details.\n"
            "3. Submit to RTO."
        )
        assert is_navigation_or_boilerplate_text(numbered_with_size) is False

    def test_preserves_lettered_steps_with_file_size(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        lettered_with_size = (
            "a) Download Form 29 (PDF, 50 KB)\n"
            "b) Fill out details"
        )
        assert is_navigation_or_boilerplate_text(lettered_with_size) is False

    def test_preserves_procedural_prose_with_file_size_limits(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        prose_with_size = (
            "To apply for duplicate RC, visit Parivahan portal. "
            "Upload your Aadhaar card and police complaint (scanned file size: 200 KB). "
            "Submit the form and pay fee."
        )
        assert is_navigation_or_boilerplate_text(prose_with_size) is False

    def test_identifies_multiline_markdown_table_listing(self):
        from backend.web_search.fetcher import is_navigation_or_boilerplate_text

        multiline_table = (
            "| Document Title | Release Date | File Size |\n"
            "|---|---|---|\n"
            "| Post Office Rules 2024 | 15-01-2024 | 1.2 MB |\n"
            "| Circular No 45 | 20-02-2024 | 450 KB |"
        )
        assert is_navigation_or_boilerplate_text(multiline_table) is True

    def test_trafilatura_extraction_omits_tables(self):
        from backend.web_search.fetcher import _extract_text

        html = """
        <html><body><main>
        <p>To claim MIS account funds without nomination up to Rs 5 Lakhs, submit Form 11 and an indemnity bond.</p>
        <table>
          <tr><th>Act</th><th>Date</th><th>Size</th></tr>
          <tr><td>Post Office Act</td><td>01-01-2020</td><td>10MB</td></tr>
        </table>
        </main></body></html>
        """
        extracted = _extract_text(html)
        assert "Form 11 and an indemnity bond" in extracted
        assert "Post Office Act" not in extracted
        assert "|" not in extracted

    def test_synthesizer_rejects_table_noise_extractive_fallback(self):
        from backend.web_search.synthesizer import synthesize_from_web, DISCRIMINATOR_FAILURE_PHRASE

        table_text = (
            "| List of Acceptable Documents | 11-06-2026 | Format: PDFSize: 838.3 KB |\n"
            "| Long term leasing policy | 03-06-2026 | Format: PDFSize: 11 MB |"
        )
        answer = synthesize_from_web(
            "How to claim Post Office MIS funds?",
            table_text,
            "https://www.indiapost.gov.in/documents/actsandpolicies",
        )
        assert DISCRIMINATOR_FAILURE_PHRASE in answer.summary
        assert answer.steps == []
        assert answer.confidence == "low"


# ─── Multi-result CRAG discriminator loop tests ───────────────────────────────

class TestDiscriminatorCRAGMultiResultLoop:
    def test_skips_boilerplate_first_hit_and_accepts_second_hit(self):
        """When hit 0 is DOM boilerplate, loop proceeds to hit 1 and accepts clean procedural steps."""
        import backend.pipeline as pipeline_mod
        from backend.schemas import Answer, AskRequest, Step
        from backend.web_search.searcher import WebSearchResult

        hit0 = WebSearchResult(
            url="https://parivahan.gov.in/",
            title="Parivahan Home",
            snippet="Government portal homepage",
        )
        hit1 = WebSearchResult(
            url="https://parivahan.gov.in/en/node/155",
            title="Alteration of Vehicle in RC",
            snippet="Procedures for correcting vehicle registration details",
        )

        hit0_text = "Skip to navigation Screen Reader Access Copyright © Parivahan"
        hit1_text = (
            "To correct chassis number mismatch in RC:\n"
            "1. Visit the registering authority (RTO) where vehicle was registered.\n"
            "2. Submit Form 29, 30 and physical engine/chassis pencil print verification.\n"
            "3. Pay statutory fee and obtain updated Registration Certificate."
        )

        valid_answer = Answer(
            title="Alteration of Vehicle Procedure (parivahan.gov.in)",
            summary="Visit registering authority with chassis pencil print and apply for alteration.",
            steps=[
                Step(title="Visit RTO", detail="Visit registering authority where vehicle was registered."),
                Step(title="Submit Verification", detail="Submit Form 29, 30 and pencil print."),
            ],
            confidence="high",
            source_url="https://parivahan.gov.in/en/node/155",
            last_verified=date.today(),
        )

        with patch.object(pipeline_mod, "WEB_SEARCH_ENABLED", True):
            with patch.object(pipeline_mod, "WEB_SEARCH_CONFIDENCE_THRESHOLD", 0.75):
                with patch("backend.rag.runtime.retrieve_if_enabled", return_value=None):
                    with patch("backend.web_search.searcher.search_duckduckgo", return_value=[hit0, hit1]):
                        def mock_fetch(url):
                            return hit0_text if url == hit0.url else hit1_text

                        with patch("backend.web_search.fetcher.fetch_page_text", side_effect=mock_fetch):
                            with patch("backend.web_search.synthesizer.synthesize_from_web", return_value=valid_answer) as mock_synth:
                                with patch("backend.web_search.audit_log.log_pending_ingestion") as mock_log:
                                    req = AskRequest(
                                        question="How to fix chassis number mismatch in Parivahan RC?",
                                        conversation_id="test-crag-loop",
                                    )
                                    ans = pipeline_mod.run(req)
                                    # Hit 0 was rejected by is_navigation_or_boilerplate_text, so synthesize was only called for hit 1!
                                    assert mock_synth.call_count == 1
                                    assert str(ans.source_url) == "https://parivahan.gov.in/en/node/155"
                                    mock_log.assert_called_once()
                                    assert mock_log.call_args[0][0]["url"] == "https://parivahan.gov.in/en/node/155"


# ─── Production transport and routing security tests ─────────────────────────

class TestProductionSearchSecurity:
    @staticmethod
    def _public_resolver(_host):
        return ("93.184.216.34",)

    def test_fetcher_enables_tls_and_disables_automatic_redirects(self):
        import httpx
        from backend.web_search.fetcher import fetch_page_text

        response = httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<main>Submit the application on the official portal and keep the acknowledgement.</main>",
            request=httpx.Request("GET", "https://example.gov.in/guide"),
        )
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.build_request.return_value = response.request
        client.send.return_value = response
        with patch("backend.web_search.fetcher.httpx.Client", return_value=client) as client_factory:
            text = fetch_page_text("https://example.gov.in/guide", resolver=self._public_resolver)
        assert "acknowledgement" in text
        assert client_factory.call_args.kwargs["verify"] is True
        assert client_factory.call_args.kwargs["follow_redirects"] is False

    def test_fetcher_rejects_redirect_to_unapproved_host_before_contact(self):
        import httpx
        from backend.web_search.fetcher import fetch_page_text

        redirect = httpx.Response(
            302,
            headers={"location": "https://example.com/steal"},
            request=httpx.Request("GET", "https://example.gov.in/start"),
        )
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.build_request.return_value = redirect.request
        client.send.return_value = redirect
        with patch("backend.web_search.fetcher.httpx.Client", return_value=client):
            assert fetch_page_text("https://example.gov.in/start", resolver=self._public_resolver) == ""
        assert client.send.call_count == 1

    def test_fetcher_rejects_private_dns_resolution_without_request(self):
        from backend.web_search.fetcher import fetch_page_text

        def private_resolver(_host):
            raise ValueError("non-public address")

        with patch("backend.web_search.fetcher.httpx.Client") as client_factory:
            assert fetch_page_text("https://example.gov.in/guide", resolver=private_resolver) == ""
        client_factory.assert_not_called()

    def test_fetcher_rejects_oversized_response(self):
        import httpx
        from backend.web_search.fetcher import fetch_page_text

        response = httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "5000"},
            content=b"small",
            request=httpx.Request("GET", "https://example.gov.in/guide"),
        )
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.build_request.return_value = response.request
        client.send.return_value = response
        with patch("backend.web_search.fetcher.httpx.Client", return_value=client):
            assert fetch_page_text(
                "https://example.gov.in/guide",
                resolver=self._public_resolver,
                max_bytes=100,
            ) == ""

    def test_allowlist_rejects_insecure_credentials_and_nonstandard_ports(self):
        from backend.web_search.allowlist import is_allowlisted_url

        assert not is_allowlisted_url("http://uidai.gov.in/guide")
        assert not is_allowlisted_url("https://user:pass@uidai.gov.in/guide")
        assert not is_allowlisted_url("https://uidai.gov.in:8443/guide")


class TestServiceAwareSearchRouting:
    def test_single_identical_suffix_across_domains(self):
        from backend.modules.domain_router import Domain
        from backend.web_search.allowlist import build_allowlist_query, _UNIVERSAL_SITE_SUFFIX

        q_onorc = build_allowlist_query("How can I use One Nation One Ration Card in another state?", Domain.IDENTITY)
        assert q_onorc.endswith(_UNIVERSAL_SITE_SUFFIX)

        q_mudra = build_allowlist_query("How do I apply for a MUDRA loan?", Domain.BANKING)
        assert q_mudra.endswith(_UNIVERSAL_SITE_SUFFIX)

    def test_explicit_site_constraint_filters_unrelated_allowlisted_results(self):
        from backend.web_search.searcher import _matches_query_site

        query = "RBI Ombudsman complaint site:rbi.org.in"
        assert _matches_query_site("https://www.rbi.org.in/complaints", query)
        assert not _matches_query_site("https://www.indiapost.gov.in/grievance", query)

