"""
GovBank Assistant - FastAPI Entrypoint
"""

import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .schemas import AskRequest, Answer
from .config import BASE_DIR, PROJECT_ROOT

app = FastAPI(
    title="GovBank Assistant API",
    description="Explains Indian government, legal, and banking procedures in plain language.",
    version="0.1.0"
)

# Enable CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    """Health status check."""
    return {"status": "ok", "app": "GovBank Assistant"}


@app.post("/api/ask", response_model=Answer)
def ask_question(request: AskRequest):
    """
    Main endpoint for user queries.
    In Phase 0, returns the stub sample answer.
    """
    sample_path = PROJECT_ROOT / "frontend" / "sample_answer.json"
    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            sample_data = json.load(f)
            return Answer(**sample_data)

    return Answer(
        title="Stub Answer",
        summary=f"Received query: '{request.question}'. The pipeline will process this in Phase 1.",
        documents_needed=[],
        steps=[],
        warnings=[],
        source_url="https://india.gov.in",
        last_verified="2026-10-01",
        confidence="medium",
        masked_items=[],
        disclaimer="GovBank Assistant informational guidance only."
    )
