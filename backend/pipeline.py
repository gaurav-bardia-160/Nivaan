from __future__ import annotations

from typing import Any

from backend.modules.agent import route
from backend.modules.explainer import explain_entry, explain_rag_result, not_found_answer
from backend.modules.guardrails import find_flags, mask_text
from backend.modules.retrieval import find_entry, find_entry_by_id, find_entry_with_score
from backend.modules.translate_voice import apply_language_policy
from backend.rag.runtime import retrieve_if_enabled
from backend.schemas import Answer, AskRequest


def _request_text(request: AskRequest) -> str:
    parts = [request.question or "", request.document_text or ""]
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _verified_entry_covers_request(entry_id: str, text: str) -> bool:
    """Reject broad router matches when the verified guide does not cover the requested subtask."""
    lowered = text.lower()
    if entry_id == "pan_card_new":
        out_of_scope_intents = ("download", "reprint", "correction", "correct", "link aadhaar", "status")
        if any(intent in lowered for intent in out_of_scope_intents):
            return False
    return True


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
    masked_question = mask_text(parsed_request.question)
    masked_document = mask_text(parsed_request.document_text)
    masked_items = list({item.item_type: item for item in [*masked_question.masked_items, *masked_document.masked_items]}.values())
    safe_request = parsed_request.model_copy(
        update={
            "question": masked_question.text or None,
            "document_text": masked_document.text or None,
        }
    )
    safe_text = _request_text(safe_request)

    route_result = route(safe_request)

    entry = None
    if route_result.matched_entry_id:
        entry = find_entry_by_id(route_result.matched_entry_id)
    if not entry:
        entry, _ = find_entry_with_score(safe_text)

    # Prefer the small, manually verified procedure library whenever it has a
    # match. The broader imported RAG corpus is explicitly unverified and must
    # not replace a trusted workflow with a lower-confidence candidate passage.
    if entry is not None and _verified_entry_covers_request(entry.get("id", ""), safe_text):
        answer = explain_entry(entry, user_question=safe_text, masked_items=masked_items)
        if parsed_request.input_type == "document" and parsed_request.document_text:
            existing_titles = {warning.title for warning in answer.warnings}
            extra_warnings = [warning for warning in find_flags(masked_document.text) if warning.title not in existing_titles]
            answer = answer.model_copy(update={"warnings": [*answer.warnings, *extra_warnings]})
        return apply_language_policy(answer, parsed_request.language, query_text=safe_text)

    # Use RAG as a conservative fallback for supported PAN/Aadhaar requests
    # that are not covered by a verified procedure. This preserves citations
    # without allowing unverified chunks to override higher-trust guidance.
    rag_result = retrieve_if_enabled(safe_text, top_k=3)
    if rag_result is not None and rag_result.hits:
        rag_answer = explain_rag_result(rag_result, safe_text, masked_items=masked_items)
        if rag_answer is not None:
            if parsed_request.input_type == "document" and parsed_request.document_text:
                existing_titles = {warning.title for warning in rag_answer.warnings}
                extra_warnings = [
                    warning for warning in find_flags(masked_document.text)
                    if warning.title not in existing_titles
                ]
                rag_answer = rag_answer.model_copy(update={"warnings": [*rag_answer.warnings, *extra_warnings]})
            return apply_language_policy(rag_answer, parsed_request.language, query_text=safe_text)

    if route_result.needs_clarification and not route_result.matched_entry_id:
        return apply_language_policy(not_found_answer(safe_text, masked_items=masked_items), parsed_request.language, query_text=safe_text)

    return apply_language_policy(not_found_answer(safe_text, masked_items=masked_items), parsed_request.language, query_text=safe_text)


__all__ = ["run"]
