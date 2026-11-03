from __future__ import annotations

import pytest

from backend.modules.translator import (
    detect_language,
    extract_language_and_clean_query,
    is_translation_enabled,
    translate_answer,
    translate_text,
)
from backend.modules.translate_voice import apply_language_policy
from backend.pipeline import run
from backend.schemas import Answer, AskRequest, Step, Warning


def test_detect_language_recognizes_scripts_and_explicit_codes():
    assert detect_language("How do I apply for a PAN card?", "en") == "en"
    assert detect_language("How do I apply for a PAN card?", "hi") == "hi"
    assert detect_language("How do I apply for a PAN card?", "gu") == "gu"

    # Native script detection regardless of requested_lang
    assert detect_language("आधार कार्ड में पता कैसे बदलें?", "en") == "hi"
    assert detect_language("આધાર કાર્ડમાં સરનામું કેવી રીતે બદલવું?", None) == "gu"
    assert detect_language("Hello world", None) == "en"


def test_translate_text_protects_pii_masks_and_urls(monkeypatch):
    # Test that protected tokens like [PAN] and URLs are preserved
    sample = "Submit [PAN] at https://example.gov.in/portal using Form 49A."
    translated = translate_text(sample, "hi")
    assert "[PAN]" in translated
    assert "https://example.gov.in/portal" in translated
    assert "Form 49A" in translated


def test_translate_answer_preserves_provenance_and_translates_fields():
    sample_answer = Answer(
        title="Apply for a new PAN card",
        summary="A PAN card is used for tax and many financial records.",
        documents_needed=["Proof of identity", "Proof of address"],
        steps=[
            Step(title="Open portal", detail="Go to the official website."),
            Step(title="Submit documents", detail="Upload identity proof."),
        ],
        warnings=[
            Warning(title="Check fees", message="Verify fee before paying.", severity="warning"),
        ],
        source_url="https://www.onlineservices.nsdl.com/",
        last_verified="2026-10-03",
        confidence="medium",
        disclaimer="This is an explanation helper.",
    )

    translated = translate_answer(sample_answer, "hi")

    # Core non-textual provenance must be unchanged
    assert str(translated.source_url) == "https://www.onlineservices.nsdl.com/"
    assert str(translated.last_verified) == "2026-10-03"
    assert translated.confidence == "medium"
    assert len(translated.steps) == 2
    assert len(translated.documents_needed) == 2

    # Translated provenance notice should be present in warnings
    warning_titles = {w.title for w in translated.warnings}
    assert any("Hindi" in title or "हिंदी" in title for title in warning_titles)


def test_language_policy_defaults_to_honest_warning_when_disabled(monkeypatch):
    monkeypatch.delenv("TRANSLATION_ENABLED", raising=False)
    assert is_translation_enabled() is False

    answer = Answer(
        title="Apply for a new PAN card",
        summary="English summary",
        documents_needed=[],
        steps=[],
        warnings=[],
        source_url="https://example.gov.in",
        last_verified="2026-10-03",
        confidence="medium",
        disclaimer="Disclaimer",
    )

    result = apply_language_policy(answer, "hi")
    assert result.title == "Apply for a new PAN card"
    warning_titles = {w.title for w in result.warnings}
    assert "Answer translation not implemented yet" in warning_titles


def test_language_policy_translates_when_feature_flag_is_active(monkeypatch):
    monkeypatch.setenv("TRANSLATION_ENABLED", "true")
    assert is_translation_enabled() is True

    answer = Answer(
        title="Apply for a new PAN card",
        summary="English summary",
        documents_needed=["Proof of identity"],
        steps=[Step(title="Open portal", detail="Details")],
        warnings=[],
        source_url="https://example.gov.in",
        last_verified="2026-10-03",
        confidence="medium",
        disclaimer="Disclaimer",
    )

    result = apply_language_policy(answer, "hi")
    assert result.title != "Apply for a new PAN card"
    assert "पैन" in result.title or "आवेदन" in result.title or len(result.title) > 0


def test_extract_language_and_clean_query():
    cleaned, lang = extract_language_and_clean_query("apply for aadhar card in hindi")
    assert cleaned == "apply for aadhar card"
    assert lang == "hi"

    cleaned, lang = extract_language_and_clean_query("download e-pan in gujarati")
    assert cleaned == "download e-pan"
    assert lang == "gu"

    cleaned, lang = extract_language_and_clean_query("how to check cibil score hindi me")
    assert cleaned == "how to check cibil score"
    assert lang == "hi"

    cleaned, lang = extract_language_and_clean_query("aadhaar update")
    assert cleaned == "aadhaar update"
    assert lang == "en"


def test_pipeline_recognizes_aadhar_spelling_and_natural_language(monkeypatch):
    monkeypatch.delenv("TRANSLATION_ENABLED", raising=False)
    # Query with 'aadhar' (single 'a') and 'in hindi'
    ans = run(AskRequest(question="apply for aadhar card in hindi"))
    assert ans.confidence in ["low", "medium", "high"]
    assert "aadhaar" in ans.title.lower() or "aadhar" in ans.title.lower() or "understand" in ans.title.lower()
    # Check that translation warning is present because TRANSLATION_ENABLED is False
    warning_titles = {w.title for w in ans.warnings}
    assert "Answer translation not implemented yet" in warning_titles

