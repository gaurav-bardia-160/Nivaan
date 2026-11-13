from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.etl.vectorize import vectorize_all
from backend.rag.loader import load_corpus


def _base_record() -> dict[str, object]:
    return {
        "id": "base_001",
        "source_url": "https://www.rbi.org.in/base",
        "title": "Base official guidance",
        "section": "Base",
        "text": " ".join(f"baseline{i}" for i in range(80)),
        "category": "banking",
        "last_verified": "2026-11-13",
        "status": "unverified",
        "quality_score": 0.8,
        "source_confidence": "official",
        "verification_method": "test_fixture",
        "retrieval_tags": ["base"],
        "language": "en",
    }


def _workspace(tmp_path: Path) -> dict[str, Path]:
    data_root = tmp_path / "data"
    base_path = data_root / "refined" / "base.jsonl"
    base_path.parent.mkdir(parents=True)
    base_path.write_text(json.dumps(_base_record()) + "\n", encoding="utf-8")
    manifest_path = data_root / "rag_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "schema_version": 1,
            "datasets": [{
                "id": "base",
                "path": "refined/base.jsonl",
                "category": "banking",
                "allowed_hosts": ["www.rbi.org.in"],
            }],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    refined_dir = data_root / "etl" / "refined"
    archive_dir = data_root / "etl" / "archive"
    canonical_dir = data_root / "refined" / "etl"
    refined_dir.mkdir(parents=True)
    return {
        "data_root": data_root,
        "manifest": manifest_path,
        "refined": refined_dir,
        "archive": archive_dir,
        "canonical": canonical_dir,
    }


def _refined_payload() -> dict[str, object]:
    procedural = " ".join(
        [
            "Applicants",
            "must",
            "open",
            "the",
            "official",
            "portal",
            "review",
            "eligibility",
            "prepare",
            "documents",
            "submit",
            "the",
            "online",
            "form",
            "save",
            "the",
            "acknowledgement",
            "track",
            "status",
            "and",
            "contact",
            "the",
            "listed",
            "grievance",
            "officer",
            "if",
            "the",
            "request",
            "is",
            "delayed",
        ]
        * 3
    )
    return {
        "url_hash": "example-source",
        "source_url": "https://www.rbi.org.in/example-procedure",
        "domain": "banking",
        "clean_text": procedural,
        "metadata": {
            "scheme_name": "Example Banking Procedure",
            "error_code": None,
            "fetched_at": "2026-11-13T10:00:00+00:00",
        },
    }


def _write_refined(paths: dict[str, Path]) -> Path:
    path = paths["refined"] / "example.json"
    path.write_text(json.dumps(_refined_payload(), indent=2), encoding="utf-8")
    return path


def test_vectorize_all_publishes_to_canonical_manifest_and_runtime_index(tmp_path: Path):
    paths = _workspace(tmp_path)
    refined_path = _write_refined(paths)
    observed: list[tuple[int, int]] = []

    def ensure_index(*, manifest_path: Path, data_root: Path):
        assert data_root == paths["data_root"]
        loaded = load_corpus(manifest_path, data_root=paths["data_root"])
        observed.append((len(loaded.documents), loaded.report.accepted_records))
        return {"ready": True, "documents": len(loaded.documents)}

    count = vectorize_all(
        refined_dir=paths["refined"],
        archive_dir=paths["archive"],
        canonical_refined_dir=paths["canonical"],
        manifest_path=paths["manifest"],
        data_root=paths["data_root"],
        index_ensurer=ensure_index,
    )

    assert count == 1
    assert observed and observed[-1][0] == 2
    loaded = load_corpus(paths["manifest"], data_root=paths["data_root"])
    assert any(
        source.source_url == "https://www.rbi.org.in/example-procedure"
        for document in loaded.documents
        for source in document.sources
    )
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    added = [item for item in manifest["datasets"] if item["id"].startswith("etl_example_source_")]
    assert len(added) == 1
    assert added[0]["path"].startswith("refined/etl/")
    assert not refined_path.exists()
    assert (paths["archive"] / refined_path.name).is_file()


