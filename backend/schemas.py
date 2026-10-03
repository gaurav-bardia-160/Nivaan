"""
Pydantic schemas and data contracts for GovBank Assistant.
Agreed contract between Person A (Backend/Knowledge) and Person B (Input/Frontend).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    detail: Optional[str] = None


class Warning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    message: str
    severity: Literal["info", "warning", "critical"] = "warning"


class MaskedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_type: str
    replacement: str = "[masked]"


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    last_verified: str


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_type: Literal["question", "document"] = "question"
    question: Optional[str] = None
    language: Literal["en", "hi", "gu"] = "en"
    conversation_id: Optional[str] = None
    file_attached: bool = False

    @model_validator(mode="after")
    def check_question(self):
        if self.input_type == "question" and not self.question:
            raise ValueError("question required when input_type='question'")
        return self


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    category: Literal["tax", "banking", "scheme", "legal", "general"]
    summary: str
    documents_needed: List[str] = Field(default_factory=list)
    steps: List[Step] = Field(default_factory=list)
    warnings: List[Warning] = Field(default_factory=list)
    source: SourceInfo
    status: Literal["verified", "unverified"] = "verified"


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    documents_needed: List[str] = Field(default_factory=list)
    steps: List[Step] = Field(default_factory=list)
    warnings: List[Warning] = Field(default_factory=list)
    source_url: str
    last_verified: str
    confidence: Literal["low", "medium", "high"] = "medium"
    masked_items: List[MaskedItem] = Field(default_factory=list)
    disclaimer: str = (
        "This is a plain-language explanation and guidance helper, not legal, tax, or financial advice."
    )


__all__ = [
    "AskRequest",
    "Answer",
    "Step",
    "Warning",
    "MaskedItem",
    "KnowledgeEntry",
    "SourceInfo",
]
