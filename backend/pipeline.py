from __future__ import annotations

from typing import Any

from backend.modules.explainer import explain_entry, not_found_answer
from backend.modules.privacy import mask_text
from backend.modules.retrieval import find_entry
from backend.modules.router import route
from backend.schemas import Answer, AskRequest


def _request_text(request: AskRequest) -> str:
    parts = [request.question or "", request.document_text or ""]
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def run(request: AskRequest | dict[str, Any]) -> Answer:
    """Run the safe backend workflow for typed text and document text.

    Current production boundary:
    - Supports typed questions and pasted document_text.
    - Masks obvious sensitive values server-side before retrieval/explanation.
    - Routes the request with deterministic rules.
    - Does not process uploaded file bytes yet because OCR/file handling is not built.
    - Never guesses outside the local knowledge base.
    """
    parsed_request = request if isinstance(request, AskRequest) else AskRequest(**request)
    raw_text = _request_text(parsed_request)
    masked = mask_text(raw_text)

    safe_request = parsed_request.model_copy(update={"question": parsed_request.question, "document_text": masked.text})
    route_result = route(safe_request)

    if route_result.needs_clarification and not route_result.matched_entry_id:
        return not_found_answer(masked.text or raw_text, masked_items=masked.masked_items)

    entry = find_entry(masked.text)
    if entry is None:
        return not_found_answer(masked.text or raw_text, masked_items=masked.masked_items)

    return explain_entry(entry, user_question=masked.text, masked_items=masked.masked_items)


__all__ = ["run"]
