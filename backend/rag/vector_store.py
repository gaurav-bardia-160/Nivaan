"""Vector-store contracts and a persistent local Qdrant adapter."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from backend.rag.models import RagDocument

INDEX_METADATA_FILENAME = "govbank_index.json"


def read_index_metadata(path: Path | str) -> dict[str, object] | None:
    metadata_path = Path(path) / INDEX_METADATA_FILENAME
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def write_index_metadata(path: Path | str, metadata: dict[str, object]) -> None:
    destination = Path(path)
    destination.mkdir(parents=True, exist_ok=True)
    metadata_path = destination / INDEX_METADATA_FILENAME
    temporary_path = destination / f".{INDEX_METADATA_FILENAME}.tmp"
    temporary_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(metadata_path)


@dataclass(frozen=True)
class VectorHit:
    document_id: str
    score: float


class VectorStore(Protocol):
    def rebuild(self, documents: tuple[RagDocument, ...], vectors: tuple[tuple[float, ...], ...]) -> None: ...

    def search(self, query_vector: tuple[float, ...], *, top_k: int, category: str | None = None) -> tuple[VectorHit, ...]: ...

    def health(self) -> dict[str, object]: ...


class VectorStoreUnavailable(RuntimeError):
    pass


class DisabledVectorStore:
    def rebuild(self, documents: tuple[RagDocument, ...], vectors: tuple[tuple[float, ...], ...]) -> None:
        raise VectorStoreUnavailable("vector_store_not_configured")

    def search(self, query_vector: tuple[float, ...], *, top_k: int, category: str | None = None) -> tuple[VectorHit, ...]:
        raise VectorStoreUnavailable("vector_store_not_configured")

    def health(self) -> dict[str, object]:
        return {"provider": "disabled", "ready": False}


class QdrantLocalVectorStore:
    """Small-corpus persistent Qdrant store using the Python client's local mode."""

    def __init__(self, path: Path | str, *, collection: str = "govbank_chunks"):
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise VectorStoreUnavailable("install qdrant-client to enable vector storage") from exc
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.collection = collection
        self._client = QdrantClient(path=str(self.path), force_disable_check_same_thread=True)

    @staticmethod
    def _point_id(document_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"govbank:{document_id}"))

    def rebuild(self, documents: tuple[RagDocument, ...], vectors: tuple[tuple[float, ...], ...]) -> None:
        if len(documents) != len(vectors):
            raise ValueError("documents and vectors must have the same length")
        if not documents:
            raise ValueError("cannot build an empty vector collection")
        dimensions = len(vectors[0])
        if dimensions < 1 or any(len(vector) != dimensions for vector in vectors):
            raise ValueError("all vectors must have the same non-zero dimensions")

        from qdrant_client.models import Distance, PointStruct, VectorParams

        if self._client.collection_exists(self.collection):
            self._client.delete_collection(self.collection)
        self._client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
        )
        batch_size = 100
        for offset in range(0, len(documents), batch_size):
            points = [
                PointStruct(
                    id=self._point_id(document.id),
                    vector=list(vector),
                    payload={
                        "document_id": document.id,
                        "category": document.category,
                        "title": document.sources[0].title if getattr(document, "sources", None) else "",
                        "source_url": document.sources[0].source_url if getattr(document, "sources", None) else "",
                    },
                )
                for document, vector in zip(documents[offset:offset + batch_size], vectors[offset:offset + batch_size])
            ]
            self._client.upsert(collection_name=self.collection, points=points, wait=True)

    def search(self, query_vector: tuple[float, ...], *, top_k: int, category: str | None = None) -> tuple[VectorHit, ...]:
        if not query_vector or top_k < 1 or not self._client.collection_exists(self.collection):
            return ()
        query_filter = None
        if category:
            from qdrant_client.models import FieldCondition, Filter, MatchValue
            query_filter = Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])
        response = self._client.query_points(
            collection_name=self.collection,
            query=list(query_vector),
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        return tuple(
            VectorHit(document_id=str(point.payload["document_id"]), score=float(point.score))
            for point in response.points
            if point.payload and point.payload.get("document_id")
        )

    def health(self) -> dict[str, object]:
        exists = self._client.collection_exists(self.collection)
        count = 0
        if exists:
            count = int(self._client.count(collection_name=self.collection, exact=True).count)
        return {
            "provider": "qdrant_local",
            "ready": exists and count > 0,
            "collection": self.collection,
            "points": count,
            "path": str(self.path),
        }

    def close(self) -> None:
        if hasattr(self, "_client") and self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass



__all__ = [
    "DisabledVectorStore",
    "QdrantLocalVectorStore",
    "VectorHit",
    "VectorStore",
    "VectorStoreUnavailable",
    "read_index_metadata",
    "write_index_metadata",
]
