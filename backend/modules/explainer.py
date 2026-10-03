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
    """Accept either a KnowledgeEntry instance or a mapping and validate it."""
    if isinstance(entry, KnowledgeEntry):
        return entry
    if isinstance(entry, Mapping):
        return KnowledgeEntry(**dict(entry))
    raise TypeError("Expected a KnowledgeEntry instance or a dictionary-like mapping.")


def _coerce_step(step: Any) -> Step:
    if isinstance(step, Step):
        return step
    if isinstance(step, Mapping):
        no = int(step.get("no", 1))
        text = str(step.get("text") or step.get("detail") or "").strip()
        tip = step.get("tip")
        return Step(no=no, text=text, tip=tip)
    return Step(no=1, text=str(step).strip(), tip=None)


def _coerce_warning(warning: Any) -> Warning:
    if isinstance(warning, Warning):
        return warning
    if isinstance(warning, Mapping):
        text = str(warning.get("text") or warning.get("message") or "").strip()
        reason = str(warning.get("reason") or warning.get("severity") or "").strip()
        source = str(warning.get("source") or "Official source").strip()
        return Warning(text=text, reason=reason, source=source)
    return Warning(text=str(warning).strip(), reason="", source="Official source")


def entry_to_answer(entry: Any) -> Answer:
    """Convert a verified knowledge entry into the frontend-safe Answer contract."""
    knowledge = _coerce_entry(entry)

    steps = [_coerce_step(item) for item in list(getattr(knowledge, "steps", []) or [])]
    warnings = []

    # Convert common_mistakes to warnings
    for item in list(getattr(knowledge, "common_mistakes", []) or []):
        warnings.append(
            Warning(
                text=str(item).strip(),
                reason="Common mistake to avoid",
                source=str(getattr(knowledge, "source_url", "https://www.india.gov.in")).strip(),
            )
        )

    # Build summary from title and first step
    summary = str(getattr(knowledge, "title", "")).strip()
    if steps:
        summary = f"{summary}. {steps[0].text}"

    return Answer(
        title=str(getattr(knowledge, "title", "")).strip(),
        summary=summary.strip(),
        documents_needed=list(getattr(knowledge, "documents", []) or []),
        steps=steps,
        warnings=warnings,
        source_url=str(getattr(knowledge, "source_url", "https://www.india.gov.in")).strip(),
        last_verified=str(getattr(knowledge, "last_verified", "2026-10-03")).strip(),
        confidence="high",
        masked_items=[],
        disclaimer=DEFAULT_DISCLAIMER,
    )


__all__ = ["entry_to_answer", "_coerce_entry"]
