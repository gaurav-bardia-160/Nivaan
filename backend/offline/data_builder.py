from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, PROJECT_ROOT

SOURCES_PATH = DATA_DIR / "sources.json"
RAW_DIR = DATA_DIR / "raw"
STRUCTURED_DIR = DATA_DIR / "structured"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge_base.json"


@dataclass(frozen=True)
class SourceDocument:
    id: str
    title: str
    url: str
    text: str
    fetched_at: str


@dataclass(frozen=True)
class CleanChunk:
    source_id: str
    title: str
    url: str
    chunk_id: str
    text: str
    fetched_at: str


def load_sources(path: Path = SOURCES_PATH) -> list[dict[str, Any]]:
    """Load whitelisted offline source metadata.

    The current safe implementation reads metadata only. Network crawling should be
    added later with domain allow-lists and robots/terms checks.
    """

    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        sources = payload.get("sources", [])
    else:
        sources = payload
    return [source for source in sources if isinstance(source, dict)]


def crawl_sources(sources: list[dict[str, Any]] | None = None) -> list[SourceDocument]:
    """Return local source documents from checked-in raw text files.

    This is intentionally offline-only for now. Each source may point to a local
    `raw_path` under the repo. Live downloads are a later build step.
    """

    documents: list[SourceDocument] = []
    for index, source in enumerate(sources or load_sources(), start=1):
        raw_path = source.get("raw_path")
        if not raw_path:
            continue
        candidate = (PROJECT_ROOT / str(raw_path)).resolve()
        if not candidate.exists() or PROJECT_ROOT not in candidate.parents:
            continue
        text = candidate.read_text(encoding="utf-8")
        documents.append(
            SourceDocument(
                id=str(source.get("id") or f"source_{index}"),
                title=str(source.get("title") or candidate.stem),
                url=str(source.get("url") or ""),
                text=text,
                fetched_at=str(source.get("fetched_at") or date.today().isoformat()),
            )
        )
    return documents


def clean_and_chunk(documents: list[SourceDocument], *, max_words: int = 450) -> list[CleanChunk]:
    chunks: list[CleanChunk] = []
    for document in documents:
        cleaned = clean_text(document.text)
        words = cleaned.split()
        for start in range(0, len(words), max_words):
            chunk_words = words[start : start + max_words]
            if not chunk_words:
                continue
            chunk_no = start // max_words + 1
            chunks.append(
                CleanChunk(
                    source_id=document.id,
                    title=document.title,
                    url=document.url,
                    chunk_id=f"{document.id}_chunk_{chunk_no}",
                    text=" ".join(chunk_words),
                    fetched_at=document.fetched_at,
                )
            )
    return chunks


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"(?:Home|Contact|Login|Skip to main content)\s+", "", text, flags=re.IGNORECASE)
    return text.strip()


def structure_chunks(chunks: list[CleanChunk]) -> list[dict[str, Any]]:
    """Create unverified draft entries from cleaned chunks.

    This is deterministic and safe. AI-assisted structuring can be added later,
    but drafts must remain unverified until manually reviewed.
    """

    drafts: list[dict[str, Any]] = []
    for chunk in chunks:
        drafts.append(
            {
                "id": chunk.chunk_id,
                "title": chunk.title,
                "category": "general",
                "keywords": [word.lower() for word in chunk.title.split()[:8]],
                "summary": chunk.text[:500],
                "documents": [],
                "steps": [],
                "warnings": [],
                "source_url": chunk.url,
                "last_verified": chunk.fetched_at,
                "status": "unverified",
            }
        )
    return drafts


def write_drafts(drafts: list[dict[str, Any]], output_dir: Path = STRUCTURED_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for draft in drafts:
        path = output_dir / f"{draft['id']}.json"
        path.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def load_verified_entries(input_dir: Path = STRUCTURED_DIR) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not input_dir.exists():
        return entries
    for path in sorted(input_dir.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry.get("status") == "verified":
            entries.append(entry)
    return entries


def build_knowledge_base(entries: list[dict[str, Any]] | None = None, output_path: Path = KNOWLEDGE_BASE_PATH) -> Path:
    selected = entries if entries is not None else load_verified_entries()
    output_path.write_text(json.dumps(selected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def run_offline_build() -> dict[str, int]:
    sources = load_sources()
    documents = crawl_sources(sources)
    chunks = clean_and_chunk(documents)
    drafts = structure_chunks(chunks)
    written = write_drafts(drafts)
    verified = load_verified_entries()
    build_knowledge_base(verified)
    return {
        "sources": len(sources),
        "documents": len(documents),
        "chunks": len(chunks),
        "drafts_written": len(written),
        "verified_entries": len(verified),
    }


__all__ = [
    "CleanChunk",
    "SourceDocument",
    "build_knowledge_base",
    "clean_and_chunk",
    "clean_text",
    "crawl_sources",
    "load_sources",
    "load_verified_entries",
    "run_offline_build",
    "structure_chunks",
    "write_drafts",
]
