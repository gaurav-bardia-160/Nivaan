from __future__ import annotations

import re
from dataclasses import dataclass

from backend.schemas import MaskedItem


@dataclass(frozen=True)
class MaskResult:
    text: str
    masked_items: list[MaskedItem]


_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "bank_account",
        "[BANK_ACCOUNT]",
        re.compile(r"\b(?:account\s*(?:no\.?|number)?\s*[:\-]?\s*)\d{9,18}\b", re.IGNORECASE),
    ),
    (
        "aadhaar",
        "[AADHAAR]",
        re.compile(r"(?<!\d)(?:\d{4}[\s-]?\d{4}[\s-]?\d{4})(?!\d)"),
    ),
    (
        "pan",
        "[PAN]",
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE),
    ),
    (
        "ifsc",
        "[IFSC]",
        re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE),
    ),
    (
        "email",
        "[EMAIL]",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
    (
        "phone",
        "[PHONE]",
        re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    ),
)


def mask_text(text: str | None) -> MaskResult:
    """Mask obvious sensitive values in server-side text before retrieval/explanation.

    This is a safeguard, not a guarantee of anonymity. The backend still receives the
    original request text, so UI copy must not claim true on-device privacy until the
    frontend implements client-side masking.
    """
    current = text or ""
    items: list[MaskedItem] = []
    seen: set[str] = set()

    for item_type, replacement, pattern in _PATTERNS:
        current, count = pattern.subn(replacement, current)
        if count and item_type not in seen:
            items.append(MaskedItem(item_type=item_type, replacement=replacement))
            seen.add(item_type)

    return MaskResult(text=current, masked_items=items)


__all__ = ["MaskResult", "mask_text"]
