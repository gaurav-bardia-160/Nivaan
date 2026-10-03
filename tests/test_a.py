import json
from pathlib import Path

from backend.modules.retrieval import find_entry


def test_knowledge_base_exists_and_has_three_entries():
    path = Path(__file__).resolve().parents[1] / "backend" / "data" / "knowledge_base.json"
    assert path.exists(), "knowledge_base.json should exist"

    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 3


def test_find_pan_entry_for_common_question():
    result = find_entry("How do I get a PAN card?")
    assert result is not None
    assert "PAN" in result["title"] or "PAN" in result["summary"].upper()


def test_find_tax_entry_for_common_question():
    result = find_entry("How do I file my ITR?")
    assert result is not None
    assert "ITR" in result["title"] or "tax" in result["summary"].lower()


def test_find_entry_returns_none_for_random_question():
    result = find_entry("when does the moon turn into a banana")
    assert result is None
