import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.modules.retrieval import find_entry
from backend.schemas import AskRequest, KnowledgeEntry

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_PATH = ROOT / "backend" / "data" / "knowledge_base.json"


def _knowledge_entries():
    data = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    return [KnowledgeEntry(**entry) for entry in data]


def test_knowledge_base_exists_has_three_entries_and_valid_schema():
    assert KNOWLEDGE_PATH.exists(), "knowledge_base.json should exist"
    entries = _knowledge_entries()
    assert len(entries) >= 10
    ids = {entry.id for entry in entries}
    assert "pan_card_new" in ids
    assert "itr_filing_basics" in ids
    assert "loan_agreement_explainer" in ids


def test_knowledge_entries_have_required_retrieval_and_trust_fields():
    for entry in _knowledge_entries():
        assert entry.keywords, f"{entry.id} should include retrieval keywords"
        assert entry.steps, f"{entry.id} should include user-facing steps"
        assert entry.source.url, f"{entry.id} should include a source URL"
        assert entry.source.last_verified, f"{entry.id} should include a source date"
        assert entry.status in ["verified", "unverified"], "early demo entries should not be marked verified until live official checks are done"


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("How do I get a PAN card?", "pan_card_new"),
        ("how to make paspot", "passport_application_new"),
        ("passport", "passport_application_new"),
        ("pan", "pan_card_new"),
        ("Form 49A", "pan_card_new"),
        ("permanent account number", "pan_card_new"),
        ("How do I file my ITR?", "itr_filing_basics"),
        ("itr", "itr_filing_basics"),
        ("Form 16", "itr_filing_basics"),
        ("income tax return", "itr_filing_basics"),
        ("loan agreement", "loan_agreement_explainer"),
        ("late payment penalty", "loan_agreement_explainer"),
        ("prepayment charges", "loan_agreement_explainer"),
        ("emi", "loan_agreement_explainer"),
    ],
)
def test_find_entry_handles_common_short_and_full_queries(query, expected_id):
    result = find_entry(query)
    assert result is not None
    assert result["id"] == expected_id


@pytest.mark.parametrize(
    "query",
    [
        "when does the moon turn into a banana",
        "commercial pilot license",
        "weather tomorrow",
        "college admission form",
    ],
)
def test_find_entry_returns_none_for_unsupported_questions(query):
    assert find_entry(query) is None


def test_ask_request_rejects_blank_question():
    with pytest.raises(ValidationError):
        AskRequest(input_type="question", question="   ")


def test_ask_request_accepts_clean_question_and_strips_whitespace():
    request = AskRequest(input_type="question", question="   How do I get a PAN card?   ", language="en")
    assert request.question == "How do I get a PAN card?"


def test_ask_request_requires_document_text_or_question_and_rejects_unprocessed_file_only():
    with pytest.raises(ValidationError):
        AskRequest(input_type="document", file_attached=False)
    with pytest.raises(ValidationError):
        AskRequest(input_type="document", file_attached=True)
    assert AskRequest(input_type="document", document_text="Loan agreement text").document_text == "Loan agreement text"
    assert AskRequest(input_type="document", question="Explain this notice").question == "Explain this notice"


def test_find_entry_rejects_single_character_and_meaningless_queries():
    assert find_entry("x") is None
    assert find_entry("a") is None
    assert find_entry("?") is None
    assert find_entry("1") is None
