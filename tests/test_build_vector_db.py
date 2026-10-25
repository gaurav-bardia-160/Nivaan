from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.offline.build_vector_db import (
    clean_title,
    discover_and_load_records,
    records_to_rag_documents,
)


def test_clean_title_removes_markdown_and_html():
    raw = '[ ![EFiling Logo](https://incometax.gov.in/logo.svg) ](https://incometax.gov.in/ "Home") Link Aadhaar &amp; PAN'
    cleaned = clean_title(raw)
    assert cleaned == "Link Aadhaar & PAN"
    assert "Logo" not in cleaned
    assert "https://" not in cleaned
    assert "&amp;" not in cleaned


def test_discover_and_load_records_deduplicates_and_loads_jsonl(tmp_path):
    refined_dir = tmp_path / "refined"
    pan_dir = refined_dir / "pan"
    pan_dir.mkdir(parents=True)

    record_1 = {
        "id": "pan_1",
        "title": "PAN Guide",
        "section": "General",
        "text": "How to apply for PAN card online via Form 49A.",
        "category": "pan",
        "source_url": "https://tinpan.proteantech.in",
        "retrieval_tags": ["pan", "form49a"],
    }
    # Duplicate text with different id
    record_duplicate = {
        "id": "pan_2",
        "title": "Duplicate PAN Guide",
        "section": "General",
        "text": "How to apply for PAN card online via Form 49A.",
        "category": "pan",
        "source_url": "https://tinpan.proteantech.in",
        "retrieval_tags": ["pan"],
    }
    record_3 = {
        "id": "pan_3",
        "title": "Download e-PAN",
        "section": "e-PAN",
        "text": "How to download e-PAN card PDF directly from portal.",
        "category": "pan",
        "source_url": "https://tinpan.proteantech.in",
        "retrieval_tags": ["epan"],
    }

    (pan_dir / "pan_chunks.jsonl").write_text(
        "\n".join(json.dumps(r) for r in (record_1, record_duplicate, record_3)) + "\n",
        encoding="utf-8",
    )

    records = discover_and_load_records(refined_dir)
    assert len(records) == 2  # record_duplicate should be deduplicated
    assert records[0]["id"] == "pan_1"
    assert records[1]["id"] == "pan_3"

    docs = records_to_rag_documents(records)
    assert len(docs) == 2
    assert docs[0].category == "pan"
    assert "pan" in docs[0].tags


def test_discover_and_load_records_handles_standalone_json_files_and_bom(tmp_path):
    refined_dir = tmp_path / "refined"
    schemes_dir = refined_dir / "schemes"
    schemes_dir.mkdir(parents=True)

    record = {
        "id": "scheme_101",
        "title": "PM Kisan Scheme",
        "text": "Beneficiaries receive financial support directly to their bank accounts.",
        "category": "schemes",
        "source_url": "https://pmkisan.gov.in",
    }
    # Write with UTF-8 BOM
    (schemes_dir / "chunk_1.json").write_text(json.dumps(record), encoding="utf-8-sig")

    records = discover_and_load_records(refined_dir)
    assert len(records) == 1
    assert records[0]["id"] == "scheme_101"
    assert records[0]["category"] == "schemes"


def test_build_unified_vector_db_end_to_end(tmp_path, monkeypatch):
    pytest.importorskip("qdrant_client")
    refined_dir = tmp_path / "refined"
    schemes_dir = refined_dir / "schemes"
    schemes_dir.mkdir(parents=True)

    record = {
        "id": "doc_1",
        "title": "Aadhaar Update",
        "text": "Update biometric details at Aadhaar Seva Kendra.",
        "category": "uidai",
        "source_url": "https://uidai.gov.in",
    }
    (schemes_dir / "doc_1.json").write_text(json.dumps(record), encoding="utf-8")

    from backend.offline.build_vector_db import build_unified_vector_db
    from backend.rag.embeddings import EmbeddingModelInfo

    class FakeProvider:
        @property
        def info(self):
            return EmbeddingModelInfo(provider="fake", model="fake", dimensions=3, multilingual=True)

        def embed_texts(self, texts):
            return tuple((0.1, 0.2, 0.3) for _ in texts)

    monkeypatch.setattr("backend.offline.build_vector_db.FastEmbedProvider", lambda **_: FakeProvider())

    dest_dir = tmp_path / "vector_index" / "qdrant"
    result = build_unified_vector_db(
        source_dir=refined_dir,
        dest_dir=dest_dir,
        collection_name="test_collection",
        batch_size=1,
    )

    assert result["status"] == "success"
    assert result["total_documents"] == 1
    assert result["dimensions"] == 3
    assert result["categories"]["aadhaar"] == 1
    assert result["vector_store_health"]["ready"] is True
    assert result["vector_store_health"]["points"] == 1
    assert result["index_metadata"]["documents"] == 1
    assert result["index_metadata"]["dimensions"] == 3
    assert result["index_metadata"]["embedding_model"] == "fake"
    assert (dest_dir / "govbank_index.json").is_file()


def test_build_unified_vector_db_uses_canonical_loader(tmp_path, monkeypatch):
    pytest.importorskip("qdrant_client")
    from backend.offline.build_vector_db import build_unified_vector_db
    from backend.rag.embeddings import EmbeddingModelInfo
    from backend.rag.loader import DEFAULT_MANIFEST

    class FakeProvider:
        @property
        def info(self):
            return EmbeddingModelInfo(provider="fake", model="fake", dimensions=3, multilingual=True)

        def embed_texts(self, texts):
            return tuple((0.1, 0.2, 0.3) for _ in texts)

    monkeypatch.setattr("backend.offline.build_vector_db.FastEmbedProvider", lambda **_: FakeProvider())

    dest_dir = tmp_path / "vector_index" / "qdrant"
    result = build_unified_vector_db(
        manifest_path=DEFAULT_MANIFEST,
        dest_dir=dest_dir,
        collection_name="test_canonical",
        batch_size=100,
    )

    assert result["status"] == "success"
    assert result["total_documents"] == 1074  # Must be 681, rejecting the 15 unsafe records
    assert result["categories"]["aadhaar"] == 390
    assert result["categories"]["pan"] == 242
    assert result["categories"]["civic"] == 332
    assert result["categories"]["tax"] == 110
    assert result["vector_store_health"]["points"] == 1074
    assert result["index_metadata"]["documents"] == 1074
    assert result["index_metadata"]["corpus_sha256"] == result["corpus_sha256"]

