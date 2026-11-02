from __future__ import annotations

import os
import pytest
import backend.config


@pytest.fixture(autouse=True)
def _default_test_masking(monkeypatch):
    """Enable masking by default during automated test suite to preserve legacy contract tests."""
    monkeypatch.setenv("ENABLE_PII_MASKING", "true")
    backend.config.ENABLE_PII_MASKING = True
