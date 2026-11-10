from __future__ import annotations

import json
from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.modules.memory import conversation_memory


@pytest.fixture(autouse=True)
def clean_memory():
    conversation_memory.clear("test-stream-conv")
    yield
    conversation_memory.clear("test-stream-conv")


def test_ask_stream_greeting():
    client = TestClient(app)
    response = client.post(
        "/api/ask/stream",
        json={
            "input_type": "question",
            "question": "Hello",
            "conversation_id": "test-stream-conv",
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    raw_text = response.text
    events = []
    for part in raw_text.split("\n\n"):
        if not part.strip():
            continue
        lines = part.strip().split("\n")
        event_name = None
        data_str = None
        for line in lines:
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
        if event_name and data_str:
            events.append((event_name, json.loads(data_str)))

    event_names = [e[0] for e in events]
    assert "status" in event_names
    assert "meta" in event_names
    assert "token" in event_names
    assert "done" in event_names

    # Check meta event structure
    meta = next(e[1] for e in events if e[0] == "meta")
    assert "title" in meta
    assert meta["confidence"] in ("verified", "high", "medium", "low")

    # Check token events
    tokens = [e[1]["delta"] for e in events if e[0] == "token"]
    assert len(tokens) > 0
    full_streamed_text = "".join(tokens)
    assert len(full_streamed_text.strip()) > 5

    # Check done event
    done = next(e[1] for e in events if e[0] == "done")
    assert "answer" in done
    answer = done["answer"]
    assert answer["title"]
    assert answer["summary"]


def test_ask_stream_verified_query():
    client = TestClient(app)
    response = client.post(
        "/api/ask/stream",
        json={
            "input_type": "question",
            "question": "How do I apply for a PAN card?",
            "conversation_id": "test-stream-conv",
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    raw_text = response.text
    events = []
    for part in raw_text.split("\n\n"):
        if not part.strip():
            continue
        lines = part.strip().split("\n")
        event_name = None
        data_str = None
        for line in lines:
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
        if event_name and data_str:
            events.append((event_name, json.loads(data_str)))

    event_names = [e[0] for e in events]
    assert "status" in event_names
    assert "meta" in event_names
    assert "token" in event_names
    assert "done" in event_names

    done = next(e[1] for e in events if e[0] == "done")
    answer = done["answer"]
    assert "pan" in answer["title"].lower()
    assert len(answer["steps"]) >= 1


def test_ask_stream_unsupported_query():
    client = TestClient(app)
    response = client.post(
        "/api/ask/stream",
        json={
            "input_type": "question",
            "question": "Can I bake a chocolate cake with pan card?",
            "conversation_id": "test-stream-conv",
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    raw_text = response.text
    assert "event: done" in raw_text
    assert "No verified guide found" in raw_text
