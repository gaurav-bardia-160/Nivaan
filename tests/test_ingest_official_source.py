from __future__ import annotations

import hashlib
import json

import pytest

from backend.offline.ingest_official_source import (
    FetchResult,
    IngestionError,
    _simhash,
    build_records,
    extract_text,
    fetch_source,
    ingest_source,
)
from backend.rag.loader import load_corpus


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        url: str = "https://example.gov.in/guide",
        content_type: str = "text/html",
        status_code: int = 200,
        headers: dict | None = None,
    ):
        self._body = body
        self.url = url
        self.headers = headers or {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        yield self._body


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class SequenceSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def _public_resolver(host, port, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def _html() -> bytes:
    words = " ".join(
        f"procedure{i} applicant document eligibility application verification payment grievance official"
        for i in range(1, 80)
    )
    return f"""
    <html><head><title>Official Citizen Procedure</title><style>noise</style></head>
    <body><header>Skip to main content</header><main>
    <h1>Official Citizen Procedure</h1><p>{words}</p>
    </main><footer>Privacy Policy</footer><script>bad()</script></body></html>
    """.encode()


def _manifest(path):
    path.write_text(json.dumps({
        "schema_version": 1,
        "datasets": [{
            "id": "existing",
            "path": "existing.jsonl",
            "category": "civic",
            "allowed_hosts": ["existing.gov.in"],
        }],
    }), encoding="utf-8")
    (path.parent / "existing.jsonl").write_text(json.dumps({
        "id": "existing_1",
        "source_url": "https://existing.gov.in/guide",
        "title": "Existing guide",
        "section": "Procedure",
        "text": "This existing official procedure contains enough distinct words for safe corpus loading and testing without overlapping the new source material in any meaningful way.",
        "category": "civic",
        "last_verified": "2026-10-01",
        "status": "unverified",
        "quality_score": 0.8,
        "source_confidence": "official",
        "verification_method": "manual_test_fixture",
        "retrieval_tags": ["existing"],
        "language": "en",
    }) + "\n", encoding="utf-8")


def test_fetch_source_requires_approved_https_and_keeps_tls_verification_enabled():
    session = FakeSession(FakeResponse(_html()))
    result = fetch_source(
        "https://example.gov.in/guide",
        allowed_hosts=["example.gov.in"],
        session=session,
        resolver=_public_resolver,
    )

    assert result.sha256 == hashlib.sha256(_html()).hexdigest()
    assert session.calls[0][1]["stream"] is True
    assert session.calls[0][1]["verify"] is True

    with pytest.raises(IngestionError, match="safe_https"):
        fetch_source(
            "http://example.gov.in/guide",
            allowed_hosts=["example.gov.in"],
            session=session,
            resolver=_public_resolver,
        )
    with pytest.raises(IngestionError, match="source_host_not_approved"):
        fetch_source(
            "https://evil.example/guide",
            allowed_hosts=["example.gov.in"],
            session=session,
            resolver=_public_resolver,
        )


def test_fetch_source_validates_every_redirect_and_rejects_private_dns():
    redirect = FakeResponse(
        b"",
        url="https://example.gov.in/start",
        status_code=302,
        headers={"Location": "https://other.gov.in/final"},
    )
    session = SequenceSession([redirect])
    with pytest.raises(IngestionError, match="source_host_not_approved"):
        fetch_source(
            "https://example.gov.in/start",
            allowed_hosts=["example.gov.in"],
            session=session,
            resolver=_public_resolver,
        )
    assert session.calls[0][1]["allow_redirects"] is False

    def private_resolver(host, port, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", port))]

    blocked_session = FakeSession(FakeResponse(_html()))
    with pytest.raises(IngestionError, match="non_public_address"):
        fetch_source(
            "https://example.gov.in/guide",
            allowed_hosts=["example.gov.in"],
            session=blocked_session,
            resolver=private_resolver,
        )
    assert blocked_session.calls == []


def test_fetch_source_resolves_and_validates_each_approved_redirect_hop():
    session = SequenceSession([
        FakeResponse(b"", status_code=302, headers={"Location": "/second"}),
        FakeResponse(
            b"",
            status_code=307,
            headers={"Location": "https://files.example.gov.in/final"},
        ),
        FakeResponse(_html(), url="https://files.example.gov.in/final"),
    ])
    resolved_hosts = []

    def resolver(host, port, **kwargs):
        resolved_hosts.append(host)
        return _public_resolver(host, port, **kwargs)

    result = fetch_source(
        "https://example.gov.in/start",
        allowed_hosts=["example.gov.in", "files.example.gov.in"],
        session=session,
        resolver=resolver,
    )

    assert result.final_url == "https://files.example.gov.in/final"
    assert [url for url, _kwargs in session.calls] == [
        "https://example.gov.in/start",
        "https://example.gov.in/second",
        "https://files.example.gov.in/final",
    ]
    assert resolved_hosts == ["example.gov.in", "example.gov.in", "files.example.gov.in"]
    assert all(kwargs["allow_redirects"] is False for _url, kwargs in session.calls)
    assert all(kwargs["verify"] is True for _url, kwargs in session.calls)


def test_fetch_source_rejects_https_downgrade_before_next_request():
    session = SequenceSession([
        FakeResponse(b"", status_code=302, headers={"Location": "http://example.gov.in/final"}),
    ])

    with pytest.raises(IngestionError, match="source_url_must_be_safe_https"):
        fetch_source(
            "https://example.gov.in/start",
            allowed_hosts=["example.gov.in"],
            session=session,
            resolver=_public_resolver,
        )

    assert len(session.calls) == 1


def test_fetch_source_rejects_sixth_redirect_without_requesting_seventh_url():
    redirects = [
        FakeResponse(b"", status_code=302, headers={"Location": f"/hop-{index}"})
        for index in range(6)
    ]
    session = SequenceSession(redirects)

    with pytest.raises(IngestionError, match="source_redirect_limit_exceeded"):
        fetch_source(
            "https://example.gov.in/start",
            allowed_hosts=["example.gov.in"],
            session=session,
            resolver=_public_resolver,
        )

    assert len(session.calls) == 6


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.1.1", "192.0.2.1"])
def test_fetch_source_rejects_each_non_public_dns_class_before_request(address):
    session = FakeSession(FakeResponse(_html()))

    def resolver(host, port, **kwargs):
        return [(2, 1, 6, "", (address, port))]

    with pytest.raises(IngestionError, match="source_resolves_to_non_public_address"):
        fetch_source(
            "https://example.gov.in/guide",
            allowed_hosts=["example.gov.in"],
            session=session,
            resolver=resolver,
        )

    assert session.calls == []


def test_fetch_source_rejects_mixed_public_and_private_dns_answers():
    session = FakeSession(FakeResponse(_html()))

    def resolver(host, port, **kwargs):
        return [
            (2, 1, 6, "", ("93.184.216.34", port)),
            (2, 1, 6, "", ("127.0.0.1", port)),
        ]

    with pytest.raises(IngestionError, match="source_resolves_to_non_public_address"):
        fetch_source(
            "https://example.gov.in/guide",
            allowed_hosts=["example.gov.in"],
            session=session,
            resolver=resolver,
        )

    assert session.calls == []


def test_extract_html_removes_navigation_script_and_footer_noise():
    result = FetchResult(
        requested_url="https://example.gov.in/guide",
        final_url="https://example.gov.in/guide",
        content_type="text/html",
        body=_html(),
        fetched_at="2026-11-02T00:00:00+00:00",
        sha256=hashlib.sha256(_html()).hexdigest(),
    )

    title, text, extension = extract_text(result)

    assert title == "Official Citizen Procedure"
    assert extension == ".html"
    assert "procedure1" in text
    assert "Privacy Policy" not in text
    assert "bad()" not in text


def test_extract_html_rejects_antibot_challenge_pages():
    body = b"""
    <html><head><title>Request verification</title></head><body>
    Testing whether you are a human visitor. What code is in the image?
    Support ID is 123456789.
    </body></html>
    """
    result = FetchResult(
        requested_url="https://example.gov.in/guide",
        final_url="https://example.gov.in/guide",
        content_type="text/html",
        body=body,
        fetched_at="2026-11-02T00:00:00+00:00",
        sha256=hashlib.sha256(body).hexdigest(),
    )

    with pytest.raises(IngestionError, match="challenge_or_error_page"):
        extract_text(result)


def test_extract_html_allows_legitimate_access_and_rejection_guidance():
    procedural = " ".join(
        "If access is denied or a request is rejected, contact the official grievance authority"
        for _ in range(20)
    )
    body = f"<html><body><main>{procedural}</main></body></html>".encode()
    result = FetchResult(
        requested_url="https://example.gov.in/guide",
        final_url="https://example.gov.in/guide",
        content_type="text/html",
        body=body,
        fetched_at="2026-11-02T00:00:00+00:00",
        sha256=hashlib.sha256(body).hexdigest(),
    )

    _, text, _ = extract_text(result)
    assert "access is denied" in text
    assert "request is rejected" in text


def test_build_records_rejects_exact_and_near_duplicates_and_keeps_provenance():
    text = " ".join(f"token{i} application document eligibility official process" for i in range(250))
    first = build_records(
        source_id="demo_source",
        category="civic",
        title="Demo",
        text=text,
        source_url="https://example.gov.in/guide",
        fetched_date="2026-11-02",
        tags=["demo", "procedure"],
        source_authority="Example Department",
        publication_date="2026-10-01",
        effective_from="2026-11-01",
        jurisdiction="India",
        scheme="Demo Scheme",
        document_type="guideline",
        supersedes=["old-guideline"],
        existing_exact=set(),
        existing_simhashes=[],
    )
    records, stats = first
    assert records
    assert stats["accepted"] == len(records)
    assert records[0].source_authority == "Example Department"
    assert records[0].document_type == "guideline"
    assert records[0].supersedes == ["old-guideline"]

    mirrored_records, mirrored_stats = build_records(
        source_id="demo_source_2",
        category="civic",
        title="Demo",
        text=text,
        source_url="https://example.gov.in/guide2",
        fetched_date="2026-11-02",
        tags=["demo"],
        source_authority="Example Department",
        publication_date=None,
        effective_from=None,
        jurisdiction="India",
        scheme=None,
        document_type="faq",
        supersedes=[],
        existing_exact={" ".join(record.text.lower().split()) for record in records},
        existing_simhashes=[_simhash(record.text) for record in records],
    )
    assert mirrored_stats["exact_duplicates"] == 0
    assert mirrored_records
    assert len(mirrored_records) == len(records)


def test_ingest_source_writes_immutable_raw_refined_and_registered_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    _manifest(manifest)
    raw_root = tmp_path / "raw" / "official_sources"
    refined_root = tmp_path / "refined" / "official_sources"
    session = FakeSession(FakeResponse(_html()))
    monkeypatch.setattr(
        "backend.offline.ingest_official_source._existing_fingerprints",
        lambda **kwargs: (set(), []),
    )

    result = ingest_source(
        source_id="official_demo",
        url="https://example.gov.in/guide",
        allowed_hosts=["example.gov.in"],
        category="civic",
        tags=["demo", "application"],
        source_authority="Example Department",
        jurisdiction="India",
        document_type="official_guide",
        publication_date="2026-10-01",
        raw_root=raw_root,
        refined_root=refined_root,
        manifest_path=manifest,
        data_root=tmp_path,
        register=True,
        session=session,
        resolver=_public_resolver,
    )

    assert result["registered"] is True
    version = hashlib.sha256(_html()).hexdigest()
    dataset_id = f"official_demo_{version[:12]}"
    assert result["dataset_id"] == dataset_id
    assert (raw_root / "official_demo" / version / "body.html").read_bytes() == _html()
    metadata = json.loads((raw_root / "official_demo" / version / "metadata.json").read_text())
    assert metadata["artifact_sha256"] == hashlib.sha256(_html()).hexdigest()
    assert metadata["review_status"] == "pending_human_review"
    assert (refined_root / "official_demo" / f"{version}.jsonl").is_file()

    corpus = load_corpus(manifest, data_root=tmp_path)
    assert corpus.report.complete is True
    assert any(source.dataset_id == dataset_id for doc in corpus.documents for source in doc.sources)

    repeated = ingest_source(
        source_id="official_demo",
        url="https://example.gov.in/guide",
        allowed_hosts=["example.gov.in"],
        category="civic",
        tags=["demo", "application"],
        source_authority="Example Department",
        jurisdiction="India",
        document_type="official_guide",
        publication_date="2026-10-01",
        raw_root=raw_root,
        refined_root=refined_root,
        manifest_path=manifest,
        data_root=tmp_path,
        register=True,
        session=session,
        resolver=_public_resolver,
    )
    assert repeated["idempotent"] is True
    assert repeated["registered"] is True
