"""
Configuration management for GovBank Assistant backend.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"

# Load backend/.env if it exists
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Settings
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

AI_PROVIDER = os.getenv("AI_PROVIDER", "none")
AI_API_KEY = os.getenv("AI_API_KEY", "")

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY", "")
BHASHINI_USER_ID = os.getenv("BHASHINI_USER_ID", "")

# Standard disclaimer
DEFAULT_DISCLAIMER = (
    "GovBank Assistant provides step-by-step guidance based exclusively on verified official portals. "
    "It is not a legal, tax, or financial advisor. Please confirm specific fees, requirements, and deadlines "
    "on the official portal before making decisions."
)
