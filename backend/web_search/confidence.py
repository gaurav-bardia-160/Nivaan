"""Confidence scoring — maps raw RRF retrieval scores to a normalized [0.0, 1.0] confidence value.

The confidence gate in pipeline.py uses this to decide whether to use the Qdrant/BM25 result
or fall back to live web search / honest refusal.

Multi-Factor Relevance & Confidence Gating (R2):
  Confidence = BaseScore × EntityAlignment × TermOverlap
  - BaseScore: RRF top score normalized against _RRF_HIGH_CONFIDENCE_FLOOR (0.040).
  - EntityAlignment: Enforces statutory anchor alignment (Sections 147-151, 206AA, 114AAA, 234H, etc.).
    If statutory anchors are in the query and the candidate chunk lacks support, confidence is
    penalized strictly below 0.35 (triggering CRAG or honest refusal).
  - TermOverlap: Content word containment factor preventing accidental single-word collisions
    from scoring high confidence.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("web_search.confidence")

# Empirically determined RRF score at which we consider retrieval "high confidence"
_RRF_HIGH_CONFIDENCE_FLOOR = 0.040

_CIVIC_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "what", "how", "when", "where", "which", "who", "why", "did", "does", "have",
    "has", "had", "can", "could", "should", "would", "will", "got", "get", "come",
    "came", "under", "about", "into", "over", "after", "before", "between", "out",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "than", "too", "very", "just", "now", "not", "but",
    "off", "down", "then", "once", "here", "there", "our", "your", "their", "his",
    "her", "its", "you", "they", "i", "we", "my", "me", "us",
}

_SHORT_STOPWORDS = {
    "is", "it", "in", "on", "to", "of", "at", "by", "or", "as", "be", "do",
    "if", "so", "up", "no", "an", "am", "he", "we", "me", "my", "us",
}

_INDIC_STOPWORDS = {
    # Hindi
    "क्या", "है", "हैं", "में", "का", "की", "के", "को", "से", "पर", "कैसे",
    "करें", "करना", "करो", "करूं", "करूँ", "नहीं", "नही",
    "होता", "होती", "बताएं", "कब", "कहाँ", "कौन", "क्यों",
    "कितना", "कितनी", "ने", "या", "और", "एक", "यह", "वह", "मुझे", "मेरा",
    "मेरी", "आपका", "लिए", "हो", "जाता", "जाती", "गया", "गई",
    "दो", "दें", "दे", "दिया", "लो", "लें", "लिया", "सकता", "सकती", "सकते",
    "रहा", "रही", "रहे", "चाहिए", "बारे", "कुछ", "सब", "तुम", "तुम्हें",
    "हम", "हमें", "हमारा", "इस", "उस", "अपना", "अपनी", "अपने",
    # Gujarati
    "શું", "છે", "માં", "ના", "ની", "નું", "ને", "થી", "પર", "કેવી", "રીતે",
    "કરવું", "કરો", "કરું", "નહીં", "નહી",
    "માટે", "મને", "મારું", "અને", "એક", "આ", "તે",
    "ક્યારે", "ક્યાં", "કોણ", "શા", "થાય", "ગયું",
}

# Indic tokens that must match exact word or explicit card compound (prevents "પાન" matching "પાનું")
_INDIC_EXACT_CIVIC_CONCEPTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("पैन", "पॅन", "પૅન", "પાન"), ("pan", "pancard", "epan")),
    (("पता", "पते"), ("address",)),
)

# Maps Indic civic root prefixes/tokens to canonical English corpus tokens
_INDIC_CIVIC_CONCEPTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("आधार", "આધાર"), ("aadhaar", "aadhar", "uidai")),
    (("पासपोर्ट", "પાસપોર્ટ"), ("passport", "psk")),
    (("સરનામ",), ("address",)),
    (("बदल", "अपडेट", "બદલ", "અપડેટ"), ("update", "change", "correction")),
    (("कार्ड", "કાર્ડ"), ("card",)),
    (("डाउनलोड", "ડાઉનલોડ"), ("download",)),
    (("आयकर", "ટેક્સ", "ઇન્કમ"), ("tax", "income", "itr")),
    (("रिटर्न", "રિટર્ન"), ("return", "returns", "itr")),
    (("दाखिल", "फाइल", "ફાઇલ", "દાખલ"), ("file", "filing", "filed", "submit")),
    (("बैंक", "खात", "બેંક", "ખાત"), ("bank", "account")),
    (("वोटर", "मतदाता", "મતદાર"), ("voter", "epic")),
    (("ड्राइविंग", "लाइसेंस", "ડ્રાઇવિંગ", "લાઇસન્સ"), ("driving", "license", "licence")),
    (("राशन", "રેશન"), ("ration",)),
    (("पेंशन", "પેન્શન"), ("pension",)),
    (("पीएफ", "ईपीएफ", "ઇપીએફ"), ("epf", "epfo", "pf")),
    (("किसान", "કિસાન"), ("kisan", "pmkisan")),
    (("शिकायत", "ફરિયાદ"), ("grievance", "complaint")),
    (("रिफंड", "રિફંડ"), ("refund",)),
    (("आवेदन", "અરજી"), ("apply", "application")),
    (("लिंक", "લિંક"), ("link", "linking")),
)

_RETRIEVER_BOOST_KEYS = (
    "exact_statutory_boost",
    "symptom_boost",
    "exact_acronym_boost",
    "troubleshooting_boost",
    "fir_procedure_boost",
    "epf_withdrawal_boost",
    "cheque_bounce_boost",
)

_EXPLICIT_SYSTEM_FORM_PATTERNS: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    ("inc-29", re.compile(r"(?<![a-z0-9])inc[-\s]?29(?![a-z0-9])", re.I), ("inc-29", "inc 29", "inc29")),
    ("inc-32", re.compile(r"(?<![a-z0-9])inc[-\s]?32(?![a-z0-9])", re.I), ("inc-32", "inc 32", "inc32")),
    ("spice+", re.compile(r"(?<![a-z0-9])spice\s*\+", re.I), ("spice+", "spice +", "spice plus")),
    ("part a", re.compile(r"\bpart[-\s]+a\b", re.I), ("part a", "part-a")),
    ("rule 8a", re.compile(r"\brule\s*8a\b", re.I), ("rule 8a", "rule8a")),
    ("mopng", re.compile(r"\bmopng\b", re.I), ("mopng",)),
    ("lpg", re.compile(r"\blpg\b", re.I), ("lpg",)),
    ("pahal", re.compile(r"\bpahal\b", re.I), ("pahal",)),
    ("dbtl", re.compile(r"\bdbtl\b", re.I), ("dbtl",)),
    ("nsp", re.compile(r"\bnsp\b", re.I), ("nsp",)),
    ("defective by institute", re.compile(r"\bdefective\s+by\s+institute\b", re.I), ("defective by institute",)),
)


def _normalize_provision_anchor(raw: str) -> str:
    """Normalize raw statutory entity reference to canonical base provision."""
    cleaned = re.sub(r"[\s\-_]", "", raw.lower())
    # Strip subsection e.g. 148a(b) -> 148a, 149(1)(a) -> 149, 119(2)(b) -> 119(2)(b)
    # For reassessment 148a(b) -> 148a
    if cleaned.startswith("148a"):
        return "148a"
    if cleaned.startswith("149"):
        return "149"
    if cleaned.startswith("147"):
        return "147"
    if cleaned.startswith("151"):
        return "151"
    if cleaned.startswith("206aa"):
        return "206aa"
    if cleaned.startswith("114aaa"):
        return "114aaa"
    if cleaned.startswith("234h"):
        return "234h"
    if cleaned.startswith("139(9)") or cleaned.startswith("139"):
        return "139(9)"
    if cleaned.startswith("119(2)(b)") or cleaned.startswith("119"):
        return "119(2)(b)"
    return cleaned


def extract_statutory_anchors(text: str) -> set[str]:
    """Extract canonical statutory anchors (sections, rules, circulars) from query text."""
    if not text:
        return set()

    anchors = set()
    cleaned = text.lower()

    # 1. Section patterns: "section 148a(b)", "sec. 149", "section 206aa", "section 999xyz"
    sec_matches = re.findall(
        r"\b(?:section|sec\.?|u/s)\s*([0-9]+[a-z]*(?:\([a-z0-9]+\))*)",
        cleaned,
        flags=re.IGNORECASE,
    )
    for m in sec_matches:
        anchors.add(_normalize_provision_anchor(m))

    # 2. Rule patterns: "rule 114aaa"
    rule_matches = re.findall(
        r"\brule\s*([0-9]+[a-z]*(?:\([a-z0-9]+\))*)",
        cleaned,
        flags=re.IGNORECASE,
    )
    for m in rule_matches:
        anchors.add(_normalize_provision_anchor(m))

    # 3. Circular patterns: "circular 03/2023", "circular no. 3 of 2023"
    cir_matches = re.findall(
        r"\bcircular\s*(?:no\.?\s*)?([0-9]+(?:/[0-9]+)?)",
        cleaned,
        flags=re.IGNORECASE,
    )
    for m in cir_matches:
        anchors.add(_normalize_provision_anchor(m))

    # 4. Standalone statutory section tokens if present
    standalone_codes = [
        "148a(b)", "148a", "149", "147", "151",
        "206aa", "114aaa", "234h", "139(9)", "119(2)(b)",
    ]
    for code in standalone_codes:
        pattern = r"(?<![a-z0-9])" + re.escape(code) + r"(?![a-z0-9])"
        if re.search(pattern, cleaned):
            anchors.add(_normalize_provision_anchor(code))

    return anchors


def _build_chunk_text(doc: Any) -> str:
    """Extract comprehensive searchable string from a RagDocument or mock."""
    parts = []
    if hasattr(doc, "id") and isinstance(doc.id, str):
        parts.append(doc.id)
    if hasattr(doc, "title") and isinstance(doc.title, str):
        parts.append(doc.title)
    if hasattr(doc, "section") and isinstance(doc.section, str):
        parts.append(doc.section)
    if hasattr(doc, "text") and isinstance(doc.text, str):
        parts.append(doc.text)

    tags = getattr(doc, "tags", ()) or getattr(doc, "retrieval_tags", ()) or ()
    if isinstance(tags, (list, tuple, set)):
        parts.extend([str(t) for t in tags])

    sources = getattr(doc, "sources", ()) or ()
    if isinstance(sources, (list, tuple)):
        for s in sources:
            if hasattr(s, "title") and isinstance(s.title, str):
                parts.append(s.title)
            if hasattr(s, "section") and isinstance(s.section, str):
                parts.append(s.section)

    return " ".join(parts).lower()


def _is_anchor_in_chunk(anchor: str, chunk_blob: str) -> bool:
    """Verify if a normalized statutory anchor is supported in candidate chunk text."""
    if anchor == "148a":
        return bool(
            re.search(r"(?<![a-z0-9])148a\b", chunk_blob)
            or re.search(r"(?<![a-z0-9])148-a\b", chunk_blob)
            or "148a" in chunk_blob
        )
    if anchor in ("149", "147", "151"):
        return bool(re.search(r"(?<![a-z0-9])" + anchor + r"(?![a-z0-9])", chunk_blob))
    if anchor == "206aa":
        return "206aa" in chunk_blob or "206 aa" in chunk_blob
    if anchor == "114aaa":
        return "114aaa" in chunk_blob or "114 aaa" in chunk_blob
    if anchor == "234h":
        return "234h" in chunk_blob or "234 h" in chunk_blob
    if anchor == "139(9)":
        return "139(9)" in chunk_blob or "139 (9)" in chunk_blob or "139" in chunk_blob
    if anchor == "119(2)(b)":
        return "119(2)(b)" in chunk_blob or "119 (2)(b)" in chunk_blob or "119" in chunk_blob
    if anchor in ("03/2023", "3/2023"):
        return any(
            t in chunk_blob
            for t in ("03/2023", "3/2023", "circular 03", "circular no. 3", "circular no. 03")
        )
    # Generic regex boundary match for arbitrary statutory tokens (e.g. 999xyz)
    pattern = r"(?<![a-z0-9])" + re.escape(anchor) + r"(?![a-z0-9])"
    return bool(re.search(pattern, chunk_blob))


def _indic_token_matches_chunk(
    token: str,
    chunk_indic_words: set[str],
    chunk_ascii_words: set[str],
    *,
    allow_pata: bool = True,
    allow_kar: bool = True,
) -> bool:
    """Return True if an Indic query token matches native chunk text or a canonical civic concept."""
    if token in ("पता", "पते") and not allow_pata:
        return False
    if token == "कर":
        if not allow_kar:
            return False
        return token in chunk_indic_words or any(w in chunk_ascii_words for w in ("tax", "income", "itr"))
    if token in chunk_indic_words:
        return True
    for exact_tokens, en_terms in _INDIC_EXACT_CIVIC_CONCEPTS:
        if any(
            token == t or token.startswith(f"{t}कार्ड") or token.startswith(f"{t}કાર્ડ")
            for t in exact_tokens
        ):
            if any(en in chunk_ascii_words for en in en_terms):
                return True
    for prefixes, en_terms in _INDIC_CIVIC_CONCEPTS:
        if any(token.startswith(p) for p in prefixes):
            if any(en in chunk_ascii_words for en in en_terms):
                return True
    return False


def _is_civic_indic_token(token: str) -> bool:
    """Return True if an Indic token maps to a known civic/tax/identity concept."""
    if token == "कर":
        return True
    for exact_tokens, _ in _INDIC_EXACT_CIVIC_CONCEPTS:
        if any(
            token == t or token.startswith(f"{t}कार्ड") or token.startswith(f"{t}કાર્ડ")
            for t in exact_tokens
        ):
            return True
    for prefixes, _ in _INDIC_CIVIC_CONCEPTS:
        if any(token.startswith(p) for p in prefixes):
            return True
    return False


def _extract_query_terms(query: str) -> tuple[set[str], set[str]]:
    lowered_q = query.lower()
    q_words = {
        w for w in re.findall(r"\b[a-z0-9_-]{3,}\b", lowered_q)
        if w not in _CIVIC_STOPWORDS and not w.isdigit()
    }
    if not q_words:
        q_words = {
            w for w in re.findall(r"\b[a-z0-9_-]{2,}\b", lowered_q)
            if w not in _CIVIC_STOPWORDS and w not in _SHORT_STOPWORDS and not w.isdigit()
        }
    indic_tokens = {
        w for w in re.findall(r"[\u0900-\u097F\u0A80-\u0AFF]{2,}", query)
        if w not in _INDIC_STOPWORDS
    }
    return q_words, indic_tokens


def _compute_term_overlap_details(query: str, chunk_blob: str) -> tuple[float, float]:
    """Return (scaled_term_overlap, raw_match_ratio) between query and chunk."""
    lowered_q = query.lower()
    lowered_chunk = chunk_blob.lower()
    q_words = {
        w for w in re.findall(r"\b[a-z0-9_-]{3,}\b", lowered_q)
        if w not in _CIVIC_STOPWORDS and not w.isdigit()
    }
    if q_words:
        chunk_words = set(re.findall(r"\b[a-z0-9_-]{3,}\b", lowered_chunk))
    else:
        q_words = {
            w for w in re.findall(r"\b[a-z0-9_-]{2,}\b", lowered_q)
            if w not in _CIVIC_STOPWORDS and w not in _SHORT_STOPWORDS and not w.isdigit()
        }
        chunk_words = set(re.findall(r"\b[a-z0-9_-]{2,}\b", lowered_chunk))

    indic_tokens = {
        w for w in re.findall(r"[\u0900-\u097F\u0A80-\u0AFF]{2,}", query)
        if w not in _INDIC_STOPWORDS
    }
    total_terms = len(q_words) + len(indic_tokens)
    if total_terms == 0:
        return 0.0, 0.0

    ascii_matches = len(q_words & chunk_words) if q_words else 0
    indic_matches = 0
    if indic_tokens:
        chunk_indic_words = set(re.findall(r"[\u0900-\u097F\u0A80-\u0AFF]{2,}", lowered_chunk))
        chunk_ascii_words = set(re.findall(r"[a-z0-9]{2,}", lowered_chunk))
        allow_pata = (
            total_terms >= 2
            and (
                not re.search(r"(?:क्या\s+पता|पता\s+(?:ही\s+)?नहीं|नहीं\s+(?:ही\s+)?पता|पता\s+है)", query)
                or bool(re.search(
                    r"(?:आधार|कार्ड|पैन|पासपोर्ट|वोटर|राशन|बैंक|अपडेट|बदल|aadhaar|pan|passport|voter|ration|card|address|update|change)",
                    lowered_q,
                ))
            )
        )
        allow_kar = (
            total_terms >= 2
            and not re.search(
                r"(?:^|\s)कर\s+(?:दो|दें|दे|दिया|दूं|दूँ|देना|देंगे|लो|लें|लिया|लेना|लेंगे|सकते|सकता|सकती|सकें|सकूं|रहा|रही|रहे|चुका|चुकी|चुके|जा|पा|पाएं|पाऊं|पाते)(?:\s|$)",
                query,
            )
        )
        indic_matches = sum(
            1 for t in indic_tokens
            if _indic_token_matches_chunk(
                t,
                chunk_indic_words,
                chunk_ascii_words,
                allow_pata=allow_pata,
                allow_kar=allow_kar,
            )
        )

    matches = ascii_matches + indic_matches
    raw_ratio = matches / total_terms
    if total_terms >= 2 and matches <= 1:
        return raw_ratio, raw_ratio
    target = max(total_terms * 0.30, 1.0)
    return min(matches / target, 1.0), raw_ratio


def compute_term_overlap(query: str, chunk_blob: str) -> float:
    """Compute lexical content word overlap ratio between query and chunk."""
    overlap, _ = _compute_term_overlap_details(query, chunk_blob)
    return overlap


def compute_rag_confidence(
    rag_result: Any,
    query: str | None = None,
) -> float:
    """Compute a multi-factor normalized confidence score in [0.0, 1.0].

    Confidence = BaseScore × EntityAlignment × TermOverlap

    Args:
        rag_result: A RetrievalResult object (from backend.rag.retriever) or None.
        query: Optional user inquiry string to enforce statutory entity alignment
               and lexical overlap. If omitted, returns backward-compatible base score.

    Returns:
        Float in [0.0, 1.0]. Returns 0.0 if rag_result is None or has no hits.
        Penalizes confidence strictly below 0.35 if query statutory anchors lack support.
    """
    if rag_result is None:
        return 0.0

    hits = getattr(rag_result, "hits", None)
    if not hits:
        return 0.0

    top_score: float = 0.0
    try:
        top_score = float(hits[0].score)
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0.0

    if top_score <= 0.0:
        return 0.0

    base_confidence = min(top_score / _RRF_HIGH_CONFIDENCE_FLOOR, 1.0)

    # Backward compatibility: If query is omitted or empty, return base score
    if query is None or not str(query).strip():
        logger.debug("RAG confidence (unconditioned): top_score=%.4f → %.3f", top_score, base_confidence)
        return base_confidence

    doc = getattr(hits[0], "document", None)
    if doc is None:
        return base_confidence

    query_str = str(query).strip()
    chunk_blob = _build_chunk_text(doc)

    # 1. Statutory Entity Alignment
    statutory_anchors = extract_statutory_anchors(query_str)
    entity_alignment = 1.0
    matched_anchors: set[str] = set()

    if statutory_anchors:
        matched_anchors = {
            a for a in statutory_anchors
            if _is_anchor_in_chunk(a, chunk_blob)
        }
        if not matched_anchors:
            # Severe statutory mismatch penalty: ensures confidence < 0.35
            entity_alignment = 0.15
        else:
            entity_alignment = len(matched_anchors) / len(statutory_anchors)

    # 2. Lexical / Term Overlap
    term_overlap, raw_match_ratio = _compute_term_overlap_details(query_str, chunk_blob)

    # Multi-factor score
    confidence = base_confidence * entity_alignment * term_overlap

    # Hard ceiling for statutory mismatch: strictly below 0.35
    if statutory_anchors and not matched_anchors:
        confidence = min(confidence, 0.25)

    # Explicit portal / scheme / form token mismatch gating
    missing_explicit_tokens = [
        label
        for label, pat, aliases in _EXPLICIT_SYSTEM_FORM_PATTERNS
        if pat.search(query_str) and not any(alias in chunk_blob for alias in aliases)
    ]
    if missing_explicit_tokens:
        confidence = min(confidence, 0.25)

    # Weak semantic vector hit with zero retriever boosts and partial lexical overlap
    signals = getattr(hits[0], "signals", None) or {}
    has_retriever_boost = any(
        float(signals.get(k, 0.0) or 0.0) > 0.0
        for k in _RETRIEVER_BOOST_KEYS
    )
    if "vector_score" in signals:
        try:
            vec_score = float(signals["vector_score"])
        except (TypeError, ValueError):
            vec_score = 1.0
        if vec_score < 0.38 and not has_retriever_boost and raw_match_ratio < 0.75:
            confidence = min(confidence, 0.30)
    elif "bm25_score" in signals and not has_retriever_boost:
        try:
            bm25_score = float(signals["bm25_score"])
        except (TypeError, ValueError):
            bm25_score = 999.0
        q_words, indic_tokens = _extract_query_terms(query_str)
        total_terms = len(q_words) + len(indic_tokens)
        tag_overlap = float(signals.get("tag_overlap", 0.0) or 0.0)
        single_non_civic_indic = (
            total_terms == 1
            and len(indic_tokens) == 1
            and not _is_civic_indic_token(next(iter(indic_tokens)))
        )
        if base_confidence < 0.55 and (
            (bm25_score < 14.0 and (raw_match_ratio <= 0.50 or (total_terms == 1 and tag_overlap <= 0.0)))
            or (single_non_civic_indic and tag_overlap <= 0.0)
        ):
            confidence = min(confidence, 0.30)

    confidence = max(0.0, min(confidence, 1.0))
    logger.debug(
        "RAG confidence: base=%.3f, entity_align=%.2f, term_overlap=%.2f → final=%.3f",
        base_confidence, entity_alignment, term_overlap, confidence,
    )
    return confidence


__all__ = ["compute_rag_confidence", "extract_statutory_anchors", "compute_term_overlap"]
