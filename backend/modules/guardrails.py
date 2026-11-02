from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from backend.schemas import MaskedItem, Warning


@dataclass(frozen=True)
class MaskResult:
    text: str
    masked_items: list[MaskedItem]


@dataclass(frozen=True)
class FlagRule:
    id: str
    title: str
    message: str
    severity: str
    patterns: tuple[re.Pattern[str], ...]


_MASK_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
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

_FLAG_RULES: tuple[FlagRule, ...] = (
    FlagRule(
        id="deadline",
        title="Deadline or response window found",
        message="The document mentions a time limit. Missing a response window can create avoidable risk, so confirm the date and next step with the official source or a qualified professional.",
        severity="critical",
        patterns=(
            re.compile(r"\bwithin\s+\d{1,3}\s+(?:days?|working days?|business days?)\b", re.IGNORECASE),
            re.compile(r"\b(?:on or before|before|by)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE),
            re.compile(r"\bdeadline\b|\bdue date\b|\blast date\b", re.IGNORECASE),
        ),
    ),
    FlagRule(
        id="late_payment_penalty",
        title="Late payment or penalty clause found",
        message="Penalty or late-payment wording can increase the total cost. Ask how the charge is calculated, when it starts, and whether taxes or extra charges apply.",
        severity="warning",
        patterns=(
            re.compile(r"\blate\s+(?:payment|fee|charge)\b", re.IGNORECASE),
            re.compile(r"\bpenal(?:ty)?\s+(?:interest|charge|fee|rate)?\b", re.IGNORECASE),
            re.compile(r"\bdefault\s+(?:interest|charge|fee)\b", re.IGNORECASE),
        ),
    ),
    FlagRule(
        id="prepayment_foreclosure",
        title="Prepayment or foreclosure condition found",
        message="Early repayment terms can affect loan cost. Confirm whether charges apply to this exact loan type, rate type, and borrower category.",
        severity="warning",
        patterns=(
            re.compile(r"\bpre[-\s]?payment\b|\bprepay\b", re.IGNORECASE),
            re.compile(r"\bforeclosure\b|\bpre[-\s]?closure\b", re.IGNORECASE),
            re.compile(r"\bearly\s+repayment\b", re.IGNORECASE),
        ),
    ),
    FlagRule(
        id="auto_renewal",
        title="Auto-renewal or automatic debit wording found",
        message="Automatic renewal or debit clauses can continue obligations unless cancelled correctly. Check the cancellation method and notice period.",
        severity="warning",
        patterns=(
            re.compile(r"\bauto(?:matic)?[-\s]?renewal\b|\brenewed automatically\b", re.IGNORECASE),
            re.compile(r"\bauto(?:matic)?\s+debit\b|\bstanding instruction\b", re.IGNORECASE),
        ),
    ),
    FlagRule(
        id="hidden_or_extra_fees",
        title="Extra fee or charge wording found",
        message="Extra fees can change the real cost. Ask for a full written list of charges before signing or paying.",
        severity="info",
        patterns=(
            re.compile(r"\bprocessing\s+fee\b|\bdocumentation\s+charge\b", re.IGNORECASE),
            re.compile(r"\bhidden\s+charges?\b|\bother\s+charges?\b|\badditional\s+charges?\b", re.IGNORECASE),
            re.compile(r"\binsurance\s+(?:premium|required|bundled)\b", re.IGNORECASE),
        ),
    ),
    FlagRule(
        id="legal_notice",
        title="Legal notice or legal action wording found",
        message="Legal notice wording can be high-stakes. The assistant can explain the text, but a lawyer or appropriate professional should review important responses.",
        severity="critical",
        patterns=(
            re.compile(r"\blegal\s+notice\b|\bcourt\s+notice\b", re.IGNORECASE),
            re.compile(r"\blegal\s+action\b|\bproceedings\b|\bsection\s+138\b", re.IGNORECASE),
        ),
    ),
)


def mask_text(text: str | None, force: bool = False) -> MaskResult:
    """Mask obvious sensitive values before retrieval and explanation.

    When running in local-first AI mode (the default), masking is disabled so
    local models have full fidelity access to PAN, IFSC, notice references, and account numbers.
    Can be explicitly toggled on via ENABLE_PII_MASKING=true if running in remote/hosted mode,
    or forced with force=True.
    """
    from backend.config import ENABLE_PII_MASKING

    current = text or ""
    if not force and not ENABLE_PII_MASKING:
        return MaskResult(text=current, masked_items=[])

    items: list[MaskedItem] = []
    seen: set[str] = set()

    for item_type, replacement, pattern in _MASK_PATTERNS:
        current, count = pattern.subn(replacement, current)
        if count and item_type not in seen:
            items.append(MaskedItem(item_type=item_type, replacement=replacement))
            seen.add(item_type)

    return MaskResult(text=current, masked_items=items)


def find_flags(document_text: str | None) -> list[Warning]:
    """Return neutral risk warnings found in document text.

    This is rule-based and intentionally conservative. It flags terms worth
    checking, but it does not decide whether a clause is valid, illegal, good,
    or bad.
    """

    if not document_text or not document_text.strip():
        return []

    sentences = _sentences(document_text)
    warnings: list[Warning] = []
    seen: set[str] = set()

    for rule in _FLAG_RULES:
        matched_sentence = _first_matching_sentence(sentences, rule)
        if not matched_sentence or rule.id in seen:
            continue
        seen.add(rule.id)
        excerpt = matched_sentence
        if len(excerpt) > 220:
            excerpt = f"{excerpt[:217]}..."
        warnings.append(
            Warning(
                title=rule.title,
                message=f"{rule.message} Matched text: {excerpt}",
                severity=rule.severity,  # type: ignore[arg-type]
            )
        )

    return warnings


def _sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [" ".join(chunk.split()) for chunk in chunks if chunk and chunk.strip()]


def _first_matching_sentence(sentences: Iterable[str], rule: FlagRule) -> str | None:
    for sentence in sentences:
        for pattern in rule.patterns:
            if pattern.search(sentence):
                return sentence
    return None


__all__ = ["FlagRule", "MaskResult", "find_flags", "mask_text"]
