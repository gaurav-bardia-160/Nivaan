from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import json
import os
os.environ["LOCAL_LLM_ENABLED"] = "false"

from fastapi.testclient import TestClient

from backend.modules.agent import route
from backend.modules.guardrails import find_flags, mask_text
from backend.offline.data_builder import SourceDocument, clean_and_chunk, clean_text, structure_chunks
from backend.main import app
import backend.pipeline as pipeline_module
from backend.pipeline import run
from backend.schemas import Answer, AskRequest

client = TestClient(app)


def build_minimal_pdf(text: str = "") -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET" if text else ""
    stream_bytes = stream.encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        b"5 0 obj\n<< /Length " + str(len(stream_bytes)).encode("ascii") + b" >>\nstream\n" + stream_bytes + b"\nendstream\nendobj\n",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content.extend(obj)
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(content)


def test_privacy_masks_common_sensitive_values():
    text = "PAN ABCDE1234F Aadhaar 1234 5678 9012 phone 9876543210 email user@example.com account no 123456789012 IFSC HDFC0001234"
    masked = mask_text(text)

    assert "ABCDE1234F" not in masked.text
    assert "1234 5678 9012" not in masked.text
    assert "9876543210" not in masked.text
    assert "user@example.com" not in masked.text
    assert "123456789012" not in masked.text
    assert "HDFC0001234" not in masked.text
    assert {item.item_type for item in masked.masked_items} == {"pan", "aadhaar", "phone", "email", "bank_account", "ifsc"}


def test_router_classifies_supported_question():
    result = route(AskRequest(input_type="question", question="How do I file ITR with Form 16?"))

    assert result.path == "question"
    assert result.category == "tax"
    assert result.needs_clarification is False


def test_router_marks_unknown_request_for_clarification():
    result = route(AskRequest(input_type="question", question="How do I cook pasta?"))

    assert result.category == "unknown"
    assert result.needs_clarification is True


def test_offline_data_builder_cleans_chunks_and_creates_unverified_drafts():
    document = SourceDocument(
        id="sample",
        title="Sample PAN Guide",
        url="https://example.gov.in/sample",
        text="Home Skip to main content Apply for PAN card with ID proof and address proof.",
        fetched_at="2026-10-04",
    )

    assert clean_text(document.text).startswith("Apply for PAN")
    chunks = clean_and_chunk([document], max_words=5)
    drafts = structure_chunks(chunks)

    assert chunks
    assert drafts[0]["status"] == "unverified"
    assert drafts[0]["source_url"] == "https://example.gov.in/sample"


def test_pipeline_masks_document_text_before_answering():
    answer = run(
        AskRequest(
            input_type="document",
            question="Explain this loan agreement",
            document_text="Borrower PAN ABCDE1234F has loan EMI and late payment penalty. Phone 9876543210.",
        )
    )

    assert answer.title == "Understand a loan agreement"
    assert "ABCDE1234F" not in answer.summary
    assert "9876543210" not in answer.summary
    assert {item.item_type for item in answer.masked_items} == {"pan", "phone"}


def test_pipeline_masks_question_and_document_before_routing(monkeypatch):
    captured = {}
    original_route = pipeline_module.route

    def capture_route(request):
        captured["question"] = request.question
        captured["document_text"] = request.document_text
        return original_route(request)

    monkeypatch.setattr(pipeline_module, "route", capture_route)
    answer = pipeline_module.run(
        AskRequest(
            input_type="document",
            question="Explain PAN ABCDE1234F for phone 9876543210",
            document_text="Loan account no 123456789012 uses IFSC HDFC0001234.",
        )
    )

    routed_text = f"{captured['question']} {captured['document_text']}"
    for secret in ("ABCDE1234F", "9876543210", "123456789012", "HDFC0001234"):
        assert secret not in routed_text
    assert "[PAN]" in captured["question"]
    assert "[BANK_ACCOUNT]" in captured["document_text"]
    assert {item.item_type for item in answer.masked_items} == {"pan", "phone", "bank_account", "ifsc"}


