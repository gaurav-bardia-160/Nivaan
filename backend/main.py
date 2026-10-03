"""
GovBank Assistant - FastAPI Entrypoint
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import PROJECT_ROOT
from backend.modules.explainer import entry_to_answer
from backend.modules.retrieval import find_entry
from backend.schemas import Answer, AskRequest

app = FastAPI(
    title="GovBank Assistant API",
    description="Explains Indian government, legal, and banking procedures in plain language.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "GovBank Assistant"}


@app.post("/api/ask", response_model=Answer)
def ask_question(request: AskRequest):
    if not request.question:
        raise ValueError("Question must not be empty.")

    entry = find_entry(request.question)
    if entry is not None:
        return entry_to_answer(entry)

    sample_path = PROJECT_ROOT / "frontend" / "sample_answer.json"
    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            sample_data = json.load(f)
            return Answer(**sample_data)

    return Answer(
        title="Stub Answer",
        summary=f"Received query: '{request.question}'. No verified match was found in the knowledge base.",
        documents_needed=[],
        steps=[],
        warnings=[],
        source_url="https://india.gov.in",
        last_verified="2026-10-01",
        confidence="medium",
        masked_items=[],
        disclaimer="GovBank Assistant informational guidance only.",
    )
