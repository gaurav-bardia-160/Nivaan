from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

APP_NAME = "Nivaan API"
APP_VERSION = "0.5.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent

# Load local environment variables from project directory before reading any env vars
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = BACKEND_DIR / "data"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge_base.json"

# ETL Pipeline directories (Phase 2 — offline write path only)
ETL_DIR = DATA_DIR / "etl"
ETL_RAW_DIR = ETL_DIR / "raw"
ETL_REFINED_DIR = ETL_DIR / "refined"
ETL_ARCHIVE_DIR = ETL_DIR / "archive"
PENDING_INGESTION_PATH = ETL_DIR / "pending_ingestion.jsonl"

# Web Search Feature Flags
_is_pytest = "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST") is not None
WEB_SEARCH_ENABLED = (
    os.getenv("WEB_SEARCH_ENABLED", "false").lower() in ("true", "1", "yes")
    and not (_is_pytest and not os.getenv("TEST_LIVE_WEB_SEARCH"))
)
WEB_SEARCH_CONFIDENCE_THRESHOLD = float(os.getenv("WEB_SEARCH_CONFIDENCE_THRESHOLD", "0.75"))
ETL_INTERVAL_HOURS = int(os.getenv("ETL_INTERVAL_HOURS", "4"))

SUPPORTED_LANGUAGES = ("en", "hi", "gu")
MAX_QUESTION_LENGTH = 1200
MAX_DOCUMENT_TEXT_LENGTH = 12000
MAX_CONVERSATION_ID_LENGTH = 120

DEFAULT_DISCLAIMER = None

# Dynamic CORS configuration
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env:
    CORS_ALLOW_ORIGINS = [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
else:
    CORS_ALLOW_ORIGINS = ["*"]

# PII Masking & Web Search Privacy Boundary:
# When WEB_SEARCH_ENABLED is true, outbound queries leave the local boundary.
# Enforce fail-closed privacy: if web search is enabled, PII masking is mandatory.
_raw_pii = os.getenv("ENABLE_PII_MASKING")
if WEB_SEARCH_ENABLED:
    if _raw_pii is not None and _raw_pii.strip().lower() in ("false", "0", "no"):
        raise RuntimeError(
            "Fail-closed privacy boundary error: WEB_SEARCH_ENABLED is True, but ENABLE_PII_MASKING is explicitly False. "
            "Citizen queries must not be dispatched over external networks without active PII masking. "
            "Set ENABLE_PII_MASKING=true or disable WEB_SEARCH_ENABLED."
        )
    ENABLE_PII_MASKING = True
else:
    ENABLE_PII_MASKING = (_raw_pii or "false").strip().lower() in ("true", "1", "yes")

CAPABILITIES = {
    "supported_languages": list(SUPPORTED_LANGUAGES),
    "answer_language_status": "English answers only by default. Hindi/Gujarati translation is available via TRANSLATION_ENABLED.",
    "supported_uploads": [".txt", ".text", ".md", ".csv", "text-based .pdf"],
    "unsupported_uploads": ["encrypted PDFs"],
    "privacy_boundary": (
        "100% on-device local execution via Ollama. No cloud transmission. "
        "The current frontend masks supported sensitive identifiers before browser persistence, "
        "and the backend masks them again before retrieval, memory, translation, or local-model processing when ENABLE_PII_MASKING is active."
    ),
    "knowledge_status": "Curated knowledge base with verified-first routing; unverified RAG corpus used as conservative fallback.",
}

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "PROJECT_ROOT",
    "BACKEND_DIR",
    "DATA_DIR",
    "KNOWLEDGE_BASE_PATH",
    "ETL_DIR",
    "ETL_RAW_DIR",
    "ETL_REFINED_DIR",
    "ETL_ARCHIVE_DIR",
    "PENDING_INGESTION_PATH",
    "WEB_SEARCH_ENABLED",
    "WEB_SEARCH_CONFIDENCE_THRESHOLD",
    "ETL_INTERVAL_HOURS",
    "SUPPORTED_LANGUAGES",
    "MAX_QUESTION_LENGTH",
    "MAX_DOCUMENT_TEXT_LENGTH",
    "MAX_CONVERSATION_ID_LENGTH",
    "DEFAULT_DISCLAIMER",
    "CORS_ALLOW_ORIGINS",
    "CAPABILITIES",
    "ENABLE_PII_MASKING",
]
