"""
Pydantic schemas and data contracts for GovBank Assistant.
Agreed contract between Person A (Backend/Knowledge) and Person B (Input/Frontend).
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class Step(BaseModel):
    """A single step in a procedure."""
    no: int
    text: str
    tip: Optional[str] = None

class Warning(BaseModel):
    """Risk flag, deadline alert, or cautionary clause."""
    text: str
    reason: str
    source: str

class MaskedItem(BaseModel):
    """Report of a masked sensitive piece of information."""
    item_type: str  # e.g., 'aadhaar', 'pan', 'phone', 'email', 'account_number'
    count: int = 1
    description: Optional[str] = None

class SourceInfo(BaseModel):
    """Metadata for verified official sources."""
    name: str
    url: str
    category: str
    description: Optional[str] = None
    last_verified: Optional[str] = None

class KnowledgeEntry(BaseModel):
    """Structure of an entry in knowledge_base.json (Section 9)."""
    id: str
    title: str
    category: str  # 'tax', 'banking', 'identity', 'schemes', 'legal', 'property_business'
    type: Literal["procedure", "red_flag", "disclaimer"] = "procedure"
    state: str = "all-India"
    keywords: List[str] = Field(default_factory=list)
    who_can_apply: Optional[str] = None
    documents: List[str] = Field(default_factory=list)
    fee: Optional[str] = None
    steps: List[Step] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)
    source_url: str
    last_verified: str  # YYYY-MM-DD
    status: Literal["unverified", "verified"] = "unverified"

class AskRequest(BaseModel):
    """Request payload sent to POST /api/ask (Section 12)."""
    input_type: Literal["question", "document"] = "question"
    question: str
    language: Literal["en", "hi", "gu"] = "en"
    conversation_id: Optional[str] = None
    file_attached: bool = False

class Answer(BaseModel):
    """Standardized response format returned by every path (Section 12)."""
    title: str
    summary: str
    documents_needed: List[str] = Field(default_factory=list)
    steps: List[Step] = Field(default_factory=list)
    warnings: List[Warning] = Field(default_factory=list)
    source_url: str
    last_verified: str  # YYYY-MM-DD
    confidence: Literal["low", "medium", "high"] = "high"
    masked_items: List[MaskedItem] = Field(default_factory=list)
    disclaimer: str

__all__ = [
    "Step",
    "Warning",
    "MaskedItem",
    "SourceInfo",
    "KnowledgeEntry",
    "AskRequest",
    "Answer"
]