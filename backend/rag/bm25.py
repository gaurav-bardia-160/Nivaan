"""Small deterministic BM25 implementation for a no-dependency lexical baseline."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

TOKEN_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)
IMPORTANT_TERMS = {
    # Identity
    "pan", "aadhaar", "uidai", "epan", "e", "itr", "vid", "pvc", "kyc", "49a", "49aa",
    "digilocker", "epic", "eci", "nvsp", "passport", "psk",
    # Transport
    "fastag", "nhai", "ihmcl", "vahan", "sarathi", "parivahan", "rc", "chassis", "challan", "echallan", "dl", "rto",
    # Education
    "cbse", "marksheet", "nios", "icse",
    # Banking, Schemes & Consumer
    "rbi", "kcc", "fir", "edaakhil", "dcdrc", "ncdrc", "nalsa", "uan", "epfo", "epf"
}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for", "from",
    "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "the", "this",
    "to", "what", "with", "you", "your", "please", "need", "want",
}


def tokenize(text: str) -> tuple[str, ...]:
    raw = [token.lower() for token in TOKEN_RE.findall(text)]
    expanded: list[str] = []
    for token in raw:
        if token == "e" or token in STOPWORDS and token not in IMPORTANT_TERMS:
            continue
        expanded.append(token)
        if token.startswith("e") and len(token) > 1 and token[1:] in {"pan", "aadhaar", "challan", "epic"}:
            expanded.append(token[1:])
    return tuple(expanded)


@dataclass(frozen=True)
class BM25Hit:
    index: int
    score: float


class BM25Index:
    def __init__(self, texts: Iterable[str], *, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = [tokenize(text) for text in texts]
        self.lengths = [len(doc) for doc in self.docs]
        self.avg_len = sum(self.lengths) / len(self.lengths) if self.lengths else 0
        self.term_freqs = [Counter(doc) for doc in self.docs]
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(set(doc))
        count = len(self.docs)
        self.idf = {term: math.log(1 + (count - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def search(self, query: str, *, top_k: int = 10, allowed_indices: set[int] | None = None) -> tuple[BM25Hit, ...]:
        q_terms = [t for t in tokenize(query) if t in self.idf]
        if not q_terms:
            return ()
        candidates = range(len(self.docs)) if allowed_indices is None else allowed_indices
        hits: list[BM25Hit] = []
        for idx in candidates:
            score = 0.0
            tf = self.term_freqs[idx]
            doc_len = self.lengths[idx]
            denom_const = self.k1 * (1 - self.b + self.b * (doc_len / self.avg_len if self.avg_len else 1))
            for term in q_terms:
                freq = tf.get(term, 0)
                if not freq:
                    continue
                score += self.idf[term] * (freq * (self.k1 + 1)) / (freq + denom_const)
            if score > 0:
                hits.append(BM25Hit(index=idx, score=score))
        hits.sort(key=lambda h: -h.score)
        return tuple(hits[:top_k])


__all__ = ["BM25Hit", "BM25Index", "tokenize"]
