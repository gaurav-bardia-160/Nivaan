"""Helpers for converting verified knowledge entries into final Answer objects."""

from __future__ import annotations

from typing import Any, Mapping

try:
    from backend.config import DEFAULT_DISCLAIMER
    from backend.schemas import Answer, KnowledgeEntry, Step, Warning
except ImportError:  # pragma: no cover - supports running uvicorn from backend/ folder
    from config import DEFAULT_DISCLAIMER
    from schemas import Answer, KnowledgeEntry, Step, Warning


def _coerce_entry(entry: Any) -> KnowledgeEntry:
    if isinstance(entry, KnowledgeEntry):
        return entry
    if isinstance(entry, Mapping):
        return KnowledgeEntry(**dict(entry))
    raise TypeError("Expected a KnowledgeEntry instance or a dictionary-like mapping.")


def _coerce_step(step: Any) -> Step:
    if isinstance(step, Step):
        return step
    if isinstance(step, Mapping):
        return Step(
            title=str(step.get("title", "")).strip(),
            detail=step.get("detail"),
        )
    return Step(title=str(step).strip(), detail=None)


def _coerce_warning(warning: Any) -> Warning:
    if isinstance(warning, Warning):
        return warning
    if isinstance(warning, Mapping):
        return Warning(
            title=str(warning.get("title", "")).strip(),
            message=str(warning.get("message", "")).strip(),
            severity=str(warning.get("severity", "warning")),
        )
    return Warning(title=str(warning).strip(), message="", severity="warning")


def entry_to_answer(entry: Any) -> Answer:
    knowledge = _coerce_entry(entry)

    source = getattr(knowledge, "source", None)
    source_url = "https://www.india.gov.in"
    last_verified = "2026-10-03"

    if source is not None:
        source_url = str(getattr(source, "url", source_url))
        last_verified = str(getattr(source, "last_verified", last_verified))

    steps = [_coerce_step(item) for item in list(getattr(knowledge, "steps", []) or [])]
    warnings = [_coerce_warning(item) for item in list(getattr(knowledge, "warnings", []) or [])]

    return Answer(
        title=str(knowledge.title).strip(),
        summary=str(knowledge.summary).strip(),
        documents_needed=list(getattr(knowledge, "documents_needed", []) or []),
        steps=steps,
        warnings=warnings,
        source_url=source_url,
        last_verified=last_verified,
        confidence="high",
        masked_items=[],
        disclaimer=DEFAULT_DISCLAIMER,
    )


__all__ = ["entry_to_answer", "_coerce_entry"]
