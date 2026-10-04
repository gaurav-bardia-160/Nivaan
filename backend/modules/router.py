from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.modules.retrieval import find_entry
from backend.schemas import AskRequest

Category = Literal["tax", "banking", "scheme", "legal", "general", "unknown"]
RoutePath = Literal["question", "document"]


@dataclass(frozen=True)
class RouteResult:
    path: RoutePath
    category: Category
    matched_entry_id: str | None = None
    needs_clarification: bool = False
    reason: str = ""


_CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    "tax": ("itr", "income tax", "form 16", "tax return", "assessment year", "pan"),
    "banking": ("bank", "loan", "emi", "interest", "kyc", "account", "rbi", "penalty", "prepayment"),
    "legal": ("legal notice", "agreement", "contract", "court", "lawyer", "clause", "respond within"),
    "scheme": ("scheme", "benefit", "subsidy", "eligibility", "myscheme"),
    "general": ("pan card", "government", "portal", "form"),
}


def _combined_text(request: AskRequest) -> str:
    parts = [request.question or "", request.document_text or ""]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _keyword_category(text: str) -> Category:
    lowered = text.lower()
    scores: dict[Category, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if keyword in lowered)

    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        return "unknown"
    return best_category


def route(request: AskRequest) -> RouteResult:
    """Classify the current request enough for safe orchestration.

    This is intentionally rule-based for now. It is predictable, testable, and avoids
    asking an LLM to decide whether a high-stakes document should be handled.
    """
    text = _combined_text(request)
    category = _keyword_category(text)
    entry = find_entry(text)
    matched_entry_id = entry["id"] if entry else None

    if entry and category == "unknown":
        category = entry.get("category", "unknown")

    if request.input_type == "document" and not request.document_text and request.file_attached:
        return RouteResult(
            path="document",
            category=category,
            matched_entry_id=matched_entry_id,
            needs_clarification=True,
            reason="File upload is marked, but OCR/file processing is not implemented in this backend step yet.",
        )

    if category == "unknown" and matched_entry_id is None:
        return RouteResult(
            path=request.input_type,
            category="unknown",
            matched_entry_id=None,
            needs_clarification=True,
            reason="No supported category or guide matched the request.",
        )

    return RouteResult(
        path=request.input_type,
        category=category,
        matched_entry_id=matched_entry_id,
        needs_clarification=False,
        reason="Matched local routing rules and/or the knowledge base.",
    )


__all__ = ["Category", "RoutePath", "RouteResult", "route"]
