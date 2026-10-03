"""
Unit tests for Person B (Frontend Mock Data, Contracts, and Schema Verification).
Compatible with both pytest and unittest.
"""

import json
from pathlib import Path
import unittest
from backend.schemas import Answer, AskRequest

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class TestPersonBFrontendContracts(unittest.TestCase):
    def test_sample_answer_matches_schema(self):
        """Verify sample_answer.json parses cleanly into the Answer Pydantic model."""
        sample_path = FRONTEND_DIR / "sample_answer.json"
        self.assertTrue(sample_path.exists(), "sample_answer.json must exist")

        with open(sample_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validates against Answer schema
        answer = Answer(**data)
        self.assertTrue(answer.title != "")
        self.assertTrue(len(answer.steps) > 0)
        self.assertIn(answer.confidence, ("low", "medium", "high"))
        self.assertTrue(answer.source_url.startswith("http"))
        self.assertTrue(answer.disclaimer != "")


if __name__ == "__main__":
    unittest.main()
