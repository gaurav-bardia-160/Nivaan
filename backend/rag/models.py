"""Provider-independent corpus contracts, distinct from the legacy Answer schema."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class ChunkRecord(BaseModel):
    """Producer metadata is an assertion, not an independently verified fact."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    source_url: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=4096)
    section: str = Field(max_length=20000)
    text: str = Field(min_length=1, max_length=100000)
    category: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_-]*$")
    last_verified: date
    status: Literal["verified", "unverified", "automated_verified"]
    quality_score: float = Field(ge=0, le=1, allow_inf_nan=False, strict=True)
    source_confidence: Literal["official", "unknown"]
    verification_method: str = Field(min_length=1, max_length=100)
    retrieval_tags: list[StrictStr] = Field(max_length=100)
    language: Literal["en", "hi", "gu", "mixed", "und"] = "und"
    source_authority: Optional[str] = Field(default=None, max_length=300)
    publication_date: Optional[date] = None
    effective_from: Optional[date] = None
    jurisdiction: Optional[str] = Field(default=None, max_length=200)
    scheme: Optional[str] = Field(default=None, max_length=300)
    document_type: Optional[str] = Field(default=None, max_length=100)
    supersedes: list[StrictStr] = Field(default_factory=list, max_length=20)

    @field_validator("last_verified", mode="before")
    @classmethod
    def iso_date_only(cls, value):
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("expected ISO date YYYY-MM-DD")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("expected ISO date YYYY-MM-DD")
        return parsed

    @field_validator("retrieval_tags")
    @classmethod
    def clean_tags(cls, values):
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("tags must be nonempty and at most 100 characters")
        return sorted(set(value.strip() for value in values))

    @field_validator("publication_date", "effective_from", mode="before")
    @classmethod
    def optional_iso_date_only(cls, value):
        if value is None:
            return None
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("expected ISO date YYYY-MM-DD")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("expected ISO date YYYY-MM-DD")
        return parsed

    @field_validator("supersedes")
    @classmethod
    def clean_supersedes(cls, values):
        if any(not value.strip() or len(value) > 4096 for value in values):
            raise ValueError("supersedes entries must be nonempty URLs or identifiers")
        return sorted(set(value.strip() for value in values))


def canonical_record_sha256(record: ChunkRecord) -> str:
    """Return the stable digest that an independent review certifies."""
    return hashlib.sha256(record.model_dump_json().encode("utf-8")).hexdigest()


class DatasetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_-]*$")
    path: str = Field(min_length=1, max_length=512)
    category: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_-]*$")
    allowed_hosts: list[StrictStr] = Field(min_length=1, max_length=500)

    @field_validator("allowed_hosts")
    @classmethod
    def exact_hosts(cls, values):
        import re
        if any(not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}", v) for v in values):
            raise ValueError("expected exact lowercase DNS hosts, not URLs or wildcards")
        return sorted(set(values))


class CorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    datasets: list[DatasetSpec] = Field(min_length=1, max_length=100)


class FactCheckRecord(BaseModel):
    """Independent human review bound to one exact canonical record revision."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    dataset_id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_-]*$")
    record_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_at: date
    expires_at: date
    reviewer: str = Field(min_length=1, max_length=200)
    evidence_url: str = Field(min_length=1, max_length=4096)

    @field_validator("reviewed_at", "expires_at", mode="before")
    @classmethod
    def fact_check_iso_date(cls, value):
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("expected ISO date YYYY-MM-DD")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("expected ISO date YYYY-MM-DD")
        return parsed

    @field_validator("evidence_url")
    @classmethod
    def secure_evidence_url(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            raise ValueError("evidence_url must be a public HTTPS URL")
        return value


class FactCheckRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    reviews: list[FactCheckRecord] = Field(default_factory=list, max_length=50000)


@dataclass(frozen=True)
class SourceReference:
    dataset_id: str
    record_id: str
    source_url: str
    title: str
    section: str
    reported_status: str
    reported_last_verified: str
    reported_quality_score: float
    reported_verification_method: str
    reported_source_confidence: str
    source_authority: str | None = None
    publication_date: str | None = None
    effective_from: str | None = None
    jurisdiction: str | None = None
    scheme: str | None = None
    document_type: str | None = None
    supersedes: tuple[str, ...] = ()
    factual_verification: str = "unverified"
    fact_checked_at: str | None = None


@dataclass(frozen=True)
class RagDocument:
    id: str
    content_hash: str
    category: str
    text: str
    language: str
    tags: tuple[str, ...]
    sources: tuple[SourceReference, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class LoadIssue:
    dataset_id: str
    line: int
    code: str


@dataclass
class IngestionReport:
    schema_version: int = 1
    manifest_sha256: str = ""
    corpus_sha256: str = ""
    source_files_sha256: dict[str, str] = field(default_factory=dict)
    records_seen: int = 0
    accepted_records: int = 0
    rejected_records: int = 0
    duplicate_records: int = 0
    unique_documents: int = 0
    retained_source_references: int = 0
    category_counts: dict[str, int] = field(default_factory=dict)
    warning_counts: dict[str, int] = field(default_factory=dict)
    rejection_counts: dict[str, int] = field(default_factory=dict)
    issues: list[LoadIssue] = field(default_factory=list)
    issues_truncated: bool = False
    complete: bool = True
    factual_verification: str = "unverified"
    usage: str = "candidate corpus; only exact active fact-check registry matches are factually verified"


@dataclass(frozen=True)
class LoadResult:
    documents: tuple[RagDocument, ...]
    report: IngestionReport


@dataclass(frozen=True)
class RetrievalHit:
    document: RagDocument
    score: float
    rank: int
    signals: dict[str, float]


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    hits: tuple[RetrievalHit, ...]
    status: str
    searched_documents: int
