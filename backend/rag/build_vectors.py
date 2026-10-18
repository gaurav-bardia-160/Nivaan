"""Build the local persistent vector index from the canonical corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.config import DATA_DIR
from backend.rag.embeddings import DEFAULT_MULTILINGUAL_MODEL, FastEmbedProvider
from backend.rag.loader import load_corpus
from backend.rag.retriever import document_text
from backend.rag.vector_store import QdrantLocalVectorStore

DEFAULT_VECTOR_PATH = DATA_DIR / "vector_index" / "qdrant"


def build_vector_index(
    *,
    path: Path = DEFAULT_VECTOR_PATH,
    model: str = DEFAULT_MULTILINGUAL_MODEL,
    batch_size: int = 32,
) -> dict[str, object]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    loaded = load_corpus()
    if not loaded.report.complete or not loaded.documents:
        raise RuntimeError("canonical corpus is incomplete or empty")

    provider = FastEmbedProvider(model=model)
    vectors: list[tuple[float, ...]] = []
    for offset in range(0, len(loaded.documents), batch_size):
        batch = loaded.documents[offset:offset + batch_size]
        vectors.extend(provider.embed_texts(tuple(document_text(document) for document in batch)))

    store = QdrantLocalVectorStore(path)
    store.rebuild(loaded.documents, tuple(vectors))
    health = store.health()
    store.close()
    return {
        "corpus_sha256": loaded.report.corpus_sha256,
        "documents": len(loaded.documents),
        "embedding": provider.info.__dict__,
        "vector_store": health,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_VECTOR_PATH)
    parser.add_argument("--model", default=DEFAULT_MULTILINGUAL_MODEL)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(build_vector_index(path=args.path, model=args.model, batch_size=args.batch_size), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
