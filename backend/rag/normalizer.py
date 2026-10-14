"""Conservative normalization: retain evidence, do not rewrite facts or fix URLs."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit

from backend.rag.models import ChunkRecord, DatasetSpec, RagDocument, SourceReference


class RecordRejected(ValueError):
    """Safe reason code only, never include raw input in exception messages."""


def normalize_record(record: ChunkRecord, spec: DatasetSpec, as_of: date) -> RagDocument:
    if record.category != spec.category:
        raise RecordRejected("category_mismatch")
    if record.last_verified > as_of:
        raise RecordRejected("future_reported_date")
    url = record.source_url
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or "\\" in url or any(ch.isspace() or ord(ch) < 32 for ch in url)):
            raise RecordRejected("unsafe_source_url")
        if parsed.hostname not in spec.allowed_hosts:
            raise RecordRejected("source_host_not_allowed")
    except ValueError as exc:
        if isinstance(exc, RecordRejected):
            raise
        raise RecordRejected("unsafe_source_url") from None

    text = unicodedata.normalize("NFC", record.text).replace("\r\n", "\n").strip()
    if not any(ch.isalnum() for ch in text):
        raise RecordRejected("empty_evidence")
    if any(unicodedata.category(ch) == "Cc" and ch not in "\n\r\t" for ch in text):
        raise RecordRejected("control_character")
    normalized = " ".join(text.split())
    fingerprint = hashlib.sha256((record.category + "\0" + normalized).encode("utf-8")).hexdigest()
    warnings = {"factual_verification_unavailable", "reported_quality_not_calibrated"}
    words = len(text.split())
    if words < 40:
        warnings.add("short_passage_review")
    if words > 500:
        warnings.add("long_passage_review")
    # Warnings are diagnostics, not proof that a passage is unusable.
    if re.search(r"\[Home\]|^\s*\d+\.\s*/|In this section|!\[", text, re.I | re.M):
        warnings.add("navigation_or_image_markdown")
    if re.search(r"captcha|javascript|browser|404|not found", text, re.I):
        warnings.add("possible_ui_or_error_text")
    if len(record.title) > 300 or len(record.section) > 500:
        warnings.add("long_metadata_review")
    if record.language == "und":
        warnings.add("language_unknown")
    source = SourceReference(
        dataset_id=spec.id, record_id=record.id, source_url=url,
        title=record.title, section=record.section,
        reported_status=record.status,
        reported_last_verified=record.last_verified.isoformat(),
        reported_quality_score=record.quality_score,
        reported_verification_method=record.verification_method,
        reported_source_confidence=record.source_confidence,
    )
    return RagDocument(
        id="rag_" + fingerprint, content_hash=fingerprint, category=record.category,
        text=text, language=record.language, tags=tuple(record.retrieval_tags),
        sources=(source,), warnings=tuple(sorted(warnings)),
    )
