"""Inspect and build the local vector index required for hybrid RAG.

The command is safe to run before every local launch. It reuses a complete index
and rebuilds only when the stored point count does not match the canonical safe
corpus. A build failure is reported with a non-zero exit code so launchers can
warn and continue with the deterministic lexical fallback.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Callable

from backend.config import DATA_DIR
from backend.offline.build_vector_db import DEFAULT_COLLECTION, DEFAULT_VECTOR_DIR, build_unified_vector_db
from backend.rag.embeddings import DEFAULT_MULTILINGUAL_MODEL
from backend.rag.loader import DEFAULT_MANIFEST, load_corpus
from backend.rag.vector_store import QdrantLocalVectorStore, read_index_metadata

logger = logging.getLogger(__name__)


def inspect_vector_index(
    *,
    dest_dir: Path | str = DEFAULT_VECTOR_DIR,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    data_root: Path | str = DATA_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    model_name: str = DEFAULT_MULTILINGUAL_MODEL,
) -> dict[str, Any]:
    """Return whether the local index exactly covers the canonical corpus."""
    destination = Path(dest_dir).resolve()
    load_result = load_corpus(Path(manifest_path), data_root=Path(data_root))
    expected_documents = len(load_result.documents)
    base = {
        "path": str(destination),
        "collection": collection_name,
        "expected_documents": expected_documents,
        "corpus_sha256": load_result.report.corpus_sha256,
    }

    if not destination.is_dir() or not any(destination.iterdir()):
        return {**base, "ready": False, "points": 0, "reason": "missing_index"}

    metadata = read_index_metadata(destination)
    if metadata is None:
        return {**base, "ready": False, "points": 0, "reason": "missing_metadata"}
    if metadata.get("corpus_sha256") != base["corpus_sha256"]:
        return {**base, "ready": False, "points": 0, "reason": "corpus_hash_mismatch"}
    if metadata.get("embedding_model") != model_name:
        return {**base, "ready": False, "points": 0, "reason": "embedding_model_mismatch"}
    if metadata.get("collection") != collection_name or metadata.get("documents") != expected_documents:
        return {**base, "ready": False, "points": 0, "reason": "metadata_count_mismatch"}
    if not isinstance(metadata.get("dimensions"), int) or int(metadata["dimensions"]) < 1:
        return {**base, "ready": False, "points": 0, "reason": "invalid_dimensions"}

    use_runtime_cache = (
        destination == Path(DEFAULT_VECTOR_DIR).resolve()
        and Path(manifest_path).resolve() == Path(DEFAULT_MANIFEST).resolve()
        and Path(data_root).resolve() == Path(DATA_DIR).resolve()
        and collection_name == DEFAULT_COLLECTION
    )
    if use_runtime_cache:
        try:
            from backend.rag.runtime import get_retriever

            active_r = get_retriever()
            if active_r.vector_store and hasattr(active_r.vector_store, "health"):
                health = active_r.vector_store.health()
                points = int(health.get("points", 0))
                ready = bool(health.get("ready")) and points == expected_documents
                return {
                    **base,
                    "ready": ready,
                    "points": points,
                    "dimensions": metadata["dimensions"],
                    "embedding_model": metadata["embedding_model"],
                    "reason": "ready" if ready else "document_count_mismatch",
                }
        except Exception:
            pass

    store = None
    try:
        store = QdrantLocalVectorStore(destination, collection=collection_name)
        health = store.health()
        points = int(health.get("points", 0))
        ready = bool(health.get("ready")) and points == expected_documents
        return {
            **base,
            "ready": ready,
            "points": points,
            "dimensions": metadata["dimensions"],
            "embedding_model": metadata["embedding_model"],
            "reason": "ready" if ready else "document_count_mismatch",
        }
    except (OSError, RuntimeError, ValueError) as exc:
        return {**base, "ready": False, "points": 0, "reason": f"unavailable:{type(exc).__name__}"}



def ensure_vector_index(
    *,
    dest_dir: Path | str = DEFAULT_VECTOR_DIR,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    data_root: Path | str = DATA_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    batch_size: int = 32,
    builder: Callable[..., dict[str, Any]] = build_unified_vector_db,
) -> dict[str, Any]:
    """Reuse a complete index or rebuild it from the canonical manifest."""
    before = inspect_vector_index(
        dest_dir=dest_dir,
        manifest_path=manifest_path,
        data_root=data_root,
        collection_name=collection_name,
        model_name=DEFAULT_MULTILINGUAL_MODEL,
    )
    if before["ready"]:
        return {**before, "action": "reused"}

    logger.info("Vector index is not ready (%s); rebuilding it now.", before["reason"])
    builder(
        dest_dir=dest_dir,
        manifest_path=manifest_path,
        data_root=data_root,
        collection_name=collection_name,
        model_name=DEFAULT_MULTILINGUAL_MODEL,
        batch_size=batch_size,
    )
    after = inspect_vector_index(
        dest_dir=dest_dir,
        manifest_path=manifest_path,
        data_root=data_root,
        collection_name=collection_name,
    )
    if not after["ready"]:
        raise RuntimeError(
            "vector index rebuild completed but readiness validation failed: "
            f"{after['points']}/{after['expected_documents']} documents"
        )
    return {**after, "action": "rebuilt"}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Ensure the canonical GovBank vector index is ready.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_VECTOR_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--data-root", type=Path, default=DATA_DIR)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    try:
        if args.check_only:
            result = inspect_vector_index(
                dest_dir=args.dest,
                manifest_path=args.manifest,
                data_root=args.data_root,
                collection_name=args.collection,
            )
            print(json.dumps(result, indent=2))
            return 0 if result["ready"] else 1

        result = ensure_vector_index(
            dest_dir=args.dest,
            manifest_path=args.manifest,
            data_root=args.data_root,
            collection_name=args.collection,
            batch_size=args.batch_size,
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        logger.error("Vector readiness failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
