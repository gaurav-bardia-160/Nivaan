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


_LANG_PHRASE_PATTERNS = [
    (re.compile(r"\b(in\s+hindi|hindi\s+me|hindi\s+mai|हिंदी\s+में)\b", re.IGNORECASE), "hi"),
    (re.compile(r"\b(in\s+gujarati|gujarati\s+ma|ગુજરાતીમાં)\b", re.IGNORECASE), "gu"),
    (re.compile(r"\b(in\s+english|english\s+me)\b", re.IGNORECASE), "en"),
]


def extract_language_and_clean_query(text: str | None, requested_lang: str | None = None) -> tuple[str, str]:
    """Extract natural language requests (like 'in hindi') from text, clean the query, and return (cleaned_text, lang)."""
    if not text:
        return "", detect_language(text, requested_lang)

    cleaned = text
    detected_lang: str | None = None

    for pattern, lang in _LANG_PHRASE_PATTERNS:
        if pattern.search(cleaned):
            detected_lang = lang
            cleaned = pattern.sub("", cleaned).strip()
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            break

    final_lang = detected_lang or detect_language(text, requested_lang)
    return cleaned, final_lang


def detect_language(text: str | None, requested_lang: str | None = None) -> str:
    """Detect whether a query or requested language is Hindi, Gujarati, or English.

    Recognizes explicit language codes, natural phrases ('in hindi'), and native scripts.
    """
    req = (requested_lang or "").strip().lower()
    if req in ("hi", "hindi", "hin"):
        return "hi"
    if req in ("gu", "gujarati", "guj"):
        return "gu"

    if text:
        for pattern, lang in _LANG_PHRASE_PATTERNS:
            if pattern.search(text):
                return lang

        # Check Devanagari Unicode block (\u0900-\u097F)
        if any("\u0900" <= char <= "\u097f" for char in text):
            return "hi"
        # Check Gujarati Unicode block (\u0a80-\u0aff)
        if any("\u0a80" <= char <= "\u0aff" for char in text):
            return "gu"

    return req if req and req != "und" else "en"


