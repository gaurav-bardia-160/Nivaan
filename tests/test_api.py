from fastapi.testclient import TestClient

from backend.modules.privacy import mask_text
from backend.modules.router import route
from backend.main import app
from backend.pipeline import run
from backend.schemas import Answer, AskRequest

client = TestClient(app)

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


def test_pipeline_returns_answer_for_supported_question():
    answer = run(AskRequest(input_type="question", question="How do I apply for a PAN card?"))

    assert isinstance(answer, Answer)
    assert answer.title == "Apply for a new PAN card"
    assert answer.steps
    assert str(answer.source_url).startswith("https://")
    assert answer.confidence == "low"
    assert "unverified" in answer.summary.lower()


def test_pipeline_refuses_unsupported_question_without_guessing():
    answer = run(AskRequest(input_type="question", question="How do I apply for a passport?"))

    assert answer.title == "No verified guide found"
    assert answer.confidence == "low"
    assert "will not invent steps" in answer.summary
    assert answer.warnings[0].title == "Answer not grounded"


def test_health_endpoint():
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "govbank-assistant"
    assert payload["version"]
    assert payload["knowledge_entries"] == 3
    assert payload["unverified_entries"] == 3


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
    assert payload["confidence"] == "low"


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
