"""ETL Phase 2 — Vectorize: Generate embeddings and push to domain-isolated Qdrant collections.

Reads refined JSON files from ETL_REFINED_DIR, generates FastEmbed vectors,
and pushes them to domain-namespaced Qdrant collections (e.g., nivaan_transport).

Collections are created automatically if they don't exist.
Processed files are moved to ETL_ARCHIVE_DIR.

Usage (offline only):
    py -m backend.etl.vectorize

Never import or call this from the live request pipeline.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

# Ensure package is importable when run as __main__
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import ETL_ARCHIVE_DIR, ETL_REFINED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("etl.vectorize")

# Domain → Qdrant collection name mapping
_COLLECTION_MAP: dict[str, str] = {
    "transport": "nivaan_transport",
    "tax": "nivaan_tax",
    "identity": "nivaan_identity",
    "banking": "nivaan_banking",
    "agriculture": "nivaan_agriculture",
    "legal_consumer": "nivaan_legal",
    "epf": "nivaan_epf",
    "general_civic": "nivaan_general",
}

_VECTOR_SIZE = 384  # fastembed default (BAAI/bge-small-en-v1.5)
_CHUNK_SIZE = 400   # approximate token window per chunk
_CHUNK_OVERLAP = 50


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks by approximate word count."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks


def _ensure_collection(client, collection_name: str) -> None:
    """Create Qdrant collection if it doesn't exist."""
    from qdrant_client.models import Distance, VectorParams
    try:
        client.get_collection(collection_name)
    except Exception:
        logger.info("Creating new Qdrant collection: %s", collection_name)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
        )


def vectorize_all() -> int:
    """Vectorize all refined JSON files and push to Qdrant. Returns number of files processed."""
    ETL_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    refined_files = sorted(ETL_REFINED_DIR.glob("*.json"))
    if not refined_files:
        logger.info("No refined files to vectorize.")
        return 0

    # Lazy imports — these are heavy and only needed for offline ETL
    try:
        from fastembed import TextEmbedding
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct
    except ImportError as exc:
        logger.error("Missing ETL dependency: %s — run: py -m pip install fastembed qdrant-client", exc)
        return 0

    import os
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key = os.getenv("QDRANT_API_KEY", None)

    try:
        qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=30)
        embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    except Exception as exc:
        logger.error("Failed to connect to Qdrant or load embedder: %s", exc)
        return 0

    processed_count = 0

    for refined_path in refined_files:
        try:
            refined = json.loads(refined_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read refined file %s: %s", refined_path.name, exc)
            continue

        domain = str(refined.get("domain", "general_civic"))
        collection_name = _COLLECTION_MAP.get(domain, "nivaan_general")
        source_url = str(refined.get("source_url", ""))
        clean_text = str(refined.get("clean_text", ""))
        url_hash = str(refined.get("url_hash", refined_path.stem))
        metadata = refined.get("metadata", {})

        if not clean_text.strip():
            logger.warning("Empty clean_text in %s — skipping", refined_path.name)
            continue

        # Ensure collection exists
        _ensure_collection(qdrant, collection_name)

        # Chunk the text
        chunks = _chunk_text(clean_text)
        if not chunks:
            continue

        logger.info(
            "Vectorizing %d chunks → %s | source: %.60s",
            len(chunks), collection_name, source_url,
        )

        # Generate embeddings
        try:
            embeddings = list(embedder.embed(chunks))
        except Exception as exc:
            logger.error("Embedding failed for %s: %s", refined_path.name, exc)
            continue

        # Build Qdrant points
        points = []
        for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_url}#{i}"))
            payload = {
                "text": chunk_text,
                "source_url": source_url,
                "domain": domain,
                "url_hash": url_hash,
                "chunk_index": i,
                "error_code": metadata.get("error_code"),
                "scheme_name": metadata.get("scheme_name"),
                "fetched_at": metadata.get("fetched_at", ""),
                "etl_source": "web_search_fallback",
            }
            points.append(PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload=payload,
            ))

        # Upsert to Qdrant
        try:
            qdrant.upsert(collection_name=collection_name, points=points, wait=True)
            logger.info("Upserted %d points to %s", len(points), collection_name)
        except Exception as exc:
            logger.error("Qdrant upsert failed for %s: %s", refined_path.name, exc)
            continue

        # Archive processed refined file
        archive_path = ETL_ARCHIVE_DIR / refined_path.name
        try:
            refined_path.rename(archive_path)
            logger.debug("Archived: %s → %s", refined_path.name, archive_path)
        except Exception as exc:
            logger.warning("Failed to archive %s: %s", refined_path.name, exc)

        processed_count += 1

    logger.info("Vectorize complete. Processed %d files.", processed_count)
    return processed_count


if __name__ == "__main__":
    count = vectorize_all()
    logger.info("Total vectorized: %d", count)
    sys.exit(0)
