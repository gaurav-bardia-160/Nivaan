from __future__ import annotations

from typing import Any

from backend.modules.explainer import explain_entry, not_found_answer
from backend.modules.retrieval import find_entry
from backend.schemas import Answer, AskRequest


def run(request: AskRequest | dict[str, Any]) -> Answer:
    """Run the safe backend question path.

    Current production boundary:
    - Supports typed questions and document metadata requests.
    - Does not process uploaded file bytes yet because OCR/privacy modules are not built.
    - Never guesses outside the local knowledge base.
    """
    parsed_request = request if isinstance(request, AskRequest) else AskRequest(**request)
    query = parsed_request.question or ""

    entry = find_entry(query)
    if entry is None:
        return not_found_answer(query)

    return explain_entry(entry, user_question=query)


__all__ = ["run"]
