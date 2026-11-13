"""Publish reviewed ETL output into the canonical corpus and local runtime index.

The live RAG runtime reads ``backend/data/rag_manifest.json`` and the unified
local Qdrant collection.  This module is the single ETL publication boundary:
it converts refined web-search documents into schema-validated JSONL datasets,
registers them in the canonical manifest, rebuilds the exact local index used by
runtime retrieval, and archives inputs only after the index is ready.

Usage (offline only):
    python -m backend.etl.vectorize

Never import or call this from the live request pipeline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import DATA_DIR, ETL_ARCHIVE_DIR, ETL_REFINED_DIR
from backend.offline.ensure_vector_db import ensure_vector_index
from backend.offline.ingest_official_source import (
    IngestionError,
    _atomic_write,
    _existing_fingerprints,
    _normalize_text,
    _simhash,
    build_records,
)
from backend.rag.loader import DEFAULT_MANIFEST, load_corpus
from backend.rag.models import CorpusManifest, DatasetSpec
from backend.web_search.allowlist import is_allowlisted_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("etl.vectorize")

CANONICAL_ETL_REFINED_DIR = DATA_DIR / "refined" / "etl"

_CATEGORY_MAP = {
    "tax": "tax",
    "banking": "banking",
    "identity": "civic",
    "transport": "civic",
    "agriculture": "civic",
    "legal_consumer": "civic",
    "epf": "civic",
    "general_civic": "civic",
}


def _safe_token(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return (cleaned or fallback)[:60]


def _reported_date(value: object) -> str:
    raw = str(value or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10]).isoformat()
            except ValueError:
                pass
    return date.today().isoformat()


def _canonical_category(domain: object, source_url: str) -> str:
    host = (urlsplit(source_url).hostname or "").lower()
    if host.endswith("uidai.gov.in"):
        return "aadhaar"
    return _CATEGORY_MAP.get(str(domain or "").strip().lower(), "civic")


def _record_title(refined: dict[str, Any], host: str) -> str:
    metadata = refined.get("metadata") if isinstance(refined.get("metadata"), dict) else {}
    scheme = str(metadata.get("scheme_name") or "").strip()
    return scheme[:300] if scheme else f"Official guidance from {host}"


def _record_tags(refined: dict[str, Any]) -> list[str]:
    metadata = refined.get("metadata") if isinstance(refined.get("metadata"), dict) else {}
    candidates = [
        str(refined.get("domain") or ""),
        str(metadata.get("scheme_name") or ""),
        str(metadata.get("error_code") or ""),
        "web search fallback",
    ]
    return sorted({_safe_token(value, fallback="official") for value in candidates if value.strip()})


def _manifest_bytes(manifest: CorpusManifest) -> bytes:
    return (json.dumps(manifest.model_dump(), indent=2) + "\n").encode("utf-8")


def _stage_manifest(
    *,
    manifest_path: Path,
    data_root: Path,
    manifest: CorpusManifest,
) -> bytes:
    updated_bytes = _manifest_bytes(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=manifest_path.name + ".validation.", dir=manifest_path.parent)
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_bytes(updated_bytes)
        staged = load_corpus(temporary_path, data_root=data_root)
        if not staged.report.complete:
            raise IngestionError("staged_manifest_validation_failed")
    finally:
        temporary_path.unlink(missing_ok=True)
    return updated_bytes


def _archive_refined(source: Path, archive_dir: Path) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / source.name
    if destination.exists():
        if destination.is_file() and destination.read_bytes() == source.read_bytes():
            source.unlink()
            return
        raise RuntimeError(f"archive_conflict:{source.name}")
    os.replace(source, destination)


def vectorize_all(
    *,
    refined_dir: Path = ETL_REFINED_DIR,
    archive_dir: Path = ETL_ARCHIVE_DIR,
    canonical_refined_dir: Path = CANONICAL_ETL_REFINED_DIR,
    manifest_path: Path = DEFAULT_MANIFEST,
    data_root: Path = DATA_DIR,
    index_ensurer: Callable[..., dict[str, Any]] = ensure_vector_index,
) -> int:
    """Publish all refined ETL files into the corpus and runtime's local index.

    The legacy function name is retained for scheduler and operator compatibility.
    A refined input is archived only after manifest validation and local index
    readiness succeed.  On publication or index failure, newly written canonical
    files and the manifest are rolled back, and the input remains available for
    retry.
    """
    refined_files = sorted(Path(refined_dir).glob("*.json"))
    if not refined_files:
        logger.info("No refined files to publish.")
        return 0

    manifest_path = Path(manifest_path)
    data_root = Path(data_root).resolve()
    canonical_refined_dir = Path(canonical_refined_dir)
    original_manifest_bytes = manifest_path.read_bytes()
    manifest = CorpusManifest.model_validate_json(original_manifest_bytes)
    existing_specs = {spec.id: spec for spec in manifest.datasets}
    exact, simhashes = _existing_fingerprints(manifest_path=manifest_path, data_root=data_root)

    pending_specs: list[DatasetSpec] = []
    created_files: list[Path] = []
    publishable_inputs: list[Path] = []

    try:
        for refined_path in refined_files:
            try:
                refined = json.loads(refined_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"invalid_refined_file:{refined_path.name}") from exc
            if not isinstance(refined, dict):
                raise RuntimeError(f"invalid_refined_record:{refined_path.name}")

            source_url = str(refined.get("source_url") or "").strip()
            clean_text = str(refined.get("clean_text") or "").strip()
            if not is_allowlisted_url(source_url):
                raise RuntimeError(f"unapproved_source_url:{refined_path.name}")
            if not clean_text:
                raise RuntimeError(f"empty_refined_text:{refined_path.name}")

            host = (urlsplit(source_url).hostname or "").lower()
            url_hash = _safe_token(str(refined.get("url_hash") or refined_path.stem), fallback="source")
            content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
            dataset_id = f"etl_{url_hash[:32]}_{content_hash[:12]}"[:60]
            category = _canonical_category(refined.get("domain"), source_url)
            metadata = refined.get("metadata") if isinstance(refined.get("metadata"), dict) else {}
            fetched_date = _reported_date(metadata.get("fetched_at"))
            scheme = str(metadata.get("scheme_name") or "").strip() or None

            records, _stats = build_records(
                source_id=dataset_id,
                category=category,
                title=_record_title(refined, host),
                text=clean_text,
                source_url=source_url,
                fetched_date=fetched_date,
                tags=_record_tags(refined),
                source_authority=host,
                publication_date=None,
                effective_from=None,
                jurisdiction="India",
                scheme=scheme,
                document_type="official_web_page",
                supersedes=(),
                existing_exact=exact,
                existing_simhashes=simhashes,
            )
            if not records:
                raise RuntimeError(f"no_unique_passages:{refined_path.name}")

            jsonl = "".join(
                json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
                for record in records
            ).encode("utf-8")
            canonical_path = canonical_refined_dir / f"{dataset_id}.jsonl"
            try:
                relative_path = canonical_path.resolve().relative_to(data_root).as_posix()
            except ValueError as exc:
                raise RuntimeError("canonical_refined_dir_must_be_inside_data_root") from exc

            spec = DatasetSpec(
                id=dataset_id,
                path=relative_path,
                category=category,
                allowed_hosts=[host],
            )
            existing = existing_specs.get(dataset_id)
            if existing is not None:
                if existing != spec or not canonical_path.is_file() or canonical_path.read_bytes() != jsonl:
                    raise RuntimeError(f"canonical_dataset_conflict:{dataset_id}")
            else:
                _atomic_write(canonical_path, jsonl)
                created_files.append(canonical_path)
                pending_specs.append(spec)
                existing_specs[dataset_id] = spec

            for record in records:
                normalized = _normalize_text(record.text)
                exact.add(normalized)
                simhashes.append(_simhash(normalized))
            publishable_inputs.append(refined_path)

        updated_manifest = CorpusManifest(
            schema_version=manifest.schema_version,
            datasets=[*manifest.datasets, *pending_specs],
        )
        updated_manifest_bytes = _stage_manifest(
            manifest_path=manifest_path,
            data_root=data_root,
            manifest=updated_manifest,
        )
        _atomic_write(manifest_path, updated_manifest_bytes)

        try:
            index_result = index_ensurer(manifest_path=manifest_path, data_root=data_root)
            if not index_result.get("ready"):
                raise RuntimeError("canonical_index_not_ready")
        except Exception:
            _atomic_write(manifest_path, original_manifest_bytes)
            for path in created_files:
                path.unlink(missing_ok=True)
            try:
                index_ensurer(manifest_path=manifest_path, data_root=data_root)
            except Exception:
                logger.exception("Failed to restore the previous canonical index after rollback")
            raise

        for refined_path in publishable_inputs:
            try:
                _archive_refined(refined_path, Path(archive_dir))
            except (OSError, RuntimeError) as exc:
                # Publication and index readiness are already committed. Keep the
                # refined input in place for an idempotent archival retry instead
                # of rolling the canonical corpus back to a stale index state.
                logger.warning("Published %s but could not archive it: %s", refined_path.name, exc)

        logger.info(
            "Published %d refined files to the canonical corpus and local runtime index.",
            len(publishable_inputs),
        )
        return len(publishable_inputs)
    except Exception:
        if manifest_path.read_bytes() != original_manifest_bytes:
            _atomic_write(manifest_path, original_manifest_bytes)
        for path in created_files:
            path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    count = vectorize_all()
    logger.info("Total published: %d", count)
    raise SystemExit(0)
