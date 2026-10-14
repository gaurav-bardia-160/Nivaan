"""Embedding provider contracts only. Real providers arrive after lexical baseline evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingModelInfo:
    provider: str
    model: str
    dimensions: int
    revision: str | None = None
    multilingual: bool = False


class EmbeddingProvider(Protocol):
    @property
    def info(self) -> EmbeddingModelInfo: ...

    def embed_texts(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class EmbeddingsUnavailable(RuntimeError):
    pass


class DisabledEmbeddingProvider:
    @property
    def info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(provider="disabled", model="none", dimensions=0, multilingual=False)

    def embed_texts(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        raise EmbeddingsUnavailable("embedding_provider_not_configured")
