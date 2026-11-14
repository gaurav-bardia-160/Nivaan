"""Explicit-manifest, network-free ingestion. Does not mutate source files."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from backend.rag.models import (
    ChunkRecord,
    CorpusManifest,
    FactCheckRecord,
    FactCheckRegistry,
    IngestionReport,
    LoadIssue,
    LoadResult,
    canonical_record_sha256,
)
from backend.rag.normalizer import RecordRejected, normalize_record

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
DEFAULT_MANIFEST = DATA_ROOT / "rag_manifest.json"
DEFAULT_FACT_CHECKS = DATA_ROOT / "fact_checks.json"


@dataclass(frozen=True)
class LoadLimits:
    manifest_bytes: int = 64 * 1024
    file_bytes: int = 32 * 1024 * 1024
    corpus_bytes: int = 128 * 1024 * 1024
    line_bytes: int = 256 * 1024
    records: int = 50000
    issues: int = 100

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in asdict(self).values()):
            raise ValueError("limits must be positive integers")


class CorpusLoadError(ValueError):
    """Fatal configuration/read failure. Message is a safe code, not input text."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("nonfinite_json_number")


def _json(data):
    return json.loads(data, object_pairs_hook=_object, parse_constant=_constant)


def _read(path: Path, limit: int) -> bytes:
    try:
        if not path.is_file():
            raise CorpusLoadError("source_not_regular_file")
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        raise CorpusLoadError("source_unreadable") from None
    if len(data) > limit:
        raise CorpusLoadError("file_size_limit")
    return data


def _within_root(root: Path, path: str) -> Path:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in path:
        raise CorpusLoadError("unsafe_dataset_path")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise CorpusLoadError("unsafe_dataset_path") from None
    if resolved.suffix != ".jsonl":
        raise CorpusLoadError("dataset_must_be_jsonl")
    return resolved


