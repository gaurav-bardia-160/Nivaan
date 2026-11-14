from __future__ import annotations

import re
from datetime import date
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from backend.config import MAX_CONVERSATION_ID_LENGTH, MAX_DOCUMENT_TEXT_LENGTH, MAX_QUESTION_LENGTH


def _clean_text(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_doc_item(item: Any) -> str | None:
    if not item:
        return None
    if isinstance(item, dict):
        title = item.get("title") or item.get("name") or item.get("document") or item.get("doc") or ""
        detail = item.get("detail") or item.get("url") or ""
        title = _clean_text(str(title)) if title else ""
        detail = _clean_text(str(detail)) if detail else ""
        if title and detail and not detail.startswith("http"):
            return f"{title} ({detail})"
        if title:
            return title
        if detail:
            return detail
        return None
    if isinstance(item, str):
        text = _clean_text(item)
        if not text:
            return None
        if (text.startswith("{") and text.endswith("}")) or ("'title'" in text or '"title"' in text):
            try:
                import ast
                val = ast.literal_eval(text)
                if isinstance(val, dict):
                    return _normalize_doc_item(val)
            except Exception:
                try:
                    import json
                    val = json.loads(text.replace("'", '"'))
                    if isinstance(val, dict):
                        return _normalize_doc_item(val)
                except Exception:
                    pass
            m = re.search(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]", text)
            if m:
                return _clean_text(m.group(1))
        return text
    return _clean_text(str(item)) or None


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
            norm = _normalize_doc_item(item)
            if norm:
                key = norm.lower()
                if key not in seen:
                    cleaned.append(norm)
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
    rl_arm: Optional[str] = Field(default=None, max_length=80)

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
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            norm = _normalize_doc_item(item)
            if norm:
                key = norm.lower()
                if key not in seen:
                    cleaned.append(norm)
                    seen.add(key)
        return cleaned


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: Optional[str] = Field(default=None, max_length=MAX_CONVERSATION_ID_LENGTH)
    query: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    answer_title: str = Field(min_length=1, max_length=180)
    feedback_type: Literal["thumbs_up", "thumbs_down", "click_citation", "copy_steps", "corrective_follow_up"]
    rating: Optional[int] = Field(default=None, ge=-1, le=1)
    comment: Optional[str] = Field(default=None, max_length=500)
    reward: Optional[float] = None
    answer_summary: Optional[str] = Field(default=None, max_length=3000)
    url: Optional[str] = Field(default=None, max_length=500)


__all__ = [
    "AskRequest",
    "Answer",
    "Step",
    "Warning",
    "MaskedItem",
    "KnowledgeEntry",
    "SourceInfo",
    "Citation",
    "FeedbackRequest",
]
