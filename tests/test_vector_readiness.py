from __future__ import annotations

from pathlib import Path

import pytest

from backend.offline import ensure_vector_db


def test_inspect_vector_index_reports_missing_index(tmp_path, monkeypatch):
    class Report:
        corpus_sha256 = "abc123"

    class LoadResult:
        documents = (object(), object())
        report = Report()

    monkeypatch.setattr(ensure_vector_db, "load_corpus", lambda _, **__: LoadResult())

    result = ensure_vector_db.inspect_vector_index(
        dest_dir=tmp_path / "missing",
        manifest_path=tmp_path / "manifest.json",
    )

    assert result["ready"] is False
    assert result["reason"] == "missing_index"
    assert result["expected_documents"] == 2
    assert result["corpus_sha256"] == "abc123"


def test_inspect_vector_index_rejects_missing_compatibility_metadata(tmp_path, monkeypatch):
    class Report:
        corpus_sha256 = "abc123"

    class LoadResult:
        documents = (object(),)
        report = Report()

    destination = tmp_path / "qdrant"
    destination.mkdir()
    (destination / "storage.sqlite").write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(ensure_vector_db, "load_corpus", lambda _, **__: LoadResult())

    result = ensure_vector_db.inspect_vector_index(
        dest_dir=destination,
        manifest_path=tmp_path / "manifest.json",
    )

    assert result["ready"] is False
    assert result["reason"] == "missing_metadata"


def test_ensure_vector_index_reuses_complete_index(monkeypatch):
    ready = {
        "ready": True,
        "reason": "ready",
        "points": 681,
        "expected_documents": 681,
    }
    monkeypatch.setattr(ensure_vector_db, "inspect_vector_index", lambda **_: ready)

    def unexpected_builder(**_):
        pytest.fail("complete indexes must not be rebuilt")

    result = ensure_vector_db.ensure_vector_index(builder=unexpected_builder)

    assert result["action"] == "reused"
    assert result["points"] == 681


def test_ensure_vector_index_rebuilds_and_rechecks(monkeypatch, tmp_path):
    states = iter(
        (
            {"ready": False, "reason": "missing_index", "points": 0, "expected_documents": 681},
            {"ready": True, "reason": "ready", "points": 681, "expected_documents": 681},
        )
    )
    monkeypatch.setattr(ensure_vector_db, "inspect_vector_index", lambda **_: next(states))
    calls = []

    def builder(**kwargs):
        calls.append(kwargs)
        return {"status": "success"}

    destination = tmp_path / "qdrant"
    data_root = tmp_path / "data"
    result = ensure_vector_db.ensure_vector_index(
        dest_dir=destination,
        data_root=data_root,
        builder=builder,
    )

    assert result["action"] == "rebuilt"
    assert result["points"] == 681
    assert calls[0]["dest_dir"] == destination
    assert calls[0]["data_root"] == data_root


def test_ensure_vector_index_rejects_incomplete_rebuild(monkeypatch):
    incomplete = {
        "ready": False,
        "reason": "document_count_mismatch",
        "points": 632,
        "expected_documents": 681,
    }
    monkeypatch.setattr(ensure_vector_db, "inspect_vector_index", lambda **_: incomplete)

    with pytest.raises(RuntimeError, match="632/681"):
        ensure_vector_db.ensure_vector_index(builder=lambda **_: {"status": "success"})