def load_corpus(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    data_root: Path = DATA_ROOT,
    fact_checks_path: Path | None = None,
    as_of: date | None = None,
    limits: LoadLimits = LoadLimits(),
) -> LoadResult:
    """Return deduplicated candidates and diagnostics, never truth certification.

    Fatal file/manifest failures raise CorpusLoadError. Invalid records are counted
    and skipped. Conflicting reuse of an ID makes complete=False and exposes no
    documents, so a caller cannot publish a partially ambiguous corpus.
    """
    root = Path(data_root).resolve()
    raw_manifest = _read(Path(manifest_path), limits.manifest_bytes)
    try:
        manifest = CorpusManifest.model_validate(_json(raw_manifest.decode("utf-8-sig")))
    except (ValueError, RecursionError):
        raise CorpusLoadError("invalid_manifest") from None
    ids = [spec.id for spec in manifest.datasets]
    paths = [_within_root(root, spec.path) for spec in manifest.datasets]
    if len(set(ids)) != len(ids) or len(set(paths)) != len(paths):
        raise CorpusLoadError("duplicate_manifest_dataset")
    report = IngestionReport(manifest_sha256=hashlib.sha256(raw_manifest).hexdigest())
    documents = {}
    seen_ids = {}
    total_bytes = 0
    as_of = as_of or date.today()
    checks_path = Path(fact_checks_path) if fact_checks_path is not None else root / "fact_checks.json"
    fact_checks: dict[tuple[str, str], FactCheckRecord] = {}
    seen_fact_check_identities: set[tuple[str, str]] = set()
    if checks_path.exists():
        raw_checks = _read(checks_path, limits.file_bytes)
        try:
            registry = FactCheckRegistry.model_validate(_json(raw_checks.decode("utf-8-sig")))
        except (ValueError, RecursionError):
            raise CorpusLoadError("invalid_fact_check_registry") from None
        for review in registry.reviews:
            identity = (review.dataset_id, review.record_id)
            if identity in fact_checks:
                raise CorpusLoadError("duplicate_fact_check")
            if review.reviewed_at > review.expires_at:
                raise CorpusLoadError("invalid_fact_check_dates")
            fact_checks[identity] = review

    def reject(dataset_id, line, code):
        report.rejected_records += 1
        report.rejection_counts[code] = report.rejection_counts.get(code, 0) + 1
        if len(report.issues) < limits.issues:
            report.issues.append(LoadIssue(dataset_id, line, code))
        else:
            report.issues_truncated = True

    for spec, path in sorted(zip(manifest.datasets, paths), key=lambda item: item[0].id):
        raw = _read(path, min(limits.file_bytes, limits.corpus_bytes - total_bytes))
        total_bytes += len(raw)
        report.source_files_sha256[spec.id] = hashlib.sha256(raw).hexdigest()
        if not raw.strip():
            raise CorpusLoadError("empty_dataset")
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            report.records_seen += 1
            if report.records_seen > limits.records:
                raise CorpusLoadError("record_count_limit")
            if len(line) > limits.line_bytes:
                reject(spec.id, line_number, "line_size_limit")
                continue
            try:
                value = _json(line.decode("utf-8-sig" if line_number == 1 else "utf-8"))
            except (ValueError, RecursionError):
                reject(spec.id, line_number, "invalid_json")
                continue
            try:
                record = ChunkRecord.model_validate(value)
            except ValidationError:
                reject(spec.id, line_number, "invalid_record_schema")
                continue
            try:
                # Identity includes metadata; changed provenance with the same ID is a conflict.
                signature = canonical_record_sha256(record)
                review = fact_checks.get((spec.id, record.id))
                if review is not None:
                    seen_fact_check_identities.add((spec.id, record.id))
                if review is not None and (
                    review.record_sha256 != signature
                    or review.reviewed_at > as_of
                    or review.expires_at < as_of
                ):
                    review = None
                document = normalize_record(record, spec, as_of, fact_check=review)
            except RecordRejected as exc:
                reject(spec.id, line_number, str(exc))
                continue
            except (UnicodeError, ValueError):
                reject(spec.id, line_number, "invalid_unicode")
                continue
            identity = (spec.id, record.id)
            if identity in seen_ids and seen_ids[identity] != signature:
                report.complete = False
                reject(spec.id, line_number, "conflicting_record_id")
                continue
            seen_ids[identity] = signature
            report.accepted_records += 1
            previous = documents.get(document.id)
            if previous is None:
                documents[document.id] = document
            else:
                report.duplicate_records += 1
                documents[document.id] = replace(
                    previous,
                    # Stable representative regardless of input order, preserving line structure.
                    text=min(previous.text, document.text),
                    tags=tuple(sorted(set(previous.tags + document.tags))),
                    sources=tuple(sorted(set(previous.sources + document.sources),
                                         key=lambda s: (s.dataset_id, s.record_id, s.source_url))),
                    language=previous.language if previous.language == document.language else "mixed",
                    warnings=tuple(sorted(set(previous.warnings + document.warnings))),
                )
    if set(fact_checks) - seen_fact_check_identities:
        raise CorpusLoadError("orphan_fact_check")
    if not report.accepted_records:
        report.complete = False
    final = tuple(documents[key] for key in sorted(documents)) if report.complete else ()
    report.unique_documents = len(final)
    report.retained_source_references = sum(len(doc.sources) for doc in final)
    report.category_counts = dict(sorted(Counter(doc.category for doc in final).items()))
    report.warning_counts = dict(sorted(Counter(w for doc in final for w in doc.warnings).items()))
    verified_sources = sum(
        1 for document in final for source in document.sources
        if source.factual_verification == "verified"
    )
    report.factual_verification = "verified" if verified_sources and verified_sources == report.retained_source_references else (
        "mixed" if verified_sources else "unverified"
    )
    report.corpus_sha256 = hashlib.sha256(
        json.dumps([asdict(doc) for doc in final], sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()
    return LoadResult(documents=final, report=report)
