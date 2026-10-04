from fastapi.testclient import TestClient

from backend.main import app
from backend.pipeline import run
from backend.schemas import Answer, AskRequest

client = TestClient(app)


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
    assert response.json() == {"status": "ok", "service": "govbank-assistant"}


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
