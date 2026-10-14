"""Vector-store contracts. M1 does not require a concrete external store."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.rag.models import RagDocument


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
