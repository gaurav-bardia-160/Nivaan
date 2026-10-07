from __future__ import annotations

from typing import Any

from backend.modules.agent import route
from backend.modules.explainer import explain_entry, not_found_answer
from backend.modules.guardrails import find_flags, mask_text
from backend.modules.retrieval import find_entry, find_entry_by_id
from backend.modules.translate_voice import apply_language_policy
from backend.schemas import Answer, AskRequest


def _request_text(request: AskRequest) -> str:
    parts = [request.question or "", request.document_text or ""]
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def run(request: AskRequest | dict[str, Any]) -> Answer:
    """Run the safe backend workflow for typed text and supported uploads.

    Current production boundary:
    - Supports typed questions, pasted document_text, .txt uploads, and text-based PDF uploads.
    - Masks obvious sensitive values server-side before retrieval/explanation.
    - Routes the request with deterministic agent rules.
    - Adds conservative rule-based warnings for document text.
    - Returns English answers only and warns honestly for non-English answer requests.
    - Never guesses outside the local knowledge base.
    """
    parsed_request = request if isinstance(request, AskRequest) else AskRequest(**request)
    raw_text = _request_text(parsed_request)
    masked = mask_text(raw_text)

    safe_request = parsed_request.model_copy(update={"question": parsed_request.question, "document_text": masked.text})
    route_result = route(safe_request)

    if route_result.needs_clarification and not route_result.matched_entry_id:
        return apply_language_policy(not_found_answer(masked.text or raw_text, masked_items=masked.masked_items), parsed_request.language)

    entry = None
    if route_result.matched_entry_id:
        entry = find_entry_by_id(route_result.matched_entry_id)
    if not entry:
        entry = find_entry(masked.text)

    if entry is None:
        return apply_language_policy(not_found_answer(masked.text or raw_text, masked_items=masked.masked_items), parsed_request.language)

    answer = explain_entry(entry, user_question=masked.text, masked_items=masked.masked_items)
    if parsed_request.input_type == "document" and parsed_request.document_text:
        existing_titles = {warning.title for warning in answer.warnings}
        extra_warnings = [warning for warning in find_flags(masked.text) if warning.title not in existing_titles]
        answer = answer.model_copy(update={"warnings": [*answer.warnings, *extra_warnings]})
    return apply_language_policy(answer, parsed_request.language)


__all__ = ["run"]
