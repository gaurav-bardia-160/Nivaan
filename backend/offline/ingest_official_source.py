"""Safely ingest one authoritative HTTPS source into the canonical RAG corpus.

The command deliberately processes one URL per invocation. It preserves the fetched
artifact, records cryptographic provenance, extracts HTML or PDF text, removes common
navigation noise, rejects exact and near duplicates, writes schema-compliant JSONL,
and optionally registers the new dataset in ``rag_manifest.json``.

It never rebuilds the vector index automatically. Call ``ensure_vector_db`` only after
reviewing the refined passages and accepting the manifest change.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import io
import json
import os
import re
import socket
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from backend.config import DATA_DIR
from backend.rag.loader import DEFAULT_MANIFEST, load_corpus
from backend.rag.models import ChunkRecord, CorpusManifest, DatasetSpec

RAW_ROOT = DATA_DIR / "raw" / "official_sources"
REFINED_ROOT = DATA_DIR / "refined" / "official_sources"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_CHUNK_WORDS = 320
DEFAULT_OVERLAP_WORDS = 45
MIN_CHUNK_WORDS = 40

_DROP_TAGS = {
    "script", "style", "noscript", "svg", "canvas", "form", "button", "input",
    "nav", "footer", "header", "aside", "template",
}
_BOILERPLATE = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"^skip to (?:main )?content$",
        r"^screen reader access$",
        r"^select language$",
        r"^website policies$",
        r"^privacy policy$",
        r"^terms (?:and|&) conditions$",
        r"^hyperlink policy$",
        r"^accessibility statement$",
        r"^copyright(?:\s+©)?\s+\d{4}.*$",
        r"^all rights reserved.*$",
        r"^designed,? developed and hosted by.*$",
        r"^last updated\s*:.*$",
        r"^total visitors\s*:.*$",
        r"^follow us(?: on)?\s*:?.*$",
    )
)


_CHALLENGE_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"testing whether you are a human visitor",
        r"support id(?:\s+is)?\s*[:#]?\s*[a-z0-9-]+",
        r"what code is in the image",
    )
)


class IngestionError(RuntimeError):
    """Safe ingestion failure with a concise operator-facing message."""


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    content_type: str
    body: bytes
    fetched_at: str
    sha256: str


def _safe_id(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not value or len(value) > 60:
        raise IngestionError("source_id_must_be_1_to_60_ascii_identifier_characters")
    return value


def _validate_https_url(url: str, allowed_hosts: set[str]) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise IngestionError("invalid_source_url") from exc
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or "\\" in url
        or any(ch.isspace() or ord(ch) < 32 for ch in url)
    ):
        raise IngestionError("source_url_must_be_safe_https")
    if host not in allowed_hosts:
        raise IngestionError(f"source_host_not_approved:{host}")
    return host


def _validate_public_dns(
    host: str,
    resolver: Callable[..., Sequence[tuple]],
) -> None:
    """Reject hosts with any non-public address before an HTTP request is sent."""
    try:
        answers = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise IngestionError(f"source_dns_resolution_failed:{host}") from exc
    if not answers:
        raise IngestionError(f"source_dns_resolution_failed:{host}")
    addresses: set[str] = set()
    for answer in answers:
        try:
            raw_address = answer[4][0].split("%", 1)[0]
            address = ipaddress.ip_address(raw_address)
        except (IndexError, TypeError, ValueError) as exc:
            raise IngestionError(f"source_dns_resolution_failed:{host}") from exc
        addresses.add(str(address))
        if not address.is_global:
            raise IngestionError(f"source_resolves_to_non_public_address:{host}")
    if not addresses:
        raise IngestionError(f"source_dns_resolution_failed:{host}")


def fetch_source(
    url: str,
    *,
    allowed_hosts: Sequence[str],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    session: requests.Session | None = None,
    resolver: Callable[..., Sequence[tuple]] = socket.getaddrinfo,
) -> FetchResult:
    """Fetch one source with verified TLS, safe redirects, DNS checks, and bounds."""
    hosts = {host.strip().lower() for host in allowed_hosts if host.strip()}
    if not hosts:
        raise IngestionError("at_least_one_approved_host_required")
    if type(max_redirects) is not int or max_redirects < 0:
        raise IngestionError("invalid_redirect_limit")
    client = session or requests.Session()
    current_url = url
    redirect_count = 0
    redirect_statuses = {301, 302, 303, 307, 308}
    while True:
        host = _validate_https_url(current_url, hosts)
        _validate_public_dns(host, resolver)
        try:
            response = client.get(
                current_url,
                timeout=timeout_seconds,
                allow_redirects=False,
                stream=True,
                verify=True,
                headers={
                    "User-Agent": "NivaanOfficialSourceIngestor/1.0 (+offline corpus maintenance)",
                    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
                },
            )
        except requests.RequestException as exc:
            raise IngestionError(f"source_fetch_failed:{type(exc).__name__}") from exc
        if response.status_code in redirect_statuses:
            location = response.headers.get("Location")
            close = getattr(response, "close", None)
            if callable(close):
                close()
            if not location:
                raise IngestionError("source_redirect_missing_location")
            if redirect_count >= max_redirects:
                raise IngestionError("source_redirect_limit_exceeded")
            next_url = urljoin(current_url, location)
            _validate_https_url(next_url, hosts)
            redirect_count += 1
            current_url = next_url
            continue
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise IngestionError(f"source_fetch_failed:{type(exc).__name__}") from exc
        break
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > max_bytes:
        raise IngestionError("source_exceeds_size_limit")
    body = bytearray()
    for part in response.iter_content(chunk_size=64 * 1024):
        if not part:
            continue
        body.extend(part)
        if len(body) > max_bytes:
            raise IngestionError("source_exceeds_size_limit")
    if not body:
        raise IngestionError("source_body_empty")
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    raw = bytes(body)
    return FetchResult(
        requested_url=url,
        final_url=current_url,
        content_type=response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower(),
        body=raw,
        fetched_at=fetched_at,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _clean_lines(lines: Iterable[str]) -> str:
    kept: list[str] = []
    previous = ""
    for raw in lines:
        line = " ".join(unicodedata.normalize("NFC", raw).split())
        if not line or line == previous or len(line) < 2:
            continue
        if any(pattern.match(line) for pattern in _BOILERPLATE):
            continue
        if re.fullmatch(r"[|•·\-–—\s]+", line):
            continue
        kept.append(line)
        previous = line
    return "\n".join(kept).strip()


def _assert_not_blocked(text: str) -> None:
    normalized = " ".join(text.split())
    if any(pattern.search(normalized) for pattern in _CHALLENGE_PATTERNS):
        raise IngestionError("source_returned_challenge_or_error_page")


def extract_text(result: FetchResult) -> tuple[str, str, str]:
    """Return title, cleaned text, and artifact extension."""
    is_pdf = result.content_type == "application/pdf" or result.body.startswith(b"%PDF")
    if is_pdf:
        try:
            reader = PdfReader(io.BytesIO(result.body), strict=False)
            pages = [(page.extract_text() or "") for page in reader.pages]
        except Exception as exc:
            raise IngestionError(f"pdf_extraction_failed:{type(exc).__name__}") from exc
        text = _clean_lines("\n".join(pages).splitlines())
        _assert_not_blocked(text)
        title = ""
        if reader.metadata and reader.metadata.title:
            title = " ".join(str(reader.metadata.title).split())
        return title or Path(urlsplit(result.final_url).path).stem or "Official document", text, ".pdf"

    if result.content_type and result.content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
        raise IngestionError(f"unsupported_content_type:{result.content_type}")
    try:
        decoded = result.body.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = result.body.decode("latin-1", errors="replace")
    soup = BeautifulSoup(decoded, "html.parser")
    _assert_not_blocked(soup.get_text(" ", strip=True))
    title = " ".join((soup.title.get_text(" ", strip=True) if soup.title else "").split())
    for node in soup.find_all(_DROP_TAGS):
        node.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = _clean_lines(root.get_text("\n", strip=True).splitlines())
    return title or "Official web page", text, ".html"


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def _simhash(text: str) -> int:
    vector = [0] * 64
    tokens = re.findall(r"[\w'-]+", _normalize_text(text), flags=re.UNICODE)
    features = tokens if len(tokens) < 3 else [" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)]
    for feature in features:
        value = int.from_bytes(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if value & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return result


def _hamming_distance(left: int, right: int) -> int:
    return bin(left ^ right).count("1")


def chunk_text(text: str, *, chunk_words: int = DEFAULT_CHUNK_WORDS, overlap_words: int = DEFAULT_OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return []
    if chunk_words < MIN_CHUNK_WORDS or overlap_words < 0 or overlap_words >= chunk_words:
        raise IngestionError("invalid_chunk_configuration")
    chunks: list[str] = []
    step = chunk_words - overlap_words
    for start in range(0, len(words), step):
        part = words[start:start + chunk_words]
        if len(part) < MIN_CHUNK_WORDS:
            if chunks and len(part) < overlap_words + MIN_CHUNK_WORDS:
                break
            if len(part) < MIN_CHUNK_WORDS:
                continue
        chunks.append(" ".join(part))
        if start + chunk_words >= len(words):
            break
    return chunks


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _existing_fingerprints(*, manifest_path: Path, data_root: Path) -> tuple[set[str], list[int]]:
    corpus = load_corpus(manifest_path, data_root=data_root)
    normalized = {_normalize_text(document.text) for document in corpus.documents}
    return normalized, [_simhash(text) for text in normalized]


def build_records(
    *,
    source_id: str,
    category: str,
    title: str,
    text: str,
    source_url: str,
    fetched_date: str,
    tags: Sequence[str],
    source_authority: str,
    publication_date: str | None,
    effective_from: str | None,
    jurisdiction: str,
    scheme: str | None,
    document_type: str,
    supersedes: Sequence[str],
    existing_exact: set[str],
    existing_simhashes: Sequence[int],
) -> tuple[list[ChunkRecord], dict[str, int]]:
    records: list[ChunkRecord] = []
    stats = {"candidates": 0, "exact_duplicates": 0, "near_duplicates": 0, "accepted": 0}
    seen_exact: set[str] = set()
    seen_simhashes: list[int] = []
    for index, chunk in enumerate(chunk_text(text), 1):
        stats["candidates"] += 1
        normalized = _normalize_text(chunk)
        if normalized in seen_exact:
            stats["exact_duplicates"] += 1
            continue
        fingerprint = _simhash(normalized)
        # Preserve an additional official source reference when the passage is
        # exactly mirrored elsewhere. The canonical loader will merge the text
        # while retaining both source references. Only non-exact near duplicates
        # are suppressed across sources.
        if normalized not in existing_exact and any(
            _hamming_distance(fingerprint, other) <= 3
            for other in (*existing_simhashes, *seen_simhashes)
        ):
            stats["near_duplicates"] += 1
            continue
        quality = min(0.95, 0.65 + min(len(chunk.split()), DEFAULT_CHUNK_WORDS) / 1200)
        record = ChunkRecord(
            id=f"{source_id}_{index:04d}_{hashlib.sha256(normalized.encode()).hexdigest()[:10]}",
            source_url=source_url,
            title=title,
            section=f"Passage {index}",
            text=chunk,
            category=category,
            last_verified=fetched_date,
            status="unverified",
            quality_score=float(round(quality, 3)),
            source_confidence="official",
            verification_method="official_source_extraction_pending_review",
            retrieval_tags=sorted({tag.strip().lower() for tag in tags if tag.strip()}),
            language="en",
            source_authority=source_authority,
            publication_date=publication_date,
            effective_from=effective_from,
            jurisdiction=jurisdiction,
            scheme=scheme,
            document_type=document_type,
            supersedes=list(supersedes),
        )
        records.append(record)
        seen_exact.add(normalized)
        seen_simhashes.append(fingerprint)
    stats["accepted"] = len(records)
    return records, stats


def register_manifest_dataset(
    *,
    manifest_path: Path,
    data_root: Path,
    dataset_id: str,
    relative_path: str,
    category: str,
    allowed_hosts: Sequence[str],
) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = CorpusManifest.model_validate(payload)
    if any(spec.id == dataset_id for spec in manifest.datasets):
        raise IngestionError(f"manifest_dataset_exists:{dataset_id}")
    datasets = list(manifest.datasets) + [DatasetSpec(
        id=dataset_id,
        path=relative_path,
        category=category,
        allowed_hosts=sorted(set(allowed_hosts)),
    )]
    updated = CorpusManifest(schema_version=manifest.schema_version, datasets=datasets)
    updated_bytes = (json.dumps(updated.model_dump(), indent=2) + "\n").encode("utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=manifest_path.name + ".validation.", dir=manifest_path.parent)
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_bytes(updated_bytes)
        staged = load_corpus(temporary_path, data_root=data_root)
        if not staged.report.complete:
            raise IngestionError("staged_manifest_validation_failed")
        _atomic_write(manifest_path, updated_bytes)
    finally:
        temporary_path.unlink(missing_ok=True)


def ingest_source(
    *,
    source_id: str,
    url: str,
    allowed_hosts: Sequence[str],
    category: str,
    tags: Sequence[str],
    source_authority: str,
    jurisdiction: str,
    document_type: str,
    publication_date: str | None = None,
    effective_from: str | None = None,
    scheme: str | None = None,
    supersedes: Sequence[str] = (),
    title_override: str | None = None,
    raw_root: Path = RAW_ROOT,
    refined_root: Path = REFINED_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    data_root: Path = DATA_DIR,
    register: bool = False,
    dry_run: bool = False,
    session: requests.Session | None = None,
    resolver: Callable[..., Sequence[tuple]] = socket.getaddrinfo,
) -> dict[str, object]:
    source_id = _safe_id(source_id)
    category = _safe_id(category)
    fetched = fetch_source(url, allowed_hosts=allowed_hosts, session=session, resolver=resolver)
    title, text, extension = extract_text(fetched)
    if len(text.split()) < MIN_CHUNK_WORDS:
        raise IngestionError("insufficient_procedural_text")
    exact, simhashes = _existing_fingerprints(manifest_path=manifest_path, data_root=data_root)
    records, stats = build_records(
        source_id=source_id,
        category=category,
        title=title_override or title,
        text=text,
        source_url=fetched.final_url,
        fetched_date=fetched.fetched_at[:10],
        tags=tags,
        source_authority=source_authority,
        publication_date=publication_date,
        effective_from=effective_from,
        jurisdiction=jurisdiction,
        scheme=scheme,
        document_type=document_type,
        supersedes=supersedes,
        existing_exact=exact,
        existing_simhashes=simhashes,
    )
    if not records:
        raise IngestionError("no_unique_passages_after_deduplication")

    version_id = fetched.sha256
    dataset_id = f"{source_id}_{version_id[:12]}"
    raw_dir = raw_root / source_id / version_id
    raw_file = raw_dir / f"body{extension}"
    metadata_file = raw_dir / "metadata.json"
    refined_file = refined_root / source_id / f"{version_id}.jsonl"
    try:
        relative_refined = refined_file.resolve().relative_to(data_root.resolve()).as_posix()
    except ValueError as exc:
        raise IngestionError("refined_output_must_be_inside_data_root") from exc
    metadata = {
        "schema_version": 1,
        "source_id": source_id,
        "dataset_id": dataset_id,
        "artifact_version": version_id,
        "requested_url": fetched.requested_url,
        "final_url": fetched.final_url,
        "approved_hosts": sorted(set(allowed_hosts)),
        "fetched_at": fetched.fetched_at,
        "content_type": fetched.content_type,
        "artifact_sha256": fetched.sha256,
        "artifact_bytes": len(fetched.body),
        "extracted_title": title,
        "extracted_words": len(text.split()),
        "refined_path": relative_refined,
        "record_count": len(records),
        "deduplication": stats,
        "review_status": "pending_human_review",
        "source_authority": source_authority,
        "publication_date": publication_date,
        "effective_from": effective_from,
        "jurisdiction": jurisdiction,
        "scheme": scheme,
        "document_type": document_type,
        "supersedes": list(supersedes),
    }
    if not dry_run:
        jsonl = "".join(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ).encode("utf-8")
        if raw_file.exists() or metadata_file.exists() or refined_file.exists():
            if (
                raw_file.is_file()
                and raw_file.read_bytes() == fetched.body
                and refined_file.is_file()
                and refined_file.read_bytes() == jsonl
            ):
                return {**metadata, "dry_run": False, "registered": any(
                    spec.id == dataset_id
                    for spec in CorpusManifest.model_validate_json(manifest_path.read_text(encoding="utf-8")).datasets
                ), "idempotent": True}
            raise IngestionError(f"source_version_conflict:{source_id}:{version_id}")
        _atomic_write(raw_file, fetched.body)
        _atomic_write(metadata_file, (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        _atomic_write(refined_file, jsonl)
        if register:
            register_manifest_dataset(
                manifest_path=manifest_path,
                data_root=data_root,
                dataset_id=dataset_id,
                relative_path=relative_refined,
                category=category,
                allowed_hosts=allowed_hosts,
            )
    return {
        **metadata,
        "dry_run": dry_run,
        "registered": bool(register and not dry_run),
        "idempotent": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest exactly one approved official HTTPS source.")
    parser.add_argument("--id", required=True, dest="source_id")
    parser.add_argument("--url", required=True)
    parser.add_argument("--host", action="append", required=True, dest="allowed_hosts")
    parser.add_argument("--category", required=True)
    parser.add_argument("--tag", action="append", default=[], dest="tags")
    parser.add_argument("--title")
    parser.add_argument("--authority", required=True, dest="source_authority")
    parser.add_argument("--jurisdiction", required=True)
    parser.add_argument("--document-type", required=True)
    parser.add_argument("--publication-date")
    parser.add_argument("--effective-from")
    parser.add_argument("--scheme")
    parser.add_argument("--supersedes", action="append", default=[])
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = ingest_source(
            source_id=args.source_id,
            url=args.url,
            allowed_hosts=args.allowed_hosts,
            category=args.category,
            tags=args.tags,
            source_authority=args.source_authority,
            jurisdiction=args.jurisdiction,
            document_type=args.document_type,
            publication_date=args.publication_date,
            effective_from=args.effective_from,
            scheme=args.scheme,
            supersedes=args.supersedes,
            title_override=args.title,
            register=args.register,
            dry_run=args.dry_run,
        )
    except (IngestionError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    print(json.dumps({"status": "ok", **result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
