"""Unified vector database generator for GovBank Assistant.

Ingests all refined files from backend/data/refined (across all civic domains
like PAN, Aadhaar, and future schemes/legal/banking datasets) into a single,
unified Qdrant vector database in backend/data/vector_index/qdrant.

Does NOT separate vectors into isolated subfolders: all embeddings are kept in
one unified collection so the AI semantic retrieval engine can discover and
rank the most relevant official passages dynamically.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from backend.config import DATA_DIR
from backend.rag.embeddings import DEFAULT_MULTILINGUAL_MODEL, FastEmbedProvider
from backend.rag.loader import DEFAULT_MANIFEST, load_corpus
from backend.rag.models import RagDocument, SourceReference
from backend.rag.retriever import document_text
from backend.rag.vector_store import QdrantLocalVectorStore, write_index_metadata

logger = logging.getLogger("build_vector_db")

DEFAULT_REFINED_DIR = DATA_DIR / "refined"
DEFAULT_VECTOR_DIR = DATA_DIR / "vector_index" / "qdrant"
DEFAULT_COLLECTION = "govbank_chunks"


def clean_title(raw_title: str) -> str:
    """Strip markdown links/images and unescape HTML in page titles."""
    if not raw_title:
        return ""
    text = html.unescape(raw_title)
    # Remove nested markdown images/links like [ ![Logo](url) ](target "Home")
    text = re.sub(r"\[\s*!\[[^\]]*\]\([^)]+\)\s*\]\([^)]+\)", "", text)
    # Remove standard markdown images ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Convert remaining markdown links [label](url) to label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove any stray HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Normalize whitespaces
    return " ".join(text.split())


def _normalize_category(raw_category: str | None, folder_name: str) -> str:
    """Normalize category to a safe civic identifier."""
    candidate = (raw_category or folder_name or "general").strip().lower()
    # Map common synonyms
    if candidate in ("uidai", "aadhaar", "aadhar"):
        return "aadhaar"
    if candidate in ("pan", "tinpan", "incometax"):
        return "pan"
    cleaned = re.sub(r"[^a-z0-9_-]", "", candidate)
    return cleaned or "general"


def discover_and_load_records(source_dir: Path) -> list[dict[str, Any]]:
    """Recursively scan source_dir for all refined JSON / JSONL files.

    Deduplicates across files and prevents double-loading when both
    .jsonl and individual .json chunk files exist in the same folder.
    """
    source_path = Path(source_dir).resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_path}")

    records_by_id: dict[str, dict[str, Any]] = {}
    seen_content_hashes: set[str] = set()

    # Discover all directories with refined data
    directories = [source_path] + [p for p in source_path.rglob("*") if p.is_dir()]

    for folder in directories:
        jsonl_files = sorted(folder.glob("*.jsonl"))
        json_files = sorted(folder.glob("*.json"))

        folder_category = folder.name.lower()

        # If .jsonl exists in folder, use it as the preferred consolidated format
        if jsonl_files:
            for jsonl_file in jsonl_files:
                try:
                    with jsonl_file.open("r", encoding="utf-8-sig") as f:
                        for line_num, line in enumerate(f, 1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                                _ingest_raw_record(
                                    record,
                                    records_by_id,
                                    seen_content_hashes,
                                    default_category=folder_category,
                                    origin=f"{jsonl_file.name}:{line_num}",
                                )
                            except json.JSONDecodeError as exc:
                                logger.warning("Skipping malformed line in %s:%d: %s", jsonl_file.name, line_num, exc)
                except OSError as exc:
                    logger.error("Failed to read %s: %s", jsonl_file, exc)
        elif json_files:
            # Fallback to individual .json files if no .jsonl exists
            for json_file in json_files:
                try:
                    with json_file.open("r", encoding="utf-8-sig") as f:
                        record = json.load(f)
                        _ingest_raw_record(
                            record,
                            records_by_id,
                            seen_content_hashes,
                            default_category=folder_category,
                            origin=json_file.name,
                        )
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Skipping unreadable JSON file %s: %s", json_file.name, exc)

    return list(records_by_id.values())


def _ingest_raw_record(
    record: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]],
    seen_content_hashes: set[str],
    *,
    default_category: str,
    origin: str,
) -> None:
    """Validate and register a raw record if unique."""
    if not isinstance(record, dict):
        return

    text = (record.get("text") or "").strip()
    if not text:
        return

    # Check content hash deduplication
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if content_hash in seen_content_hashes:
        return

    record_id = str(record.get("id") or f"doc_{content_hash[:12]}")
    if record_id in records_by_id:
        return

    category = _normalize_category(record.get("category"), default_category)
    cleaned_doc_title = clean_title(str(record.get("title") or record_id))

    tags = record.get("retrieval_tags") or []
    if isinstance(tags, list):
        clean_tags = [str(t).strip() for t in tags if str(t).strip()]
    else:
        clean_tags = []

    prepared = {
        "id": record_id,
        "content_hash": content_hash,
        "source_url": str(record.get("source_url") or "https://gov.in"),
        "title": cleaned_doc_title,
        "section": str(record.get("section") or "General"),
        "text": text,
        "category": category,
        "last_verified": str(record.get("last_verified") or date.today().isoformat()),
        "status": str(record.get("status") or "unverified"),
        "quality_score": float(record.get("quality_score") or 0.8),
        "source_confidence": str(record.get("source_confidence") or "official"),
        "verification_method": str(record.get("verification_method") or "automated_official_source"),
        "retrieval_tags": clean_tags,
        "language": str(record.get("language") or "en"),
        "origin": origin,
    }

    seen_content_hashes.add(content_hash)
    records_by_id[record_id] = prepared


def records_to_rag_documents(records: Sequence[dict[str, Any]]) -> tuple[RagDocument, ...]:
    """Convert raw records into immutable RagDocument objects."""
    documents: list[RagDocument] = []
    for r in records:
        source_ref = SourceReference(
            dataset_id=r["category"],
            record_id=r["id"],
            source_url=r["source_url"],
            title=r["title"],
            section=r["section"],
            reported_status=r["status"],
            reported_last_verified=r["last_verified"],
            reported_quality_score=r["quality_score"],
            reported_verification_method=r["verification_method"],
            reported_source_confidence=r["source_confidence"],
        )
        doc = RagDocument(
            id=r["id"],
            content_hash=r["content_hash"],
            category=r["category"],
            text=r["text"],
            language=r["language"],
            tags=tuple(sorted(set(r["retrieval_tags"]))),
            sources=(source_ref,),
            warnings=(),
        )
        documents.append(doc)
    return tuple(documents)


def build_unified_vector_db(
    *,
    source_dir: Path | str = DEFAULT_REFINED_DIR,
    dest_dir: Path | str = DEFAULT_VECTOR_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    model_name: str = DEFAULT_MULTILINGUAL_MODEL,
    batch_size: int = 32,
    manifest_path: Path | str | None = None,
    use_canonical_loader: bool = True,
) -> dict[str, Any]:
    """Build a single, unified vector database from all refined files.

    All datasets (PAN, UIDAI, and future schemes/legal/banking datasets)
    are embedded together in one single collection so the AI model can
    determine relevance across domains without separate database folders.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be a positive integer")

    source_path = Path(source_dir).resolve()
    dest_path = Path(dest_dir).resolve()
    manifest_file = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST

    corpus_sha256 = ""
    if use_canonical_loader and manifest_file.is_file() and (manifest_path is not None or source_path == DEFAULT_REFINED_DIR.resolve()):
        logger.info("Loading canonical safe corpus via rag.loader: %s", manifest_file)
        load_result = load_corpus(manifest_file)
        documents = load_result.documents
        corpus_sha256 = load_result.report.corpus_sha256
        logger.info(
            "Loaded %d safe canonical documents (rejected %d unsafe records, SHA: %s)",
            len(documents),
            load_result.report.rejected_records,
            load_result.report.corpus_sha256[:12] if load_result.report.corpus_sha256 else "none",
        )
    else:
        logger.info("Scanning refined documents from: %s", source_path)
        records = discover_and_load_records(source_path)
        if not records:
            raise RuntimeError(f"No valid refined records found in {source_path}")

        documents = records_to_rag_documents(records)
        corpus_sha256 = hashlib.sha256(
            json.dumps(
                [(document.id, document.content_hash) for document in documents],
                ensure_ascii=True,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        logger.info("Loaded %d unique canonical documents", len(documents))

    category_counts: dict[str, int] = {}
    for doc in documents:
        category_counts[doc.category] = category_counts.get(doc.category, 0) + 1

    logger.info("Initializing multilingual embedding provider: %s", model_name)
    provider = FastEmbedProvider(model=model_name)

    logger.info("Generating dense embeddings for %d documents (batch size %d)...", len(documents), batch_size)
    vectors: list[tuple[float, ...]] = []
    total = len(documents)

    for offset in range(0, total, batch_size):
        batch = documents[offset : offset + batch_size]
        # Include category, tags, title, section, and text in the embedding input
        texts = tuple(document_text(doc) for doc in batch)
        batch_vectors = provider.embed_texts(texts)
        vectors.extend(batch_vectors)
        done = min(offset + batch_size, total)
        if done % 100 == 0 or done == total:
            logger.info("Embedded %d / %d documents (%.1f%%)", done, total, (done / total) * 100)

    logger.info("Storing vectors into unified Qdrant database: %s", dest_path)
    dest_path.mkdir(parents=True, exist_ok=True)
    store = QdrantLocalVectorStore(dest_path, collection=collection_name)
    store.rebuild(documents, tuple(vectors))

    health = store.health()
    store.close()
    metadata = {
        "schema_version": 1,
        "collection": collection_name,
        "documents": len(documents),
        "corpus_sha256": corpus_sha256,
        "embedding_provider": provider.info.provider,
        "embedding_model": provider.info.model,
        "dimensions": provider.info.dimensions,
    }
    write_index_metadata(dest_path, metadata)
    logger.info("Vector database successfully built: %s", health)

    return {
        "status": "success",
        "total_documents": len(documents),
        "dimensions": provider.info.dimensions,
        "collection": collection_name,
        "database_path": str(dest_path),
        "categories": category_counts,
        "model": model_name,
        "corpus_sha256": corpus_sha256,
        "index_metadata": metadata,
        "vector_store_health": health,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(
        description="Convert all refined files into a single unified vector database for GovBank Assistant."
    )
    parser.add_argument(
        "--source",
        "-s",
        type=Path,
        default=DEFAULT_REFINED_DIR,
        help="Path to the directory containing refined files (default: backend/data/refined)",
    )
    parser.add_argument(
        "--dest",
        "-d",
        type=Path,
        default=DEFAULT_VECTOR_DIR,
        help="Path to output Qdrant vector database (default: backend/data/vector_index/qdrant)",
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=DEFAULT_COLLECTION,
        help="Qdrant collection name (default: govbank_chunks)",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=32,
        help="Embedding batch size (default: 32)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=DEFAULT_MULTILINGUAL_MODEL,
        help="Embedding model name (default: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)",
    )
    parser.add_argument(
        "--manifest",
        "-man",
        type=Path,
        default=None,
        help="Path to rag_manifest.json to enforce safe canonical ingestion (default: auto-detected)",
    )

    args = parser.parse_args()

    try:
        result = build_unified_vector_db(
            source_dir=args.source,
            dest_dir=args.dest,
            collection_name=args.collection,
            model_name=args.model,
            batch_size=args.batch_size,
            manifest_path=args.manifest,
        )
        print("\n=== Vector Database Build Summary ===")
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        logger.error("Build failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
