from __future__ import annotations

from datetime import date

import httpx
import pytest

from backend.main import app
from backend.modules.llm import LocalLLMClient, LocalLLMConfig, enhance_grounded_answer
from backend.modules.memory import ConversationMemory, conversation_memory
from backend.pipeline import run
from backend.schemas import Answer, AskRequest, Citation, Step, Warning
from fastapi.testclient import TestClient


def _rag_answer() -> Answer:
    return Answer(
        title="Relevant official material: e-PAN",
        summary="Deterministic cited fallback summary.",
        documents_needed=[],
        steps=[Step(title="Read the evidence", detail="Use the official portal.")],
        warnings=[Warning(title="Verify details", message="Confirm current rules.")],
        source_url="https://www.incometax.gov.in/",
        last_verified=date(2026, 10, 1),
        confidence="low",
        citations=[
            Citation(
                title="Instant e-PAN",
                url="https://www.incometax.gov.in/iec/foportal/help/instant-e-pan",
                excerpt="Instant e-PAN is available through the Income Tax portal for eligible applicants using Aadhaar.",
                reported_last_verified=date(2026, 10, 1),
                factual_verification="unverified",
            )
        ],
    )


def test_memory_is_bounded_and_resolves_latest_entry():
    memory = ConversationMemory(max_conversations=2, max_turns=2, ttl_seconds=60)
    answer = _rag_answer().model_copy(update={"entry_id": "pan_card_new"})
    memory.remember("one", user_text="first", answer=answer)
    memory.remember("one", user_text="second", answer=answer)
    memory.remember("one", user_text="third", answer=answer)

    assert [turn.user_text for turn in memory.recent("one", limit=10)] == ["second", "third"]
    assert memory.latest_entry_id("one") == "pan_card_new"

    memory.remember("two", user_text="two", answer=answer)
    memory.remember("three", user_text="three", answer=answer)
    assert memory.recent("one") == ()
    assert memory.health()["conversations"] == 2


def test_pipeline_uses_redacted_backend_memory_for_follow_up():
    conversation_memory.clear("memory-test")
    first = run(
        AskRequest(
            input_type="question",
            question="My PAN is ABCDE1234F. How do I apply for a PAN card?",
            conversation_id="memory-test",
        )
    )
    follow_up = run(
        AskRequest(
            input_type="question",
            question="What documents do I need for that?",
            conversation_id="memory-test",
        )
    )

    assert first.entry_id == "pan_card_new"
    assert follow_up.entry_id == "pan_card_new"
    turns = conversation_memory.recent("memory-test")
    assert turns
    assert all("ABCDE1234F" not in turn.user_text for turn in turns)
    assert "[PAN]" in turns[0].user_text


def test_local_llm_rejects_remote_endpoint_without_explicit_opt_in():
    config = LocalLLMConfig(
        enabled=True,
        base_url="https://example.com",
        model="example",
        timeout_seconds=5,
        allow_remote=False,
    )
    with pytest.raises(ValueError, match="LOCAL_LLM_ALLOW_REMOTE"):
        LocalLLMClient(config)


def test_local_llm_rewrites_only_summary_and_preserves_grounded_contract(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": '{"summary":"Instant e-PAN is available through the Income Tax portal for eligible applicants using Aadhaar. Confirm eligibility on the official portal."}'
                }
            }

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse())
    config = LocalLLMConfig(
        enabled=True,
        base_url="http://127.0.0.1:11434",
        model="test-model",
        timeout_seconds=5,
        allow_remote=False,
    )
    original = _rag_answer()
    rewrite = LocalLLMClient(config).rewrite_summary(question="How do I get e-PAN?", answer=original)

    assert rewrite is not None
    enhanced = original.model_copy(update={"summary": rewrite})
    assert enhanced.summary != original.summary
    assert enhanced.citations == original.citations
    assert enhanced.steps == original.steps
    assert enhanced.source_url == original.source_url
    assert enhanced.confidence == original.confidence


def test_local_llm_failure_returns_exact_deterministic_answer(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "true")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    original = _rag_answer()

    assert enhance_grounded_answer(original, question="How do I get e-PAN?") == original


def test_conversation_delete_endpoint_clears_backend_memory():
    client = TestClient(app)
    conversation_memory.clear("delete-me")
    answer = run(AskRequest(question="How do I apply for PAN?", conversation_id="delete-me"))
    assert answer.entry_id == "pan_card_new"
    assert conversation_memory.latest_entry_id("delete-me") == "pan_card_new"

    response = client.delete("/api/conversations/delete-me")
    assert response.status_code == 200
    assert response.json()["status"] == "cleared"
    assert conversation_memory.recent("delete-me") == ()
