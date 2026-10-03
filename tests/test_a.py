"""
Unit tests for Person A (Knowledge Base, Schema Conformance, and Data Integrity).
Compatible with both pytest and unittest.
"""

import json
from pathlib import Path
import unittest
from backend.schemas import KnowledgeEntry, Answer

DATA_DIR = Path(__file__).resolve().parent.parent / "backend" / "data"


class TestPersonAKnowledgeBase(unittest.TestCase):
    def test_knowledge_base_loads(self):
        """Verify knowledge_base.json exists and is valid JSON."""
        kb_path = DATA_DIR / "knowledge_base.json"
        self.assertTrue(kb_path.exists(), "knowledge_base.json must exist")

        with open(kb_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, list), "Knowledge base must be a list of entries"

    def test_verified_entries_have_required_fields(self):
        """Every verified entry must have title, steps, source, date, and status."""
        kb_path = DATA_DIR / "knowledge_base.json"
        with open(kb_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for entry_dict in data:
            entry = KnowledgeEntry(**entry_dict)
            self.assertTrue(entry.title.strip() != "", "Title cannot be empty")
            self.assertTrue(len(entry.steps) > 0, "Must have at least one step")
            self.assertTrue(entry.source_url.startswith("http"), "Source URL must be valid HTTP(S)")
            self.assertEqual(len(entry.last_verified), 10, "last_verified must be YYYY-MM-DD")
            self.assertIn(entry.status, ("verified", "unverified"))


if __name__ == "__main__":
    unittest.main()
