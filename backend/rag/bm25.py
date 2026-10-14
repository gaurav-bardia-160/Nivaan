"""Small deterministic BM25 implementation for a no-dependency lexical baseline."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

TOKEN_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)
IMPORTANT_TERMS = {"pan", "aadhaar", "uidai", "epan", "e", "itr", "vid", "pvc", "kyc", "49a", "49aa"}
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
        if token.startswith("e") and len(token) > 1 and token[1:] in {"pan", "aadhaar"}:
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

    def search(self, query: str, *, top_k: int = 20, allowed_indices: set[int] | None = None) -> tuple[BM25Hit, ...]:
        terms = tokenize(query)
        if not terms or not self.docs or top_k < 1:
            return ()
        candidates = allowed_indices if allowed_indices is not None else set(range(len(self.docs)))
        scores: list[BM25Hit] = []
        for idx in candidates:
            score = 0.0
            freqs = self.term_freqs[idx]
            doc_len = self.lengths[idx]
            for term in terms:
                tf = freqs.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avg_len or 1))
                score += self.idf.get(term, 0.0) * (tf * (self.k1 + 1)) / denom
            if score > 0:
                scores.append(BM25Hit(idx, score))
        scores.sort(key=lambda hit: (-hit.score, hit.index))
        return tuple(scores[:top_k])
