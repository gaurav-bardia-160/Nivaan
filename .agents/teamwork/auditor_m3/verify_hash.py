import sys
import os
sys.path.insert(0, os.path.abspath("."))

from backend.rag.loader import load_corpus, DEFAULT_MANIFEST
import json

res = load_corpus(DEFAULT_MANIFEST)
h = res.report.corpus_sha256
print("load_corpus computed hash:", h)
with open("backend/data/vector_index/qdrant/govbank_index.json", "r", encoding="utf-8") as f:
    meta = json.load(f)
print("index metadata hash:       ", meta["corpus_sha256"])
print("index metadata documents:  ", meta["documents"])
print("load_corpus documents:     ", len(res.documents))
assert h == meta["corpus_sha256"], f"Hash mismatch: {h} != {meta['corpus_sha256']}"
print("VERIFICATION SUCCESS: Corpus SHA-256 matches Qdrant index metadata exactly.")
