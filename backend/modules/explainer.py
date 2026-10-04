from __future__ import annotations

from typing import Any

from backend.config import DEFAULT_DISCLAIMER
from backend.schemas import Answer, KnowledgeEntry, MaskedItem, Step, Warning

NOT_FOUND_SOURCE_URL = "https://www.india.gov.in/"
NOT_FOUND_LAST_VERIFIED = "2026-10-03"


def _to_entry(entry: KnowledgeEntry | dict[str, Any]) -> KnowledgeEntry:
    if isinstance(entry, KnowledgeEntry):
        return entry
    return KnowledgeEntry(**entry)


def explain_entry(
    entry: KnowledgeEntry | dict[str, Any],
    user_question: str,
    masked_items: list[MaskedItem] | None = None,
) -> Answer:
    """Build a source-grounded answer from one verified/curated knowledge entry.

    This first production-safe explainer is deterministic on purpose. It does not call
    an external AI model yet, so it cannot invent facts. Later, an LLM can rewrite the
    summary, but the source URL, date, checklist, warnings, and disclaimer should still
    be copied from trusted data in code.
    """
    clean_question = " ".join(user_question.strip().split())
    if len(clean_question) > 240:
        clean_question = f"{clean_question[:237]}..."
    knowledge = _to_entry(entry)

    summary = knowledge.summary
    if knowledge.status != "verified":
        summary = (
            f"{summary} Note: this guide is currently marked unverified in the project data, "
            "so re-check the official source before using it for a real task."
        )

    if clean_question:
        summary = f"For your question, '{clean_question}', this is the closest guide I found. {summary}"

    return Answer(
        title=knowledge.title,
        summary=summary,
        documents_needed=knowledge.documents_needed,
        steps=[Step(title=step.title, detail=step.detail) for step in knowledge.steps],
        warnings=[
            Warning(title=warning.title, message=warning.message, severity=warning.severity)
            for warning in knowledge.warnings
        ],
        source_url=knowledge.source.url,
        last_verified=knowledge.source.last_verified,
        confidence="medium" if knowledge.status == "verified" else "low",
        masked_items=masked_items or [],
        disclaimer=DEFAULT_DISCLAIMER,
    )


def not_found_answer(user_question: str, masked_items: list[MaskedItem] | None = None) -> Answer:
    clean_question = " ".join(user_question.strip().split()) or "your request"
    if len(clean_question) > 240:
        clean_question = f"{clean_question[:237]}..."
    return Answer(
        title="No verified guide found",
        summary=(
            f"I could not find a close enough verified guide for '{clean_question}'. "
            "To avoid guessing, this assistant will not invent steps. Please check the relevant "
            "official portal or add a verified guide to the knowledge base first."
        ),
        documents_needed=[],
        steps=[
            Step(
                title="Check an official source",
                detail="Use an official government, regulator, court, or bank website instead of blogs or agent websites.",
            ),
            Step(
                title="Add a verified guide before demoing this task",
                detail="The project should only answer tasks that exist in knowledge_base.json with a source and date.",
            ),
        ],
        warnings=[
            Warning(
                title="Answer not grounded",
                message="No matching local guide was found, so the system is intentionally refusing to guess.",
                severity="warning",
            )
        ],
        source_url=NOT_FOUND_SOURCE_URL,
        last_verified=NOT_FOUND_LAST_VERIFIED,
        confidence="low",
        masked_items=masked_items or [],
        disclaimer=DEFAULT_DISCLAIMER,
    )


__all__ = ["DEFAULT_DISCLAIMER", "explain_entry", "not_found_answer"]
