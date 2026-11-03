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
REFINED_DIR = DATA_DIR / "refined"
STRUCTURED_DIR = DATA_DIR / "structured"


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
    doc_title: str
    section: str
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
        if "sources" in payload:
            sources = payload.get("sources", [])
        else:
            sources = []
            for val in payload.values():
                if isinstance(val, list):
                    sources.extend(val)
    else:
        sources = payload
    return [source for source in sources if isinstance(source, dict)]


def crawl_sources(sources: list[dict[str, Any]] | None = None) -> list[SourceDocument]:
    """Return local source documents from downloaded refined text files in REFINED_DIR."""
    documents: list[SourceDocument] = []
    
    if not REFINED_DIR.exists():
        return documents
        
    for index, path in enumerate(REFINED_DIR.glob("*.txt"), start=1):
        content = path.read_text(encoding="utf-8")
        lines = content.split('\n')
        url = ""
        text_lines = []
        
        for line in lines:
            if line.startswith("URL: "):
                url = line.replace("URL: ", "").strip()
            else:
                text_lines.append(line)
                
        text = '\n'.join(text_lines).strip()
        
        documents.append(
            SourceDocument(
                id=f"source_{index}",
                title=path.stem,
                url=url,
                text=text,
                fetched_at=date.today().isoformat(),
            )
        )
    return documents


def clean_and_chunk(documents: list[SourceDocument], *, max_words: int | None = None) -> list[CleanChunk]:
    chunks: list[CleanChunk] = []
    for document in documents:
        cleaned = clean_text(document.text)
        
        if max_words:
            words = cleaned.split()
            for start in range(0, len(words), max_words):
                chunk_words = words[start : start + max_words]
                if not chunk_words:
                    continue
                chunk_no = start // max_words + 1
                chunks.append(
                    CleanChunk(
                        source_id=document.id,
                        doc_title=document.title,
                        section=document.title,
                        url=document.url,
                        chunk_id=f"{document.id}_chunk_{chunk_no}",
                        text=" ".join(chunk_words),
                        fetched_at=document.fetched_at,
                    )
                )
            continue
        
        # Chunk by markdown headings (## or #)
        # We split by \n# and then restore the #
        raw_chunks = re.split(r'\n(?=#+ )', cleaned)
        
        for i, chunk_text in enumerate(raw_chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text or len(chunk_text) < 20: # skip very small chunks
                continue
                
            # Try to extract a section title from the heading
            section = document.title
            lines = chunk_text.split('\n')
            if lines and lines[0].startswith('#'):
                section = lines[0].strip('# ').strip()
                
            chunks.append(
                CleanChunk(
                    source_id=document.id,
                    doc_title=document.title,
                    section=section,
                    url=document.url,
                    chunk_id=f"{document.id}_chunk_{i+1}",
                    text=chunk_text,
                    fetched_at=document.fetched_at,
                )
            )
    return chunks


def clean_text(text: str) -> str:
    text = re.sub(r"(?:Home|Contact|Login|Skip to main content)\s+", "", text or "", flags=re.IGNORECASE)
    # We remove excessive empty lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def structure_chunks(chunks: list[CleanChunk]) -> list[dict[str, Any]]:
    """Create unverified draft entries from cleaned chunks."""

    drafts: list[dict[str, Any]] = []
    for chunk in chunks:
        drafts.append(
            {
                "id": chunk.chunk_id,
                "source_url": chunk.url,
                "title": chunk.doc_title,
                "section": chunk.section,
                "text": chunk.text,
                "category": "aadhaar",
                "last_verified": chunk.fetched_at,
                "status": "unverified"
            }
        )
    return drafts


def write_drafts(drafts: list[dict[str, Any]], output_dir: Path = STRUCTURED_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    
    # Write the combined JSONL
    processed_dir = DATA_DIR / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = processed_dir / "uidai_chunks.jsonl"
    
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for draft in drafts:
            f.write(json.dumps(draft, ensure_ascii=False) + '\n')
            
    # Also write individual JSONs to structured dir for backward compatibility
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



def run_offline_build() -> dict[str, int]:
    sources = load_sources()
    documents = crawl_sources(sources)
    chunks = clean_and_chunk(documents)
    drafts = structure_chunks(chunks)
    written = write_drafts(drafts)
    verified = load_verified_entries()
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
    "clean_and_chunk",
    "clean_text",
    "crawl_sources",
    "load_sources",
    "load_verified_entries",
    "run_offline_build",
    "structure_chunks",
    "write_drafts",
]
