"""Post-generation quality check for AI-grounded answers.

Runs automated checks on LLM-rewritten answers before they are shown to users.
Catches invented abbreviations, terms not present in source text, and suspicious
URL patterns in cited sources.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("qa_check")

# URL substrings that indicate non-production / staging sources
_STAGING_INDICATORS = {"beta", "staging", "test", "dev", "sandbox", "preview", "canary"}


def verify_against_source(answer_text: str, source_text: str) -> list[str]:
    """Return a list of warnings for terms in the answer not found in source.

    Checks:
    1. Capitalized abbreviations (2-5 letters) that don't appear in the source.
    2. Quoted terms that don't appear in the source text.
    """
    warnings: list[str] = []
    if not answer_text or not source_text:
        return warnings

    # 1. Extract capitalized abbreviations (2-5 letters) from the answer
    abbreviations = set(re.findall(r'\b[A-Z][a-zA-Z]{1,4}\b', answer_text))
    # Exclude very common ones that aren't domain-specific
    common_abbrs = {
        "The", "You", "Your", "This", "That", "Step", "Note", "From", "With",
        "Also", "Each", "Once", "JSON", "None", "True", "False", "India",
    }
    for abbr in abbreviations - common_abbrs:
        if abbr not in source_text:
            warnings.append(
                f"Abbreviation '{abbr}' used in answer but not found in source text — verify it's real."
            )

    # 2. Check for quoted terms (in single or double quotes)
    quoted_terms = re.findall(r'["\u201c\u201d]([^"\u201c\u201d]{2,30})["\u201c\u201d]', answer_text)
    for term in quoted_terms:
        if term.lower() not in source_text.lower() and not term.startswith("Step"):
            warnings.append(
                f"Quoted term '{term}' not found in source text — may be invented."
            )

    return warnings


def flag_staging_urls(source_url: str) -> list[str]:
    """Return warnings if the source URL looks like a staging/beta environment."""
    warnings: list[str] = []
    if not source_url:
        return warnings

    url_lower = source_url.lower()
    for indicator in _STAGING_INDICATORS:
        if indicator in url_lower:
            warnings.append(
                f"Source URL '{source_url}' contains '{indicator}' — "
                f"this may be a staging/non-production URL. Verify it's the canonical public page."
            )
            break  # One warning per URL is enough

    return warnings


def run_qa_checks(
    answer_text: str,
    source_text: str,
    source_url: str = "",
) -> list[str]:
    """Run all QA checks and return combined warnings list."""
    warnings = []
    warnings.extend(verify_against_source(answer_text, source_text))
    warnings.extend(flag_staging_urls(source_url))

    for w in warnings:
        logger.warning("QA Check: %s", w)

    return warnings


__all__ = [
    "flag_staging_urls",
    "run_qa_checks",
    "verify_against_source",
]