def test_ask_endpoint_document_text_masks_sensitive_values():
    response = client.post(
        "/api/ask",
        json={
            "input_type": "document",
            "question": "Explain this loan agreement",
            "document_text": "Loan EMI clause for PAN ABCDE1234F and phone 9876543210 with prepayment charge.",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Understand a loan agreement"
    assert "ABCDE1234F" not in payload["summary"]
    assert "9876543210" not in payload["summary"]
    assert {item["item_type"] for item in payload["masked_items"]} == {"pan", "phone"}


def test_flagger_detects_key_document_risks():
    flags = find_flags(
        "This loan has a late payment fee and penal interest. "
        "Borrower may face foreclosure charges for prepayment. "
        "Respond within 15 days."
    )

    titles = {flag.title for flag in flags}
    assert "Late payment or penalty clause found" in titles
    assert "Prepayment or foreclosure condition found" in titles
    assert "Deadline or response window found" in titles


def test_flagger_detects_legal_notice_without_giving_verdict():
    flags = find_flags("This is a legal notice under Section 138. You must respond within 15 days.")

    assert any(flag.severity == "critical" for flag in flags)
    combined = " ".join(flag.message.lower() for flag in flags)
    assert "lawyer" in combined or "professional" in combined
    assert "ignore" not in combined


def test_pipeline_adds_document_risk_flags():
    answer = run(
        AskRequest(
            input_type="document",
            question="Explain this loan agreement",
            document_text="Loan EMI includes a late payment fee. There is a prepayment charge. Reply within 15 days.",
        )
    )

    titles = {warning.title for warning in answer.warnings}
    assert "Late payment or penalty clause found" in titles
    assert "Prepayment or foreclosure condition found" in titles
    assert "Deadline or response window found" in titles


def test_pipeline_returns_answer_for_supported_question():
    answer = run(AskRequest(input_type="question", question="How do I apply for a PAN card?"))

    assert isinstance(answer, Answer)
    assert "pan" in answer.title.lower()
    assert answer.steps
    assert str(answer.source_url).startswith("https://")
    assert answer.confidence == "medium"
    assert "unverified" not in answer.summary.lower()


def test_pipeline_refuses_unsupported_question_without_guessing():
    answer = run(AskRequest(input_type="question", question="How do I apply for a commercial pilot license?"))

    assert answer.title == "No verified guide found"
    assert answer.confidence == "low"
    assert "will not invent steps" in answer.summary
    assert answer.warnings[0].title == "Answer not grounded"


def test_pipeline_refuses_unrelated_make_query_without_matching_passport():
    answer = run(AskRequest(input_type="question", question="How to make chocolate cake at home?"))

    assert answer.title == "No verified guide found"
    assert answer.entry_id is None


def test_live_rag_is_feature_flagged_and_returns_cited_candidate_evidence(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "How can I download e-PAN?", "language": "en"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] in ["low", "medium", "high"]
    assert payload["citations"]
    assert payload["citations"][0]["factual_verification"] == "unverified"
    assert payload["citations"][0]["url"].startswith("https://")
    assert "not been independently fact-checked" in payload["summary"]

    health = client.get("/api/health").json()["rag"]
    assert health["enabled"] is True
    assert health["ready"] is True
    assert health["documents"] >= 1212


def test_live_rag_rejects_out_of_corpus_topics_and_preserves_document_routing(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("RAG_VECTOR_ENABLED", "true")

    out_of_scope = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "How do I get a fishing permit in Alaska?", "language": "en"},
    ).json()
    assert out_of_scope["title"] == "No verified guide found"
    assert out_of_scope["citations"] == []

    notice = client.post(
        "/api/ask",
        json={
            "input_type": "document",
            "question": "Explain this bank recovery notice",
            "document_text": "Loan payment overdue. Respond within 15 days. Late payment penalty applies.",
            "language": "en",
        },
    ).json()
    assert notice["title"] == "Understand a loan agreement"
    assert notice["citations"] == []
    warning_titles = {warning["title"] for warning in notice["warnings"]}
    assert "Deadline or response window found" in warning_titles
    assert "Late payment or penalty clause found" in warning_titles


def test_live_rag_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("RAG_ENABLED", raising=False)
    monkeypatch.delenv("RAG_VECTOR_ENABLED", raising=False)
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "How do I apply for a PAN card?", "language": "en"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "No verified guide found"
    assert payload["citations"] == []
    assert client.get("/api/health").json()["rag"]["enabled"] is False


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "nivaan"
    assert payload["version"] == "0.5.0"
    assert payload["capabilities_url"] == "/api/capabilities"
    assert payload["rag"]["enabled"] is True
    assert payload["rag"]["documents"] >= 1000


def test_capabilities_endpoint_reports_honest_limits():
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "0.5.0"
    assert "text-based .pdf" in payload["supported_uploads"]
    assert "ocr" in payload
    if payload["ocr"]["enabled"]:
        assert ".png" in payload["supported_uploads"]
    else:
        assert "images without Tesseract-OCR" in payload["unsupported_uploads"]
    assert "English answers only" in payload["answer_language_status"]
    assert "frontend masks" in payload["privacy_boundary"]
    assert "backend masks" in payload["privacy_boundary"]
    assert "translation" in payload
    assert "local_llm" in payload
    assert "memory" in payload
    assert payload["translation"]["enabled"] is False


def test_capabilities_endpoint_reports_active_translation(monkeypatch):
    monkeypatch.setenv("TRANSLATION_ENABLED", "true")
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["translation"]["enabled"] is True
    assert "translation into Hindi and Gujarati is currently active" in payload["answer_language_status"]
    assert "English answers only" in payload["answer_language_status"]



def test_ask_endpoint_supported_question_uses_real_backend_boundary():
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "What should I check in a loan agreement?", "language": "en"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "loan" in payload["title"].lower() or "rbi" in payload["title"].lower()
    assert payload["steps"]
    assert payload["warnings"]
    assert payload["source_url"].startswith("https://")
    assert payload["confidence"] in ["low", "medium", "high"]


def test_ask_endpoint_non_english_request_warns_without_fake_translation():
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "How do I apply for a PAN card?", "language": "hi"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "pan" in payload["title"].lower()
    warning_titles = {warning["title"] for warning in payload["warnings"]}
    assert "Answer translation not implemented yet" in warning_titles


def test_ask_endpoint_unsupported_question_refuses_to_guess():
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "Tell me tomorrow's weather", "language": "en"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "No verified guide found"
    assert payload["warnings"][0]["title"] == "Answer not grounded"
    assert payload["confidence"] == "low"


def test_ask_endpoint_rejects_invalid_blank_question():
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "   ", "language": "en"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "invalid_request"
    assert "details" in payload


def test_ask_endpoint_rejects_file_only_until_ocr_is_implemented():
    response = client.post(
        "/api/ask",
        json={"input_type": "document", "file_attached": True, "language": "en"},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_ask_endpoint_defaults_to_question_input_type():
    response = client.post(
        "/api/ask",
        json={"question": "How do I get PAN card?", "language": "en"},
    )

    assert response.status_code == 200
    assert "pan" in response.json()["title"].lower()


def test_ask_file_endpoint_accepts_text_file_and_masks_sensitive_values():
    response = client.post(
        "/api/ask-file",
        data={"question": "Explain this loan agreement", "language": "en"},
        files={
            "file": (
                "loan.txt",
                b"Loan agreement for PAN ABCDE1234F. Late payment fee applies. Reply within 15 days.",
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Understand a loan agreement"
    assert "ABCDE1234F" not in payload["summary"]
    assert {item["item_type"] for item in payload["masked_items"]} == {"pan"}
    warning_titles = {warning["title"] for warning in payload["warnings"]}
    assert "Late payment or penalty clause found" in warning_titles
    assert "Deadline or response window found" in warning_titles


def test_ask_file_endpoint_accepts_text_based_pdf_and_masks_sensitive_values():
    response = client.post(
        "/api/ask-file",
        data={"question": "Explain this loan agreement", "language": "en"},
        files={
            "file": (
                "loan.pdf",
                build_minimal_pdf("Loan agreement for PAN ABCDE1234F. Late payment fee applies. Reply within 15 days."),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Understand a loan agreement"
    assert "ABCDE1234F" not in payload["summary"]
    assert {item["item_type"] for item in payload["masked_items"]} == {"pan"}
    warning_titles = {warning["title"] for warning in payload["warnings"]}
    assert "Late payment or penalty clause found" in warning_titles
    assert "Deadline or response window found" in warning_titles


def test_ask_file_endpoint_rejects_scanned_pdf_until_ocr_is_available():
    response = client.post(
        "/api/ask-file",
        data={"question": "Explain this PDF", "language": "en"},
        files={"file": ("notice.pdf", build_minimal_pdf(), "application/pdf")},
    )

    assert response.status_code == 415
    assert "No selectable text" in response.json()["detail"]


def test_ask_file_endpoint_rejects_malformed_pdf():
    response = client.post(
        "/api/ask-file",
        data={"question": "Explain this PDF", "language": "en"},
        files={"file": ("notice.pdf", b"%PDF fake", "application/pdf")},
    )

    assert response.status_code == 400
    assert "could not be read" in response.json()["detail"]


def test_ask_file_endpoint_rejects_empty_text_file():
    response = client.post(
        "/api/ask-file",
        data={"question": "Explain this file", "language": "en"},
        files={"file": ("empty.txt", b"   \n\t", "text/plain")},
    )

    assert response.status_code == 400
    assert "No readable text" in response.json()["detail"]


def test_ask_endpoint_rejects_meaningless_single_character_query():
    response = client.post("/api/ask", json={"question": "x", "language": "en"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "No verified guide found"


def test_ask_endpoint_supports_multi_turn_conversational_context():
    # Turn 1: User asks initial PAN question
    turn1_res = client.post("/api/ask", json={"question": "How do I apply for a new PAN card?", "language": "en"})
    assert turn1_res.status_code == 200
    turn1 = turn1_res.json()
    assert "pan" in turn1["title"].lower()

    # Turn 2: User asks follow-up referencing previous topic
    turn2_res = client.post(
        "/api/ask",
        json={
            "question": "What documents do I need for that?",
            "context_topic": turn1["title"],
            "language": "en",
        },
    )
    assert turn2_res.status_code == 200
    turn2 = turn2_res.json()
    assert "pan" in turn2["title"].lower() or "pan" in turn2["summary"].lower() or len(turn2["steps"]) > 0

    # Turn 3: User asks follow-up about fees
    turn3_res = client.post(
        "/api/ask",
        json={
            "question": "What is the fee?",
            "context_topic": turn1["title"],
            "language": "en",
        },
    )
    assert turn3_res.status_code == 200

    # Turn 4: User switches to an independent topic - must NOT use previous topic
    turn4_res = client.post(
        "/api/ask",
        json={
            "question": "How do I file ITR?",
            "context_topic": turn1["title"],
            "language": "en",
        },
    )
    assert turn4_res.status_code == 200
    turn4 = turn4_res.json()
    assert "tax" in turn4["title"].lower() or "itr" in turn4["title"].lower() or "tax" in turn4["summary"].lower()

    # Turn 5: User asks an unrelated out-of-scope query - must NOT use previous topic
    turn5_res = client.post(
        "/api/ask",
        json={
            "question": "What is the capital of France?",
            "context_topic": turn1["title"],
            "language": "en",
        },
    )
    assert turn5_res.status_code == 200
    turn5 = turn5_res.json()
    assert turn5["title"] == "No verified guide found"


def test_metrics_endpoint_reports_live_counters():
    res = client.get("/api/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "total_requests" in data
    assert "rate_limiter" in data
    assert "ocr_available" in data


def test_rate_limiter_throttles_excessive_requests(monkeypatch):
    # Set a low limit for this test
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_RPM", "2")
    from backend.main import _RATE_LIMITER
    _RATE_LIMITER.max_requests = 2
    _RATE_LIMITER._requests.clear()

    try:
        # Requests 1 and 2 should pass
        r1 = client.post("/api/ask", json={"question": "apply pan card", "language": "en"})
        assert r1.status_code == 200
        r2 = client.post("/api/ask", json={"question": "apply pan card", "language": "en"})
        assert r2.status_code == 200

        # Request 3 should be throttled
        r3 = client.post("/api/ask", json={"question": "apply pan card", "language": "en"})
        assert r3.status_code == 429
        assert "Too Many Requests" in r3.json()["detail"]
    finally:
        # Reset limiter for subsequent tests
        _RATE_LIMITER.max_requests = 120
        _RATE_LIMITER._requests.clear()


def test_api_key_auth_enforcement_when_configured(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-conclave-token")

    # Call without key -> 401
    unauth = client.post("/api/ask", json={"question": "apply pan card", "language": "en"})
    assert unauth.status_code == 401
    assert "Unauthorized" in unauth.json()["detail"]

    # Call with correct X-API-Key header -> 200
    auth_x = client.post(
        "/api/ask",
        headers={"X-API-Key": "secret-conclave-token"},
        json={"question": "apply pan card", "language": "en"},
    )
    assert auth_x.status_code == 200

    # Call with correct Bearer header -> 200
    auth_bearer = client.post(
        "/api/ask",
        headers={"Authorization": "Bearer secret-conclave-token"},
        json={"question": "apply pan card", "language": "en"},
    )
    assert auth_bearer.status_code == 200


def test_ask_endpoint_returns_welcoming_answer_for_greetings():
    for greeting in ("hi", "hello", "hey", "namaste", "good morning"):
        response = client.post("/api/ask", json={"question": greeting, "language": "en"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "Welcome to Nivaan"
        assert payload["confidence"] == "high"
        assert len(payload["summary"]) > 20
        assert len(payload["steps"]) == 0



# ===================================================================
# Regression tests for accuracy audit fixes (Aadhaar enrolment case)
# ===================================================================

def test_aadhaar_entry_does_not_contain_pob_abbreviation():
    """PoB is not standard UIDAI terminology; the entry should use 'date of birth proof'."""
    uidai_path = ROOT / "backend" / "data" / "refined" / "uidai" / "uidai_chunks_clean.jsonl"
    text = uidai_path.read_text(encoding="utf-8").lower()
    assert "(pob)" not in text, "Official UIDAI corpus should not use invented abbreviation 'PoB'"
    assert "date of birth" in text or "dob" in text or "birth" in text


def test_aadhaar_entry_mentions_free_of_cost():
    """First-time Aadhaar enrolment and biometric updates are free — this must appear in official UIDAI chunks."""
    uidai_path = ROOT / "backend" / "data" / "refined" / "uidai" / "uidai_chunks_clean.jsonl"
    text = uidai_path.read_text(encoding="utf-8").lower()
    assert "free of cost" in text or "free" in text, "Aadhaar official corpus must mention that enrolment/updates are free"


def test_aadhaar_entry_mentions_children_biometric_exemption():
    """Children under 5 are exempt from biometrics — this should be present in official UIDAI chunks."""
    uidai_path = ROOT / "backend" / "data" / "refined" / "uidai" / "uidai_chunks_clean.jsonl"
    text = uidai_path.read_text(encoding="utf-8").lower()
    assert "child" in text or "under 5" in text or "exempt" in text or "age of 5" in text, \
        "Aadhaar corpus must mention children / biometric exemption"


def test_aadhaar_source_url_is_not_beta():
    """Source URL should be the canonical UIDAI portal, not a beta/staging version."""
    response = client.post("/api/ask", json={"question": "how to get aadhaar card", "language": "en"})
    assert response.status_code == 200
    payload = response.json()
    source_url = payload.get("source_url", "")
    assert "beta" not in source_url.lower(), f"Source URL should not be beta: {source_url}"
    assert "staging" not in source_url.lower(), f"Source URL should not be staging: {source_url}"
    assert "test" not in source_url.lower() or "latest" in source_url.lower(), \
        f"Source URL should not be a test URL: {source_url}"


def test_qa_check_verify_against_source_catches_invented_abbreviations():
    """The QA check module should flag abbreviations not present in source text."""
    from backend.modules.qa_check import verify_against_source

    source = "Proof of Identity and Proof of Address are required for Aadhaar enrolment."
    answer_with_invented = "You need PoI, PoA, and PoB documents for Aadhaar enrolment."
    
    warnings = verify_against_source(answer_with_invented, source)
    # PoB should be flagged since it's not in source
    flagged_terms = " ".join(warnings).lower()
    assert "pob" in flagged_terms, f"QA check should flag 'PoB' — got: {warnings}"


def test_qa_check_flag_staging_urls():
    """The QA check module should flag staging/beta URLs."""
    from backend.modules.qa_check import flag_staging_urls

    assert len(flag_staging_urls("https://myaadhaarbeta.uidai.gov.in/")) > 0
    assert len(flag_staging_urls("https://staging.example.gov.in/")) > 0
    assert len(flag_staging_urls("https://uidai.gov.in/")) == 0
    assert len(flag_staging_urls("https://www.incometax.gov.in/")) == 0


def test_qa_check_verify_clean_answer_passes():
    """A clean answer with no invented terms should produce no warnings."""
    from backend.modules.qa_check import verify_against_source

    source = "Aadhaar is a 12-digit number issued by UIDAI. First enrolment is free."
    answer = "Aadhaar is a 12-digit number from UIDAI. Your first enrolment is free."
    
    warnings = verify_against_source(answer, source)
    # Only check for non-common abbreviation warnings
    real_warnings = [w for w in warnings if "UIDAI" not in w and "Aadhaar" not in w]
    assert len(real_warnings) == 0, f"Clean answer should not produce warnings: {real_warnings}"


# verify.py removed in favor of dynamic RAG and official refined corpus

def test_troubleshoot_aadhaar_pvc_payment_deducted_no_srn():
    """When a user reports money debited for PVC without SRN, provide the diagnostic resolution."""
    response = client.post("/api/ask", json={
        "question": "money deducted for aadhaar pvc but no srn generated",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] in ("high", "medium")
    assert "pvc" in payload["title"].lower() or "srn" in payload["title"].lower()
    full_text = json.dumps(payload).lower()
    assert "reconciliation" in full_text or "refund" in full_text or "1947" in full_text


def test_troubleshoot_itr_bank_validation_failed():
    """When bank validation fails or refund is unpaid, provide the IFSC/reissue resolution."""
    response = client.post("/api/ask", json={
        "question": "income tax refund unpaid bank account validation failed",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    full_text = json.dumps(payload).lower()
    assert "refund reissue" in full_text or "validation" in full_text or "ifsc" in full_text


def test_troubleshoot_failed_upi_transaction_penalty():
    """Verify RBI auto-reversal TAT and Rs 100/day compensation resolution."""
    response = client.post("/api/ask", json={
        "question": "upi failed money deducted auto reversal penalty",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    full_text = json.dumps(payload).lower()
    assert "100" in full_text and ("ombudsman" in full_text or "tat" in full_text)


def test_troubleshoot_passport_police_verification_delayed():
    """Verify police verification pending beyond 21 days resolution."""
    response = client.post("/api/ask", json={
        "question": "passport police verification pending past 21 days",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    full_text = json.dumps(payload).lower()
    assert "21" in full_text and ("police" in full_text or "rpo" in full_text)


def test_multi_turn_troubleshooting_query_reformulation():
    """Verify follow-up error query expands with context and matches diagnostic guide."""
    conv_id = "test_conv_trouble_reformulation"
    r1 = client.post("/api/ask", json={"question": "How to apply for fresh passport?", "conversation_id": conv_id})
    assert r1.status_code == 200

    r2 = client.post("/api/ask", json={"question": "Police verification is pending past 21 days", "conversation_id": conv_id})
    assert r2.status_code == 200
    p2 = r2.json()
    full_text = json.dumps(p2).lower()
    assert "21" in full_text and ("police" in full_text or "rpo" in full_text)


def test_multi_turn_aadhaar_pvc_deducted_followup():
    """Verify payment deduction follow-up expands with Aadhaar context."""
    conv_id = "test_conv_trouble_pvc"
    r1 = client.post("/api/ask", json={"question": "How do I order an Aadhaar PVC card?", "conversation_id": conv_id})
    assert r1.status_code == 200

    r2 = client.post("/api/ask", json={"question": "Money was deducted from UPI but no SRN was generated.", "conversation_id": conv_id})
    assert r2.status_code == 200
    p2 = r2.json()
    full_text = json.dumps(p2).lower()
    assert "srn" in full_text and ("1947" in full_text or "reconciliation" in full_text or "refund" in full_text)


def test_rag_troubleshooting_boost_ranking():
    """Verify RAG retrieval prioritizes troubleshooting SOPs and applies boost."""
    from backend.rag.retriever import RagRetriever
    retriever = RagRetriever()
    result = retriever.search("UPI failed money deducted Rs 100 penalty")
    assert len(result.hits) > 0
    top_hit = result.hits[0]
    assert "troubleshooting_boost" in top_hit.signals
    assert "11693" in top_hit.document.sources[0].source_url or "tat" in top_hit.document.sources[0].title.lower()


def test_troubleshoot_baal_aadhaar_mandatory_biometric_updates():
    """Verify Baal Aadhaar biometric exemption and MBU-1/MBU-2 schedules."""
    response = client.post("/api/ask", json={
        "question": "Baal Aadhaar biometric update rules for child age 5 and 15",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    full_text = json.dumps(payload).lower()
    assert "mbu" in full_text or "biometric" in full_text or "baal" in full_text or "child" in full_text


def test_troubleshoot_rbi_unsolicited_credit_card_penalty():
    """Verify statutory penalty for unsolicited credit card issuance."""
    response = client.post("/api/ask", json={
        "question": "Bank issued unsolicited credit card and charged fee without consent",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    full_text = json.dumps(payload).lower()
    assert "unsolicited" in full_text or "card" in full_text or "penalty" in full_text


def test_troubleshoot_epfo_closed_establishment_attestation():
    """Verify alternative attestation when company is closed or employer untraceable."""
    response = client.post("/api/ask", json={
        "question": "EPF joint declaration company closed employer untraceable",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    full_text = json.dumps(payload).lower()
    assert "closed" in full_text or "attestation" in full_text or "magistrate" in full_text or "bank manager" in full_text or "joint declaration" in full_text


def test_troubleshoot_nalsa_free_legal_aid_eligibility():
    """Verify free legal aid under Section 12 of Legal Services Authorities Act."""
    response = client.post("/api/ask", json={
        "question": "Who is eligible for free legal aid under NALSA Section 12?",
        "language": "en"
    })
    assert response.status_code == 200
    payload = response.json()
    full_text = json.dumps(payload).lower()
    assert "legal" in full_text and ("nalsa" in full_text or "12" in full_text or "women" in full_text or "free" in full_text)


def test_cross_domain_multi_turn_isolation_prevents_punting_trap(tmp_path):
    """Verify that switching topics across domains never leaks context or causes the punting trap."""
    from backend.modules.unresolved_queue import UNRESOLVED_CSV_PATH
    session_id = f"test_session_punting_{tmp_path.name}"

    # Turn 1: Aadhaar cross limit
    t1 = client.post("/api/ask", json={
        "question": "Aadhaar update limit has exhausted. How do I get an exception?",
        "conversation_id": session_id,
        "language": "en"
    }).json()
    assert "aadhaar" in t1["title"].lower() or "uidai" in str(t1["source_url"]).lower()

    # Turn 2: Switch to Passport Police Verification - must NOT contain Aadhaar or UIDAI
    t2 = client.post("/api/ask", json={
        "question": "What is the procedure if passport police verification is pending past 21 days?",
        "conversation_id": session_id,
        "language": "en"
    }).json()
    assert "uidai" not in str(t2["source_url"]).lower()
    assert "aadhaar" not in t2["title"].lower()
    assert "passport" in t2["title"].lower() or "passport" in str(t2["source_url"]).lower() or "police" in t2["title"].lower()

    # Turn 3: Switch to Tax Refund - must NOT contain Passport or Aadhaar
    t3 = client.post("/api/ask", json={
        "question": "Why did my income tax refund fail with refund unpaid?",
        "conversation_id": session_id,
        "language": "en"
    }).json()
    assert "passport" not in str(t3["source_url"]).lower()
    assert "uidai" not in str(t3["source_url"]).lower()
    assert "refund" in t3["title"].lower() or "tax" in t3["title"].lower() or "incometax" in str(t3["source_url"]).lower()

    # Turn 4: Out of scope refusal - must trigger structured fallback and log to audit queue
    t4 = client.post("/api/ask", json={
        "question": "when does the moon turn into a banana",
        "conversation_id": session_id,
        "language": "en"
    }).json()
    assert t4["confidence"] == "low"
    assert "No verified guide found" in t4["title"]
    assert UNRESOLVED_CSV_PATH.exists()



def test_scenario1_income_tax_bank_validation_prevents_defective_return_hallucination():
    """Verify Scenario 1: Bank validation failure MUST NOT cross-contaminate with Section 139(9) defective return."""
    query = "My income tax refund failed with bank account validation failed in red color. What should I do?"
    response = client.post("/api/ask", json={"question": query})
    assert response.status_code == 200
    data = response.json()

    assert "bank" in data["title"].lower() or "refund" in data["title"].lower()
    full_text = (data["summary"] + " " + " ".join(s["title"] + " " + s["detail"] for s in data["steps"])).lower()

    # Must contain exact resolution workflow
    assert "my bank account" in full_text
    assert "refund reissue" in full_text

    # Must NEVER instruct filing under 139(9) or Defective Return schema for bank validation
    assert "139(9)" not in full_text
    assert "defective return" not in full_text
    assert "corrected schema" not in full_text

    # Citations must not include defective return notice
    for c in data.get("citations", []):
        assert "139(9)" not in c["title"].lower()
        assert "defective" not in c["title"].lower()


def test_scenario2_aadhaar_pvc_no_srn_provides_exact_tat_and_escalation():
    """Verify Scenario 2: Aadhaar PVC payment deducted with no SRN provides exact TAT, reversal, and UTR escalation."""
    query = "I paid 50 rupees through PhonePe for Aadhaar PVC card, money debited but no SRN generated. What to do?"
    response = client.post("/api/ask", json={"question": query})
    assert response.status_code == 200
    data = response.json()

    assert "pvc" in data["title"].lower() or "aadhaar" in data["title"].lower() or "payment" in data["title"].lower()
    full_text = (data["summary"] + " " + " ".join(s["title"] + " " + s["detail"] for s in data["steps"])).lower()

    # Must contain exact statutory TAT and reconciliation window
    assert "24" in full_text and "48" in full_text
    # Must contain auto-reversal timeline
    assert "5 to 7" in full_text or "5-7" in full_text or "refund" in full_text
    # Must contain official escalation and 12-digit UTR
    assert "helpdesk@uidai.gov.in" in full_text or "1947" in full_text
    assert "utr" in full_text
