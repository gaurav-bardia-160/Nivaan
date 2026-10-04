from __future__ import annotations

from backend.schemas import Answer, Warning

_TRANSLATION_LIMITATION = Warning(
    title="Answer translation not implemented yet",
    message=(
        "The backend currently returns answers in English only. The selected language is recorded, "
        "but Hindi/Gujarati answer translation will be added in a later verified build."
    ),
    severity="info",
)


def apply_language_policy(answer: Answer, requested_language: str | None) -> Answer:
    """Return an honest answer for the requested language.

    The frontend can translate UI labels, but backend answer translation is not ready.
    Rather than fake translation, the backend keeps the sourced English answer and adds
    a visible warning for non-English requests.
    """

    language = (requested_language or "en").strip().lower()
    if language == "en":
        return answer

    existing_titles = {warning.title for warning in answer.warnings}
    if _TRANSLATION_LIMITATION.title in existing_titles:
        return answer

    return answer.model_copy(update={"warnings": [*answer.warnings, _TRANSLATION_LIMITATION]})


__all__ = ["apply_language_policy"]
