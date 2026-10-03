"""GovBank Assistant - FastAPI Entrypoint
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import DEFAULT_DISCLAIMER
from backend.modules.explainer import entry_to_answer
from backend.modules.retrieval import find_entry
from backend.schemas import Answer, AskRequest, Warning

app = FastAPI(
    title="GovBank Assistant API",
    description="Explains Indian government, legal, and banking procedures in plain language.",
    version="0.1.0",
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
    Match the user's question against a verified knowledge base entry and
    return the standard Answer schema.
    """
    if not request.question or not request.question.strip():
        return Answer(
            title="No question provided",
            summary="Please ask a specific question about a government procedure, form, notice, or banking rule.",
            documents_needed=[],
            steps=[],
            warnings=[
                Warning(
                    title="Missing input",
                    message="A valid question is required before I can match a verified guide.",
                    severity="warning",
                )
            ],
            source_url="https://www.india.gov.in",
            last_verified="2026-10-03",
            confidence="low",
            masked_items=[],
            disclaimer=DEFAULT_DISCLAIMER,
        )

    try:
        entry = find_entry(request.question)
        if entry is None:
            return Answer(
                title="No verified match found",
                summary=(
                    "I could not find a verified guide for this question in the current knowledge base. "
                    "Please rephrase the question or check the official government portal for the latest procedure."
                ),
                documents_needed=[],
                steps=[],
                warnings=[
                    Warning(
                        title="No match in verified knowledge",
                        message="The current knowledge base does not include a close verified match for this query.",
                        severity="warning",
                    )
                ],
                source_url="https://www.india.gov.in",
                last_verified="2026-10-03",
                confidence="low",
                masked_items=[],
                disclaimer=DEFAULT_DISCLAIMER,
            )

        return entry_to_answer(entry)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return Answer(
            title="Guide search failed",
            summary=f"The retrieval system could not complete the search: {exc}",
            documents_needed=[],
            steps=[],
            warnings=[
                Warning(
                    title="Technical issue",
                    message="Please try again or rephrase the request. The verified knowledge lookup failed.",
                    severity="critical",
                )
            ],
            source_url="https://www.india.gov.in",
            last_verified="2026-10-03",
            confidence="low",
            masked_items=[],
            disclaimer=DEFAULT_DISCLAIMER,
        )
