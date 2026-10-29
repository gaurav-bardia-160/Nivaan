from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from backend.config import MAX_CONVERSATION_ID_LENGTH, MAX_DOCUMENT_TEXT_LENGTH, MAX_QUESTION_LENGTH


def _clean_text(value: str) -> str:
    return " ".join(value.strip().split())


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    detail: Optional[str] = Field(default=None, max_length=700)

    @field_validator("title", "detail", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        cleaned = _clean_text(value)
        return cleaned or None


class Warning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=900)
    severity: Literal["info", "warning", "critical"] = "warning"

    @field_validator("title", "message", mode="before")
    @classmethod
    def clean_text(cls, value):
        return _clean_text(value) if isinstance(value, str) else value


class MaskedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_type: str = Field(min_length=1, max_length=40)
    replacement: str = Field(default="[masked]", min_length=3, max_length=80)

    @field_validator("item_type", "replacement", mode="before")
    @classmethod
    def clean_text(cls, value):
        return _clean_text(value) if isinstance(value, str) else value


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    url: HttpUrl
    last_verified: date

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return _clean_text(value) if isinstance(value, str) else value


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_type: Literal["question", "document"] = "question"
    question: Optional[str] = Field(default=None, max_length=MAX_QUESTION_LENGTH)
    document_text: Optional[str] = Field(default=None, max_length=MAX_DOCUMENT_TEXT_LENGTH)
    language: Literal["en", "hi", "gu"] = "en"
    conversation_id: Optional[str] = Field(default=None, max_length=MAX_CONVERSATION_ID_LENGTH)
    previous_entry_id: Optional[str] = Field(default=None, max_length=80)
    context_topic: Optional[str] = Field(default=None, max_length=120)
    file_attached: bool = False
    history: Optional[List[dict]] = Field(default=None)

    @field_validator("question", "document_text", "conversation_id", "previous_entry_id", "context_topic", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        cleaned = _clean_text(value)
        return cleaned or None

    @model_validator(mode="after")
    def validate_input_requirements(self):
        if self.input_type == "question" and not self.question:
            raise ValueError("question required when input_type='question'")
        if self.input_type == "document" and self.file_attached and not self.document_text:
            raise ValueError("Please use the /api/ask-file endpoint for file uploads, not /api/ask.")
        if self.input_type == "document" and not (self.question or self.document_text):
            raise ValueError("document input requires a question or document_text")
        return self


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9_\-]+$")
    title: str = Field(min_length=1, max_length=180)
    category: Literal["tax", "banking", "scheme", "legal", "general"]
    summary: str = Field(min_length=1, max_length=1200)
    keywords: List[str] = Field(default_factory=list, min_length=1, max_length=40)
    documents_needed: List[str] = Field(default_factory=list, max_length=30)
    steps: List[Step] = Field(default_factory=list, min_length=1, max_length=20)
    warnings: List[Warning] = Field(default_factory=list, max_length=20)
    source: SourceInfo
    status: Literal["verified", "unverified"] = "unverified"

    @field_validator("title", "summary", mode="before")
    @classmethod
    def clean_required_text(cls, value):
        return _clean_text(value) if isinstance(value, str) else value

    @field_validator("keywords", "documents_needed", mode="before")
    @classmethod
    def clean_string_list(cls, value):
        if not isinstance(value, list):
            return value
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                cleaned.append(item)
                continue
            text = _clean_text(item)
            key = text.lower()
            if text and key not in seen:
                cleaned.append(text)
                seen.add(key)
        return cleaned


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    excerpt: str = Field(min_length=1, max_length=700)
    reported_last_verified: date
    factual_verification: Literal["unverified", "verified"] = "unverified"

    @field_validator("title", "excerpt", mode="before")
    @classmethod
    def clean_text(cls, value):
        return _clean_text(value) if isinstance(value, str) else value


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: Optional[str] = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=1200)
    documents_needed: List[str] = Field(default_factory=list, max_length=30)
    steps: List[Step] = Field(default_factory=list, max_length=20)
    warnings: List[Warning] = Field(default_factory=list, max_length=20)
    source_url: Optional[HttpUrl] = None
    last_verified: date
    confidence: Literal["low", "medium", "high"] = "medium"
    masked_items: List[MaskedItem] = Field(default_factory=list, max_length=30)
    citations: List[Citation] = Field(default_factory=list, max_length=10)
    disclaimer: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @field_validator("entry_id", mode="before")
    @classmethod
    def clean_entry_id(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        cleaned = _clean_text(value)
        return cleaned or None

    @field_validator("title", "summary", mode="before")
    @classmethod
    def clean_required_text(cls, value):
        return _clean_text(value) if isinstance(value, str) else value

    @field_validator("disclaimer", mode="before")
    @classmethod
    def clean_disclaimer(cls, value):
        if value is None:
            return None
        cleaned = _clean_text(value) if isinstance(value, str) else value
        return cleaned or None

    @field_validator("documents_needed", mode="before")
    @classmethod
    def clean_documents(cls, value):
        if not isinstance(value, list):
            return value
        return [_clean_text(item) if isinstance(item, str) else item for item in value if not isinstance(item, str) or _clean_text(item)]


__all__ = [
    "AskRequest",
    "Answer",
    "Step",
    "Warning",
    "MaskedItem",
    "KnowledgeEntry",
    "SourceInfo",
    "Citation",
]
