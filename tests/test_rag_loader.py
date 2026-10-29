from __future__ import annotations

import json
from datetime import date

import pytest

from backend.rag.loader import CorpusLoadError, LoadLimits, load_corpus


def _write_manifest(root, dataset_path="safe.jsonl", *, host="example.gov.in"):
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "datasets": [{
            "id": "demo",
            "path": dataset_path,
            "category": "demo",
            "allowed_hosts": [host],
        }],
    }), encoding="utf-8")
    return manifest


def _record(**overrides):
    data = {
        "id": "demo_1",
        "source_url": "https://example.gov.in/service",
        "title": "Demo Service",
        "section": "Documents",
        "text": "This official passage explains the demo service with enough useful words to pass the short passage warning boundary. It includes documents, steps, fees, and clear civic procedure details for testing ingestion.",
        "category": "demo",
        "last_verified": "2026-10-12",
        "status": "verified",
        "quality_score": 0.95,
        "source_confidence": "official",
        "verification_method": "automated_official_source",
        "retrieval_tags": ["demo", "documents", "demo"],
    }
    data.update(overrides)
    return data


def test_loader_accepts_manifest_jsonl_and_normalizes_truth_status(tmp_path):
    manifest = _write_manifest(tmp_path)
    (tmp_path / "safe.jsonl").write_text(json.dumps(_record()) + "\n", encoding="utf-8")

    result = load_corpus(manifest, data_root=tmp_path, as_of=date(2026, 10, 14))

    assert result.report.complete is True
    assert result.report.records_seen == 1
    assert result.report.accepted_records == 1
    assert result.report.unique_documents == 1
    assert result.report.factual_verification == "unverified"
    doc = result.documents[0]
    assert doc.category == "demo"
    assert doc.sources[0].reported_status == "verified"
    assert doc.sources[0].factual_verification == "unverified"
    assert "reported_quality_not_calibrated" in doc.warnings


def test_loader_deduplicates_text_but_retains_source_references(tmp_path):
    manifest = _write_manifest(tmp_path)
    first = _record(id="demo_1", source_url="https://example.gov.in/a", retrieval_tags=["one"])
    second = _record(id="demo_2", source_url="https://example.gov.in/b", retrieval_tags=["two"])
    (tmp_path / "safe.jsonl").write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8"
    )

    result = load_corpus(manifest, data_root=tmp_path, as_of=date(2026, 10, 14))

    assert result.report.records_seen == 2
    assert result.report.accepted_records == 2
    assert result.report.duplicate_records == 1
    assert result.report.unique_documents == 1
    assert result.report.retained_source_references == 2
    assert {source.record_id for source in result.documents[0].sources} == {"demo_1", "demo_2"}
    assert set(result.documents[0].tags) == {"one", "two"}


def test_loader_rejects_unsafe_source_url_without_fetching(tmp_path):
    manifest = _write_manifest(tmp_path)
    (tmp_path / "safe.jsonl").write_text(
        json.dumps(_record(source_url="https://evil.example/service")) + "\n", encoding="utf-8"
    )

    result = load_corpus(manifest, data_root=tmp_path, as_of=date(2026, 10, 14))

    assert result.report.complete is False
    assert result.report.accepted_records == 0
    assert result.report.rejection_counts == {"source_host_not_allowed": 1}
    assert result.documents == ()


def test_loader_rejects_path_traversal_manifest(tmp_path):
    manifest = _write_manifest(tmp_path, dataset_path="../outside.jsonl")

    with pytest.raises(CorpusLoadError, match="unsafe_dataset_path"):
        load_corpus(manifest, data_root=tmp_path, as_of=date(2026, 10, 14))


def test_loader_detects_conflicting_reused_record_id(tmp_path):
    manifest = _write_manifest(tmp_path)
    first = _record(id="same", text=_record()["text"] + " first")
    second = _record(id="same", text=_record()["text"] + " second")
    (tmp_path / "safe.jsonl").write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8"
    )

    result = load_corpus(manifest, data_root=tmp_path, as_of=date(2026, 10, 14))

    assert result.report.complete is False
    assert result.report.rejection_counts == {"conflicting_record_id": 1}
    assert result.documents == ()


def test_loader_flags_overlong_metadata_without_rejecting(tmp_path):
    manifest = _write_manifest(tmp_path)
    (tmp_path / "safe.jsonl").write_text(
        json.dumps(_record(section="Very long metadata " * 80)) + "\n", encoding="utf-8"
    )

    result = load_corpus(manifest, data_root=tmp_path, as_of=date(2026, 10, 14))

    assert result.report.complete is True
    assert result.report.accepted_records == 1
    assert "long_metadata_review" in result.documents[0].warnings
    assert result.report.warning_counts["long_metadata_review"] == 1


def test_loader_default_repo_corpus_counts_are_explicit():
    result = load_corpus(as_of=date(2026, 10, 26))

    assert result.report.records_seen == 1227
    assert result.report.accepted_records == 1212
    assert result.report.rejected_records == 15
    assert result.report.unique_documents == 1212
    assert result.report.retained_source_references == 1212
    assert result.report.category_counts == {"aadhaar": 390, "civic": 470, "pan": 242, "tax": 110}
    assert result.report.factual_verification == "unverified"