def test_vectorize_all_rolls_back_manifest_and_dataset_when_index_fails(tmp_path: Path):
    paths = _workspace(tmp_path)
    refined_path = _write_refined(paths)
    original_manifest = paths["manifest"].read_bytes()
    calls = 0

    def fail_then_restore(*, manifest_path: Path, data_root: Path):
        nonlocal calls
        assert data_root == paths["data_root"]
        calls += 1
        if calls == 1:
            raise RuntimeError("index build failed")
        loaded = load_corpus(manifest_path, data_root=paths["data_root"])
        return {"ready": True, "documents": len(loaded.documents)}

    with pytest.raises(RuntimeError, match="index build failed"):
        vectorize_all(
            refined_dir=paths["refined"],
            archive_dir=paths["archive"],
            canonical_refined_dir=paths["canonical"],
            manifest_path=paths["manifest"],
            data_root=paths["data_root"],
            index_ensurer=fail_then_restore,
        )

    assert calls == 2
    assert paths["manifest"].read_bytes() == original_manifest
    assert not list(paths["canonical"].glob("*.jsonl"))
    assert refined_path.is_file()
    assert not paths["archive"].exists()


def test_vectorize_all_is_idempotent_for_an_already_published_dataset(tmp_path: Path):
    paths = _workspace(tmp_path)
    refined_path = _write_refined(paths)

    def ensure_index(*, manifest_path: Path, data_root: Path):
        assert data_root == paths["data_root"]
        loaded = load_corpus(manifest_path, data_root=paths["data_root"])
        return {"ready": True, "documents": len(loaded.documents)}

    kwargs = {
        "refined_dir": paths["refined"],
        "archive_dir": paths["archive"],
        "canonical_refined_dir": paths["canonical"],
        "manifest_path": paths["manifest"],
        "data_root": paths["data_root"],
        "index_ensurer": ensure_index,
    }
    assert vectorize_all(**kwargs) == 1
    manifest_after_first = paths["manifest"].read_bytes()
    refined_path.write_bytes((paths["archive"] / refined_path.name).read_bytes())

    assert vectorize_all(**kwargs) == 1
    assert paths["manifest"].read_bytes() == manifest_after_first
    assert not refined_path.exists()


def test_vectorize_all_rejects_unapproved_source_without_publication(tmp_path: Path):
    paths = _workspace(tmp_path)
    payload = _refined_payload()
    payload["source_url"] = "https://example.com/not-official"
    refined_path = paths["refined"] / "bad.json"
    refined_path.write_text(json.dumps(payload), encoding="utf-8")
    original_manifest = paths["manifest"].read_bytes()

    with pytest.raises(RuntimeError, match="unapproved_source_url"):
        vectorize_all(
            refined_dir=paths["refined"],
            archive_dir=paths["archive"],
            canonical_refined_dir=paths["canonical"],
            manifest_path=paths["manifest"],
            data_root=paths["data_root"],
            index_ensurer=lambda **_: {"ready": True},
        )

    assert paths["manifest"].read_bytes() == original_manifest
    assert refined_path.is_file()
    assert not list(paths["canonical"].glob("*.jsonl"))


def test_scheduler_publishes_previously_refined_files(monkeypatch, tmp_path: Path):
    from backend import config
    from backend.etl import extract, refine, scheduler, vectorize

    raw_dir = tmp_path / "raw"
    refined_dir = tmp_path / "refined"
    raw_dir.mkdir()
    refined_dir.mkdir()
    (raw_dir / "waiting.html").write_text("pending raw", encoding="utf-8")
    (refined_dir / "waiting.json").write_text("{}", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(config, "ETL_RAW_DIR", raw_dir)
    monkeypatch.setattr(config, "ETL_REFINED_DIR", refined_dir)
    monkeypatch.setattr(scheduler, "_is_llm_generating", lambda: False)
    monkeypatch.setattr(extract, "extract_all", lambda: 0)
    monkeypatch.setattr(refine, "refine_all", lambda: (0, 0))
    monkeypatch.setattr(vectorize, "vectorize_all", lambda: calls.append("published") or 1)

    scheduler.run_etl_pipeline()

    assert calls == ["published"]
