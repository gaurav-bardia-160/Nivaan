"""Regional translation layer for GovBank Assistant.

Provides script detection for Indic languages (Devanagari/Hindi, Gujarati)
and post-translation of grounded English answers into the user's required language
while preserving URLs, form codes, dates, and PII masks.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from backend.schemas import Answer, Step, Warning

logger = logging.getLogger("translator")

# In-memory translation cache to avoid duplicate API calls
_TRANSLATION_CACHE: dict[tuple[str, str], str] = {}

# Non-translatable tokens that should be preserved exactly
_PROTECTED_PATTERN = re.compile(
    r"(\[PAN\]|\[AADHAAR\]|\[PHONE\]|\[EMAIL\]|\[BANK_ACCOUNT\]|\[IFSC\]|https?://[^\s]+|Form\s+\d+[A-Z]*|\bRs\.?\s*\d+)",
    re.IGNORECASE,
)


def is_translation_enabled() -> bool:
    """Check if the translation layer feature flag is active."""
    return os.getenv("TRANSLATION_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def detect_language(text: str | None, requested_lang: str | None = None) -> str:
    """Detect whether a query or requested language is Hindi, Gujarati, or English.

    Recognizes explicit language codes as well as native Devanagari and Gujarati scripts.
    """
    req = (requested_lang or "").strip().lower()
    if req in ("hi", "hindi", "hin"):
        return "hi"
    if req in ("gu", "gujarati", "guj"):
        return "gu"

    if text:
        # Check Devanagari Unicode block (\u0900-\u097F)
        if any("\u0900" <= char <= "\u097f" for char in text):
            return "hi"
        # Check Gujarati Unicode block (\u0a80-\u0aff)
        if any("\u0a80" <= char <= "\u0aff" for char in text):
            return "gu"

    return req if req and req != "und" else "en"


def _target_code(lang: str) -> str:
    """Map short code to standard Indic locale for translation providers."""
    if lang == "hi":
        return "hi-IN"
    if lang == "gu":
        return "gu-IN"
    return lang


def translate_text(text: str, target_lang: str) -> str:
    """Translate an English text snippet to the target regional language.

    Safely protects URLs, form codes, and masked PII values from distortion.
    """
    if not text or not text.strip() or target_lang in ("en", "und", ""):
        return text

    clean_text = text.strip()
    cache_key = (clean_text, target_lang)
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]

    # Temporarily replace protected tokens with unique markers
    placeholders: dict[str, str] = {}

    def _replace_protected(match: re.Match) -> str:
        token = match.group(0)
        marker = f"__TOKEN_{len(placeholders)}__"
        placeholders[marker] = token
        return marker

    masked_text = _PROTECTED_PATTERN.sub(_replace_protected, clean_text)

    try:
        from deep_translator import MyMemoryTranslator

        target_locale = _target_code(target_lang)
        translated = MyMemoryTranslator(source="en-US", target=target_locale).translate(masked_text)

        if not translated:
            return text

        # Restore protected tokens flexibly (handling case changes and space insertions)
        for marker, original in placeholders.items():
            num = marker.strip("_").split("_")[-1]
            pattern = re.compile(rf"__\s*token\s*_\s*{num}\s*__", re.IGNORECASE)
            translated = pattern.sub(original, translated)
            translated = translated.replace(marker, original)

        _TRANSLATION_CACHE[cache_key] = translated
        return translated

    except Exception as exc:
        logger.warning("Translation to %s failed for text '%s': %s", target_lang, clean_text[:40], exc)
        return text


def translate_answer(answer: Answer, target_lang: str) -> Answer:
    """Translate all user-facing textual fields of an Answer into the target regional language.

    Preserves source URLs, verification status, confidence score, and citations.
    """
    if target_lang in ("en", "und", ""):
        return answer

    lang_name = "Hindi" if target_lang == "hi" else ("Gujarati" if target_lang == "gu" else target_lang.upper())

    # 1. Translate Title & Summary
    translated_title = translate_text(answer.title, target_lang)
    translated_summary = translate_text(answer.summary, target_lang)

    # 2. Translate Steps
    translated_steps = [
        Step(
            title=translate_text(step.title, target_lang),
            detail=translate_text(step.detail, target_lang),
        )
        for step in answer.steps
    ]

    # 3. Translate Documents Needed
    translated_docs = [translate_text(doc, target_lang) for doc in answer.documents_needed]

    # 4. Translate Warnings
    translated_warnings = [
        Warning(
            title=translate_text(warning.title, target_lang),
            message=translate_text(warning.message, target_lang),
            severity=warning.severity,
        )
        for warning in answer.warnings
    ]

    # Add translation provenance note
    translated_warnings.append(
        Warning(
            title=f"Translated into {lang_name}",
            message=f"This response was translated into {lang_name} from official English guidance.",
            severity="info",
        )
    )

    # 5. Translate Disclaimer
    translated_disclaimer = translate_text(answer.disclaimer, target_lang)

    return answer.model_copy(
        update={
            "title": translated_title,
            "summary": translated_summary,
            "steps": translated_steps,
            "documents_needed": translated_docs,
            "warnings": translated_warnings,
            "disclaimer": translated_disclaimer,
        }
    )


__all__ = [
    "detect_language",
    "is_translation_enabled",
    "translate_answer",
    "translate_text",
]