# High-precision civic/government terminology glossary to ensure 100% accuracy for official terms
_CIVIC_GLOSSARY: dict[tuple[str, str], str] = {
    # Hindi
    ("proof of date of birth (pob)", "hi"): "जन्मतिथि का प्रमाण (PoB)",
    ("date of birth proof", "hi"): "जन्मतिथि का प्रमाण",
    ("proof of identity (poi)", "hi"): "पहचान का प्रमाण (PoI)",
    ("proof of identity", "hi"): "पहचान का प्रमाण",
    ("proof of address (poa)", "hi"): "पते का प्रमाण (PoA)",
    ("proof of address", "hi"): "पते का प्रमाण",
    ("free of cost", "hi"): "नि:शुल्क (कोई शुल्क नहीं)",
    ("recent photograph if required by the selected application flow", "hi"): "हाल ही की तस्वीर (यदि चयनित आवेदन प्रक्रिया में आवश्यक हो)",
    ("recent photographs", "hi"): "हाल ही की तस्वीरें",
    ("pan card", "hi"): "पैन कार्ड",
    ("aadhaar card", "hi"): "आधार कार्ड",
    ("aadhaar number if applicable", "hi"): "आधार संख्या (यदि लागू हो)",
    ("registered mobile number", "hi"): "पंजीकृत मोबाइल नंबर",
    ("bank account details", "hi"): "बैंक खाता विवरण",
    ("bank account details for refund", "hi"): "रिफंड के लिए बैंक खाता विवरण",
    ("valid kyc document (aadhaar, passport, voter id, etc.)", "hi"): "मान्य केवाईसी दस्तावेज़ (आधार, पासपोर्ट, वोटर आईडी, आदि)",
    ("avoid sharing real id data in the demo", "hi"): "डेमो में वास्तविक पहचान डेटा साझा करने से बचें",
    ("confirm the latest official form and fee", "hi"): "नवीनतम आधिकारिक फॉर्म और शुल्क की पुष्टि करें",

    # Gujarati
    ("proof of date of birth (pob)", "gu"): "જન્મ તારીખનો પુરાવો (PoB)",
    ("date of birth proof", "gu"): "જન્મ તારીખનો પુરાવો",
    ("proof of identity (poi)", "gu"): "ઓળખનો પુરાવો (PoI)",
    ("proof of identity", "gu"): "ઓળખનો પુરાવો",
    ("proof of address (poa)", "gu"): "સરનામાનો પુરાવો (PoA)",
    ("proof of address", "gu"): "સરનામાનો પુરાવો",
    ("free of cost", "gu"): "મફત / નિઃશુલ્ક",
    ("recent photograph if required by the selected application flow", "gu"): "તાજેતરનો ફોટોગ્રાફ (જો અરજી માટે જરૂરી હોય)",
    ("recent photographs", "gu"): "તાજેતરના ફોટોગ્રાફ્સ",
    ("pan card", "gu"): "પાન કાર્ડ",
    ("aadhaar card", "gu"): "આધાર કાર્ડ",
    ("aadhaar number if applicable", "gu"): "આધાર નંબર (જો લાગુ હોય તો)",
    ("registered mobile number", "gu"): "નોંધાયેલ મોબાઈલ નંબર",
    ("bank account details", "gu"): "બેંક ખાતાની વિગતો",
    ("bank account details for refund", "gu"): "રિફંડ માટે બેંક ખાતાની વિગતો",
    ("valid kyc document (aadhaar, passport, voter id, etc.)", "gu"): "માન્ય કેવાયસી દસ્તાવેજ (આધાર, પાસપોર્ટ, મતદાર આઈડી, વગેરે)",
    ("avoid sharing real id data in the demo", "gu"): "ડેમોમાં વાસ્તવિક આઈડી ડેટા શેર કરવાનું ટાળો",
    ("confirm the latest official form and fee", "gu"): "નવીનતમ સત્તાવાર ફોર્મ અને ફીની પુષ્ટિ કરો",

    # Curated Guide Titles & Disclaimers (Hindi)
    ("apply for a new pan card", "hi"): "नए पैन कार्ड के लिए आवेदन करें",
    ("file your income tax return (itr) - basics", "hi"): "अपना आयकर रिटर्न (ITR) दाखिल करें - बुनियादी बातें",
    ("understand a loan agreement", "hi"): "ऋण समझौते (लोन एग्रीमेंट) को समझें",
    ("aadhaar enrolment basics", "hi"): "आधार नामांकन की बुनियादी प्रक्रिया",
    ("link pan with aadhaar", "hi"): "पैन को आधार से लिंक करें",
    ("epf withdrawal process", "hi"): "ईपीएफ (EPF) निकासी प्रक्रिया",
    ("filing a first information report (fir)", "hi"): "प्रथम सूचना रिपोर्ट (FIR) दर्ज करना",
    ("opening a savings bank account", "hi"): "बचत बैंक खाता खोलना",
    ("pm kisan samman nidhi yojana", "hi"): "पीएम किसान सम्मान निधि योजना",
    ("filing a consumer court complaint", "hi"): "उपभोक्ता अदालत में शिकायत दर्ज करना",
    ("no verified guide found", "hi"): "कोई सत्यापित मार्गदर्शिका नहीं मिली",
    ("this is a plain-language explanation and guidance helper, not legal, tax, or financial advice.", "hi"): "यह सरल भाषा में व्याख्या और मार्गदर्शन सहायता है, कानूनी, कर या वित्तीय सलाह नहीं।",

    # Curated Guide Titles & Disclaimers (Gujarati)
    ("apply for a new pan card", "gu"): "નવા પાન કાર્ડ માટે અરજી કરો",
    ("file your income tax return (itr) - basics", "gu"): "તમારું ઇન્કમ ટેક્સ રિટર્ન (ITR) ફાઇલ કરો - મૂળભૂત બાબતો",
    ("understand a loan agreement", "gu"): "લોન કરારને સમજો",
    ("aadhaar enrolment basics", "gu"): "આધાર નોંધણીની મૂળભૂત બાબતો",
    ("link pan with aadhaar", "gu"): "પાન કાર્ડને આધાર સાથે લિંક કરો",
    ("epf withdrawal process", "gu"): "ઇપીએફ (EPF) ઉપાડવાની પ્રક્રિયા",
    ("filing a first information report (fir)", "gu"): "પ્રથમ માહિતી અહેવાલ (FIR) નોંધાવવી",
    ("opening a savings bank account", "gu"): "બચત બેંક ખાતું ખોલવું",
    ("pm kisan samman nidhi yojana", "gu"): "પીએમ કિસાન સન્માન નિધિ યોજના",
    ("filing a consumer court complaint", "gu"): "ગ્રાહક અદાલતમાં ફરિયાદ નોંધાવવી",
    ("no verified guide found", "gu"): "કોઈ ચકાસાયેલ માર્ગદર્શિકા મળી નથી",
    ("this is a plain-language explanation and guidance helper, not legal, tax, or financial advice.", "gu"): "આ સરળ ભાષામાં સમજૂતી અને માર્ગદર્શન સહાયક છે, કાનૂની, કર અથવા નાણાકીય સલાહ નથી.",
}


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
    glossary_key = (clean_text.lower(), target_lang)
    if glossary_key in _CIVIC_GLOSSARY:
        return _CIVIC_GLOSSARY[glossary_key]

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
    "extract_language_and_clean_query",
    "is_translation_enabled",
    "translate_answer",
    "translate_text",
]
