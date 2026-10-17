"""Embedding provider contracts and the optional local FastEmbed implementation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

DEFAULT_MULTILINGUAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


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


class FastEmbedProvider:
    """Local multilingual ONNX embeddings with no text sent to a cloud API."""

    def __init__(self, model: str = DEFAULT_MULTILINGUAL_MODEL):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingsUnavailable("install qdrant-client[fastembed] to enable local embeddings") from exc
        self._model_name = model
        self._model = TextEmbedding(model_name=model)
        dimensions = len(next(iter(self._model.embed(["dimension probe"]))))
        self._info = EmbeddingModelInfo(
            provider="fastembed",
            model=model,
            dimensions=dimensions,
            multilingual=True,
        )

    @property
    def info(self) -> EmbeddingModelInfo:
        return self._info

    def embed_texts(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        vectors = self._model.embed(list(texts))
        return tuple(tuple(float(value) for value in vector) for vector in vectors)


__all__ = [
    "DEFAULT_MULTILINGUAL_MODEL",
    "DisabledEmbeddingProvider",
    "EmbeddingModelInfo",
    "EmbeddingProvider",
    "EmbeddingsUnavailable",
    "FastEmbedProvider",
]
