"""Acceptance-level answer quality evaluation through the public FastAPI boundary."""
from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

os.environ.setdefault("RAG_ENABLED", "true")
os.environ.setdefault("LOCAL_LLM_ENABLED", "false")
os.environ.setdefault("WEB_SEARCH_ENABLED", "false")

from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.explainer import is_allowed_official_source
from backend.modules import unresolved_queue

CASES_PATH = Path(__file__).with_name("fixtures") / "answer_quality_cases.json"
unresolved_queue.UNRESOLVED_CSV_PATH = (
    Path(os.environ.get("JCODE_SCRATCH_DIR", tempfile.gettempdir()))
    / f"nivaan-quality-unresolved-{os.getpid()}.csv"
)


def _load_cases() -> list[dict[str, Any]]:
    value = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError("answer quality fixture must contain a nonempty list")
    ids = [str(case.get("id") or "") for case in value]
    if any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("answer quality case ids must be nonempty and unique")
    return value


def _citation_text(payload: dict[str, Any]) -> str:
    return " ".join(
        f"{citation.get('title', '')} {citation.get('excerpt', '')} {citation.get('url', '')}"
        for citation in payload.get("citations") or []
    ).lower()


def _response_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False).lower()


def _grounded_checks(case: dict[str, Any], payload: dict[str, Any], *, as_of: date) -> dict[str, bool]:
    citations = payload.get("citations") or []
    citation_text = _citation_text(payload)
    response_text = _response_text(payload)
    expected = [str(term).lower() for term in case.get("citation_any") or []]
    forbidden = [str(term).lower() for term in case.get("forbidden") or []]
    max_age = int(case.get("max_source_age_days", 400))

    dates_valid = True
    for citation in citations:
        try:
            reported = date.fromisoformat(str(citation["reported_last_verified"]))
            dates_valid = dates_valid and 0 <= (as_of - reported).days <= max_age
        except (KeyError, TypeError, ValueError):
            dates_valid = False

    factual_states = [citation.get("factual_verification") for citation in citations]
    warning_titles = {warning.get("title") for warning in payload.get("warnings") or []}
    truth_label_consistent = bool(factual_states) and all(
        state in {"verified", "unverified"} for state in factual_states
    )
    if truth_label_consistent and any(state == "unverified" for state in factual_states):
        truth_label_consistent = "Candidate evidence, not verified advice" in warning_titles

    return {
        "answered": payload.get("title") != "No verified guide found",
        "has_citations": bool(citations),
        "citation_topic_alignment": bool(expected) and any(term in citation_text for term in expected),
        "forbidden_topic_absent": not any(term in response_text for term in forbidden),
        "official_https_citations": bool(citations) and all(
            is_allowed_official_source(str(citation.get("url") or "")) for citation in citations
        ),
        "citation_freshness": bool(citations) and dates_valid,
        "truth_label_consistency": truth_label_consistent,
    }


def _refusal_checks(payload: dict[str, Any]) -> dict[str, bool]:
    return {
        "safe_refusal": payload.get("title") == "No verified guide found",
        "no_unsupported_citations": not (payload.get("citations") or []),
        "low_confidence": payload.get("confidence") == "low",
    }


def _privacy_checks(case: dict[str, Any], payload: dict[str, Any]) -> dict[str, bool]:
    serialized = json.dumps(payload, ensure_ascii=False)
    return {
        "secret_not_returned": all(secret not in serialized for secret in case.get("secrets") or []),
    }


def run_evaluation() -> dict[str, Any]:
    client = TestClient(app)
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    as_of = date.today()

    for case in _load_cases():
        conversation_id = f"quality-{case['id'].lower()}"
        client.delete(f"/api/conversations/{conversation_id}")
        if case.get("setup_query"):
            setup = client.post(
                "/api/ask",
                json={"question": case["setup_query"], "conversation_id": conversation_id},
            )
            if setup.status_code != 200:
                raise AssertionError(f"{case['id']} setup returned HTTP {setup.status_code}")

        started = time.perf_counter()
        response = client.post(
            "/api/ask",
            json={"question": case["query"], "conversation_id": conversation_id},
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(elapsed_ms)
        payload = response.json() if response.status_code == 200 else {}

        checks: dict[str, bool] = {"http_200": response.status_code == 200}
        if response.status_code == 200 and case["kind"] == "grounded":
            checks.update(_grounded_checks(case, payload, as_of=as_of))
        elif response.status_code == 200 and case["kind"] == "refusal":
            checks.update(_refusal_checks(payload))
        elif response.status_code == 200 and case["kind"] == "privacy":
            checks.update(_privacy_checks(case, payload))
        else:
            checks["recognized_case_kind"] = False

        failures = sorted(name for name, passed in checks.items() if not passed)
        results.append({
            "id": case["id"],
            "kind": case["kind"],
            "query": case["query"],
            "passed": not failures,
            "blocking": bool(case.get("blocking", True)),
            "known_gap": case.get("known_gap"),
            "checks": checks,
            "failures": failures,
            "title": payload.get("title"),
            "latency_ms": round(elapsed_ms, 2),
        })
        client.delete(f"/api/conversations/{conversation_id}")

    passed = sum(result["passed"] for result in results)
    blocking_failures = [
        result["id"] for result in results
        if result["blocking"] and not result["passed"]
    ]
    known_gaps = [
        {"id": result["id"], "reason": result["known_gap"], "failures": result["failures"]}
        for result in results
        if not result["blocking"] and not result["passed"]
    ]
    return {
        "schema_version": 1,
        "cases": len(results),
        "passed": passed,
        "accuracy": passed / len(results),
        "blocking_failures": blocking_failures,
        "known_gaps": known_gaps,
        "average_latency_ms": round(sum(latencies) / len(latencies), 2),
        "results": results,
    }


def test_reviewed_answer_quality_acceptance_gate():
    report = run_evaluation()
    assert not report["blocking_failures"], json.dumps(report["blocking_failures"], indent=2)
    assert report["accuracy"] >= 0.94
    assert all(gap["reason"] for gap in report["known_gaps"])


if __name__ == "__main__":
    print(json.dumps(run_evaluation(), indent=2))
