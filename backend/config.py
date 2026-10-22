from __future__ import annotations

from pathlib import Path

APP_NAME = "GovBank Assistant API"
APP_VERSION = "0.5.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge_base.json"

SUPPORTED_LANGUAGES = ("en", "hi", "gu")
MAX_QUESTION_LENGTH = 1200
MAX_DOCUMENT_TEXT_LENGTH = 12000
MAX_CONVERSATION_ID_LENGTH = 120

DEFAULT_DISCLAIMER = None

import os

# Dynamic CORS configuration
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env:
    CORS_ALLOW_ORIGINS = [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
else:
    CORS_ALLOW_ORIGINS = ["*"]

CAPABILITIES = {
    "supported_languages": list(SUPPORTED_LANGUAGES),
    "answer_language_status": "English answers only by default. Hindi/Gujarati translation is available via TRANSLATION_ENABLED.",
    "supported_uploads": [".txt", ".text", ".md", ".csv", "text-based .pdf"],
    "unsupported_uploads": ["encrypted PDFs"],
    "privacy_boundary": "The current frontend masks supported sensitive identifiers before browser persistence, and the backend masks them again before retrieval, memory, translation, or local-model processing.",
    "knowledge_status": "Curated knowledge base with verified-first routing; unverified RAG corpus used as conservative fallback.",
}

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "PROJECT_ROOT",
    "BACKEND_DIR",
    "DATA_DIR",
    "KNOWLEDGE_BASE_PATH",
    "SUPPORTED_LANGUAGES",
    "MAX_QUESTION_LENGTH",
    "MAX_DOCUMENT_TEXT_LENGTH",
    "MAX_CONVERSATION_ID_LENGTH",
    "DEFAULT_DISCLAIMER",
    "CORS_ALLOW_ORIGINS",
    "CAPABILITIES",
]
