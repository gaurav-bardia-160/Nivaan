from __future__ import annotations

from typing import Any

from backend.modules.agent import route
from backend.modules.explainer import explain_entry, explain_rag_result, not_found_answer
from backend.modules.guardrails import find_flags, mask_text
from backend.modules.llm import enhance_grounded_answer
from backend.modules.memory import conversation_memory
from backend.modules.retrieval import find_entry, find_entry_by_id, find_entry_with_score
from backend.modules.translate_voice import apply_language_policy
from backend.modules.translator import extract_language_and_clean_query
from backend.rag.runtime import retrieve_if_enabled
from backend.schemas import Answer, AskRequest


_FOLLOW_UP_MARKERS = {
    "that", "this", "it", "its", "same", "above", "these", "those", "here", "there",
    # Hindi/Hinglish pronouns
    "iska", "iski", "iske", "uska", "uski", "uske", "yeh", "ye", "woh", "wo", "isme", "usme",
    # Gujarati pronouns
    "ana", "ama", "te", "tenu",
}

_FOLLOW_UP_INTENTS = {
    "document", "documents", "doc", "docs", "proof", "proofs", "paper", "papers", "paperwork",
    "step", "steps", "procedure", "process", "apply", "requirement", "requirements",
    "fee", "fees", "cost", "charge", "charges", "price", "penalty", "free", "pay",
    "time", "days", "duration", "tat", "deadline", "long", "when",
    "status", "track", "tracking", "check", "verify",
    "eligibility", "eligible", "criteria", "who can",
    # Hindi/Gujarati intents
    "dastavej", "kagaj", "paisa", "shulk", "samay", "kya", "kaise",
}


def _has_anaphoric_reference(text: str) -> bool:
    tokens = {t.lower().strip("?,.!:;'\"") for t in text.split()}
    return bool(tokens & _FOLLOW_UP_MARKERS)


def _is_follow_up_query(text: str) -> bool:
    tokens = {t.lower().strip("?,.!:;'\"") for t in text.split()}
    has_pronoun = bool(tokens & _FOLLOW_UP_MARKERS)
    has_intent = bool(tokens & _FOLLOW_UP_INTENTS)
    if has_pronoun:
        return True
    if has_intent and len(tokens) <= 8:
        return True
    return False


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


def _finalize_answer(answer: Answer, *, request: AskRequest, safe_question: str, target_lang: str) -> Answer:
    translated = apply_language_policy(answer, target_lang, query_text=safe_question)
    conversation_memory.remember(
        request.conversation_id,
        user_text=safe_question,
        answer=translated,
    )
    return translated


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

    search_question, target_lang = extract_language_and_clean_query(masked_question.text, parsed_request.language)
    search_document, _ = extract_language_and_clean_query(masked_document.text, parsed_request.language)
    routing_request = parsed_request.model_copy(
        update={
            "question": search_question or None,
            "document_text": search_document or None,
        }
    )
    search_text = _request_text(routing_request) or safe_text

    route_result = route(routing_request)
    memory_turns = conversation_memory.recent(parsed_request.conversation_id)
    context_entry_id = parsed_request.previous_entry_id or conversation_memory.latest_entry_id(
        parsed_request.conversation_id
    )

    entry = None
    if route_result.matched_entry_id:
        entry = find_entry_by_id(route_result.matched_entry_id)
    if not entry:
        entry, _ = find_entry_with_score(search_text)

    # Multi-turn conversational context resolution:
    # If no standalone entry matched (or entry matched incidentally while the user explicitly
    # used an anaphoric pronoun like 'for that' / 'for this' pointing to the previous topic),
    # resolve against previous_entry_id or context_topic.
    if context_entry_id and _is_follow_up_query(search_text):
        if entry is None or _has_anaphoric_reference(search_text):
            candidate = find_entry_by_id(context_entry_id)
            if candidate:
                entry = candidate

    if entry is None and parsed_request.context_topic and _is_follow_up_query(search_text):
        candidate, _ = find_entry_with_score(parsed_request.context_topic)
        if candidate:
            entry = candidate

    # Prefer the small, manually verified procedure library whenever it has a
    # match. The broader imported RAG corpus is explicitly unverified and must
    # not replace a trusted workflow with a lower-confidence candidate passage.
    if entry is not None and _verified_entry_covers_request(entry.get("id", ""), search_text):
        answer = explain_entry(entry, user_question=safe_text, masked_items=masked_items)
        if parsed_request.input_type == "document" and parsed_request.document_text:
            existing_titles = {warning.title for warning in answer.warnings}
            extra_warnings = [warning for warning in find_flags(masked_document.text) if warning.title not in existing_titles]
            answer = answer.model_copy(update={"warnings": [*answer.warnings, *extra_warnings]})
        return _finalize_answer(
            answer,
            request=parsed_request,
            safe_question=masked_question.text or safe_text,
            target_lang=target_lang,
        )

    # Use RAG as a conservative fallback for supported PAN/Aadhaar requests
    # that are not covered by a verified procedure. This preserves citations
    # without allowing unverified chunks to override higher-trust guidance.
    rag_query = search_text
    if parsed_request.context_topic and _is_follow_up_query(search_text):
        rag_query = f"{parsed_request.context_topic} {search_text}"
    rag_result = retrieve_if_enabled(rag_query, top_k=3)
    if rag_result is not None and rag_result.hits:
        rag_answer = explain_rag_result(rag_result, safe_text, masked_items=masked_items)
        if rag_answer is not None:
            rag_answer = enhance_grounded_answer(
                rag_answer,
                question=safe_text,
                memory=memory_turns,
            )
            if parsed_request.input_type == "document" and parsed_request.document_text:
                existing_titles = {warning.title for warning in rag_answer.warnings}
                extra_warnings = [
                    warning for warning in find_flags(masked_document.text)
                    if warning.title not in existing_titles
                ]
                rag_answer = rag_answer.model_copy(update={"warnings": [*rag_answer.warnings, *extra_warnings]})
            return _finalize_answer(
                rag_answer,
                request=parsed_request,
                safe_question=masked_question.text or safe_text,
                target_lang=target_lang,
            )

    if route_result.needs_clarification and not route_result.matched_entry_id:
        return _finalize_answer(
            not_found_answer(safe_text, masked_items=masked_items),
            request=parsed_request,
            safe_question=masked_question.text or safe_text,
            target_lang=target_lang,
        )

    return _finalize_answer(
        not_found_answer(safe_text, masked_items=masked_items),
        request=parsed_request,
        safe_question=masked_question.text or safe_text,
        target_lang=target_lang,
    )


__all__ = ["run"]
