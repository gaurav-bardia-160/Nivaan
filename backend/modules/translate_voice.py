from __future__ import annotations

from backend.modules.translator import (
    detect_language,
    is_translation_enabled,
    translate_answer,
)
from backend.schemas import Answer, Warning

_TRANSLATION_LIMITATION = Warning(
    title="Answer translation not implemented yet",
    message=(
        "The backend currently returns answers in English only. The selected language is recorded, "
        "but Hindi/Gujarati answer translation will be added in a later verified build."
    ),
    severity="info",
)


def apply_language_policy(
    answer: Answer,
    requested_language: str | None,
    query_text: str | None = None,
) -> Answer:
    """Return an answer translated to the requested regional language if enabled, or an honest warning.

    If TRANSLATION_ENABLED is active and the user's query or selected language is Hindi or Gujarati,
    the translation layer translates the response into the target language.
    Otherwise, it retains the canonical English answer with an informative limitation warning.
    """
    target_lang = detect_language(query_text, requested_language)
    if target_lang == "en":
        return answer

    if is_translation_enabled():
        return translate_answer(answer, target_lang)

    existing_titles = {warning.title for warning in answer.warnings}
    if _TRANSLATION_LIMITATION.title in existing_titles:
        return answer

    return answer.model_copy(update={"warnings": [*answer.warnings, _TRANSLATION_LIMITATION]})


__all__ = ["apply_language_policy"]
