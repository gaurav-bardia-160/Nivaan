from __future__ import annotations

import json
from datetime import date

from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.explainer import explain_rag_result
from backend.rag.loader import load_corpus
from backend.rag.models import ChunkRecord, RetrievalHit, RetrievalResult, canonical_record_sha256


def _record() -> dict[str, object]:
    return {
        "id": "reviewed_1",
        "source_url": "https://example.gov.in/service",
        "title": "Reviewed official procedure",
        "section": "Procedure",
        "text": "Applicants must open the official portal, review eligibility, prepare the required documents, submit the form, save the acknowledgement, track status, and contact the official grievance officer if processing is delayed.",
        "category": "civic",
        "last_verified": "2026-11-01",
        "status": "verified",
        "quality_score": 0.95,
        "source_confidence": "official",
        "verification_method": "human_fact_check",
        "retrieval_tags": ["reviewed", "procedure"],
        "language": "en",
    }


def _workspace(tmp_path, *, record_hash: str, expires_at: str = "2027-01-01"):
    record = _record()
    (tmp_path / "safe.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "datasets": [{
            "id": "reviewed",
            "path": "safe.jsonl",
            "category": "civic",
            "allowed_hosts": ["example.gov.in"],
        }],
    }), encoding="utf-8")
    checks = tmp_path / "fact_checks.json"
    checks.write_text(json.dumps({
        "schema_version": 1,
        "reviews": [{
            "dataset_id": "reviewed",
            "record_id": "reviewed_1",
            "record_sha256": record_hash,
            "reviewed_at": "2026-11-10",
            "expires_at": expires_at,
            "reviewer": "Civic content review team",
            "evidence_url": "https://example.gov.in/service",
        }],
    }), encoding="utf-8")
    return manifest, checks


def _record_hash() -> str:
    return canonical_record_sha256(ChunkRecord.model_validate(_record()))


def test_active_exact_fact_check_promotes_only_the_bound_record(tmp_path):
    manifest, checks = _workspace(tmp_path, record_hash=_record_hash())

    result = load_corpus(
        manifest,
        data_root=tmp_path,
        fact_checks_path=checks,
        as_of=date(2026, 11, 13),
    )

    source = result.documents[0].sources[0]
    assert source.factual_verification == "verified"
    assert source.fact_checked_at == "2026-11-10"
    assert "factual_verification_unavailable" not in result.documents[0].warnings
    assert result.report.factual_verification == "verified"


def test_changed_or_expired_record_cannot_reuse_a_fact_check(tmp_path):
    manifest, checks = _workspace(tmp_path, record_hash="0" * 64, expires_at="2026-11-12")

    result = load_corpus(
        manifest,
        data_root=tmp_path,
        fact_checks_path=checks,
        as_of=date(2026, 11, 13),
    )

    source = result.documents[0].sources[0]
    assert source.factual_verification == "unverified"
    assert source.fact_checked_at is None
    assert result.report.factual_verification == "unverified"


def test_explainer_exposes_verified_state_without_unverified_warning(tmp_path):
    manifest, checks = _workspace(tmp_path, record_hash=_record_hash())
    loaded = load_corpus(
        manifest,
        data_root=tmp_path,
        fact_checks_path=checks,
        as_of=date(2026, 11, 13),
    )
    retrieval = RetrievalResult(
        query="How do I use the reviewed official procedure?",
        hits=(RetrievalHit(document=loaded.documents[0], score=0.95, rank=1, signals={}),),
        status="supported",
        searched_documents=1,
    )

    answer = explain_rag_result(retrieval, retrieval.query)

    assert answer is not None
    assert answer.title.startswith("Verified official material:")
    assert answer.citations[0].factual_verification == "verified"
    assert not any(w.title == "Candidate evidence, not verified advice" for w in answer.warnings)


def test_public_api_preserves_verified_fact_check_state(monkeypatch, tmp_path):
    manifest, checks = _workspace(tmp_path, record_hash=_record_hash())
    loaded = load_corpus(
        manifest,
        data_root=tmp_path,
        fact_checks_path=checks,
        as_of=date(2026, 11, 13),
    )
    retrieval = RetrievalResult(
        query="How do I use this banking procedure?",
        hits=(RetrievalHit(document=loaded.documents[0], score=0.95, rank=1, signals={}),),
        status="supported",
        searched_documents=1,
    )
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setattr("backend.pipeline.retrieve_if_enabled", lambda *_args, **_kwargs: retrieval)

    response = TestClient(app).post(
        "/api/ask",
        json={"question": "How do I use this reviewed banking procedure?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"].startswith("Verified official material:")
    assert payload["citations"][0]["factual_verification"] == "verified"
