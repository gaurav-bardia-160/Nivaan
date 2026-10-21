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
    assert result.matched_entry_id == "itr_filing_basics"
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
    assert answer.title == "Apply for a new PAN card"
    assert answer.steps
    assert str(answer.source_url).startswith("https://")
    assert answer.confidence == "medium"
    assert "unverified" not in answer.summary.lower()


def test_pipeline_refuses_unsupported_question_without_guessing():
    answer = run(AskRequest(input_type="question", question="How do I apply for a passport?"))

    assert answer.title == "No verified guide found"
    assert answer.confidence == "low"
    assert "will not invent steps" in answer.summary
    assert answer.warnings[0].title == "Answer not grounded"


def test_live_rag_is_feature_flagged_and_returns_cited_candidate_evidence(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "true")
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "How can I download e-PAN?", "language": "en"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] == "low"
    assert payload["citations"]
    assert payload["citations"][0]["factual_verification"] == "unverified"
    assert payload["citations"][0]["url"].startswith("https://")
    assert "not been independently fact-checked" in payload["summary"]

    health = client.get("/api/health").json()["rag"]
    assert health["enabled"] is True
    assert health["ready"] is True
    assert health["documents"] == 681


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
    assert payload["title"] == "Apply for a new PAN card"
    assert payload["citations"] == []
    assert client.get("/api/health").json()["rag"]["enabled"] is False


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "govbank-assistant"
    assert payload["version"] == "0.4.0"
    assert payload["knowledge_entries"] >= 10
    assert payload["unverified_entries"] == 0
    assert payload["capabilities_url"] == "/api/capabilities"


def test_capabilities_endpoint_reports_honest_limits():
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "0.4.0"
    assert "text-based .pdf" in payload["supported_uploads"]
    assert "images" in payload["unsupported_uploads"]
    assert "English answers only" in payload["answer_language_status"]
    assert "Client-side masking is not implemented" in payload["privacy_boundary"]
    assert "translation" in payload
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
    assert payload["title"] == "Understand a loan agreement"
    assert payload["steps"]
    assert payload["warnings"]
    assert payload["source_url"].startswith("https://")
    assert payload["confidence"] == "medium"


def test_ask_endpoint_non_english_request_warns_without_fake_translation():
    response = client.post(
        "/api/ask",
        json={"input_type": "question", "question": "How do I apply for a PAN card?", "language": "hi"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Apply for a new PAN card"
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
    assert response.json()["title"] == "Apply for a new PAN card"


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
    assert turn1["entry_id"] == "pan_card_new"
    assert turn1["title"] == "Apply for a new PAN card"

    # Turn 2: User asks follow-up referencing previous topic
    turn2_res = client.post(
        "/api/ask",
        json={
            "question": "What documents do I need for that?",
            "previous_entry_id": turn1["entry_id"],
            "language": "en",
        },
    )
    assert turn2_res.status_code == 200
    turn2 = turn2_res.json()
    assert turn2["entry_id"] == "pan_card_new"
    assert turn2["title"] == "Apply for a new PAN card"
    assert len(turn2["documents_needed"]) >= 3

    # Turn 3: User asks follow-up about fees
    turn3_res = client.post(
        "/api/ask",
        json={
            "question": "What is the fee?",
            "previous_entry_id": turn1["entry_id"],
            "language": "en",
        },
    )
    assert turn3_res.status_code == 200
    turn3 = turn3_res.json()
    assert turn3["entry_id"] == "pan_card_new"

    # Turn 4: User switches to an independent topic - must NOT use previous_entry_id
    turn4_res = client.post(
        "/api/ask",
        json={
            "question": "How do I file ITR?",
            "previous_entry_id": turn1["entry_id"],
            "language": "en",
        },
    )
    assert turn4_res.status_code == 200
    turn4 = turn4_res.json()
    assert turn4["entry_id"] == "itr_filing_basics"
    assert "Income Tax Return" in turn4["title"]

    # Turn 5: User asks an unrelated out-of-scope query - must NOT use previous_entry_id
    turn5_res = client.post(
        "/api/ask",
        json={
            "question": "What is the capital of France?",
            "previous_entry_id": turn1["entry_id"],
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

    # Requests 1 and 2 should pass
    r1 = client.post("/api/ask", json={"question": "apply pan card", "language": "en"})
    assert r1.status_code == 200
    r2 = client.post("/api/ask", json={"question": "apply pan card", "language": "en"})
    assert r2.status_code == 200

    # Request 3 should be throttled
    r3 = client.post("/api/ask", json={"question": "apply pan card", "language": "en"})
    assert r3.status_code == 429
    assert "Too Many Requests" in r3.json()["detail"]

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
