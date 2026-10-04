from __future__ import annotations

from pathlib import Path

APP_NAME = "GovBank Assistant API"
APP_VERSION = "0.3.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge_base.json"

SUPPORTED_LANGUAGES = ("en", "hi", "gu")
MAX_QUESTION_LENGTH = 1200
MAX_DOCUMENT_TEXT_LENGTH = 12000
MAX_CONVERSATION_ID_LENGTH = 120

DEFAULT_DISCLAIMER = (
    "This is a plain-language explanation and guidance helper, not legal, tax, "
    "or financial advice. Confirm important details on the official source or with "
    "a qualified professional before acting."
)

# Local demo setting. Restrict this before real deployment.
CORS_ALLOW_ORIGINS = ["*"]

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
]
