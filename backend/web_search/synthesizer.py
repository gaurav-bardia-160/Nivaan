"""Web synthesizer — LLM-grounded answer synthesis from ephemeral web page text.

Phase 1 only: The fetched page text is used to generate an answer in memory.
It is NEVER written to Qdrant here. The ETL pipeline handles ingestion offline.

The synthesized answer is clearly marked as web-sourced (confidence="low",
disclaimer notes it's from live web search, not the verified civic corpus).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date

import httpx

from backend.schemas import Answer, Citation, Step, _normalize_doc_item
from backend.web_search.fetcher import is_navigation_or_boilerplate_text

logger = logging.getLogger("web_search.synthesizer")

_OLLAMA_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
_OLLAMA_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:3b").strip() or "qwen2.5:3b"
_LLM_TIMEOUT = None

DISCRIMINATOR_FAILURE_PHRASE = "Live search failed to extract the procedural text from the official portal."

_WEB_SYNTHESIS_SYSTEM = f"""\
You are Nivaan, an expert Indian Civic AI. Read the provided reference text and the user's query. Answer the query in natural language, applying conditional logic or date-math if required by the user's specific scenario. NEVER copy-paste the reference text verbatim. Write a clear, conversational, and step-by-step response based ONLY on the provided reference.

STRICT DISCRIMINATOR AND SYNTHESIS RULES:
1. Evaluate the scraped text first. If it primarily consists of website navigation menus, homepage popups, or irrelevant links (e.g., 'Skip to navigation', 'Screen Reader Access', news banners, copyright notices), and lacks specific procedural steps to answer the user's prompt, DO NOT output a summary. Instead, output exactly:
   {{"summary": "{DISCRIMINATOR_FAILURE_PHRASE}", "steps": [], "documents_needed": []}}
2. If specific procedural content IS present to answer the question:
   - Answer ONLY from the provided official web page content. Do NOT invent steps or procedures not present in the page.
   - Return valid JSON: "summary" (concise, 2-4 sentences explaining the procedure), "steps" (list of objects with "title" and "detail"), and "documents_needed" (list of strings).
   - MANDATORY SCOPE & CONDITIONALITY FIDELITY: When stating legal rules, prohibitions, or exemptions, preserve all statutory scope qualifiers (borrower type: individual vs corporate vs MSE; rate type: floating vs fixed rate). NEVER compress conditional rules into blanket absolute statements.
   - DOCUMENTS NEEDED FORMATTING: The "documents_needed" key MUST be a simple list of clean document title strings. Never return dictionary objects, JSON blobs, or URLs inside "documents_needed".
3. ZERO external commercial sites. ZERO invented URLs.
"""


def _call_ollama(system: str, prompt: str, *, timeout: float | None = None) -> str | None:
    """Call local Ollama model using active configuration."""
    base_url = os.getenv("LOCAL_LLM_BASE_URL", _OLLAMA_BASE_URL).rstrip("/")
    model = os.getenv("LOCAL_LLM_MODEL", _OLLAMA_MODEL).strip() or _OLLAMA_MODEL
    try:
        num_ctx = min(max(int(os.getenv("LOCAL_LLM_NUM_CTX", "4096")), 1024), 4096)
    except ValueError:
        num_ctx = 4096
    try:
        num_predict = min(max(int(os.getenv("LOCAL_LLM_NUM_PREDICT", "512")), 128), 700)
    except ValueError:
        num_predict = 512

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.1,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "num_thread": min(os.cpu_count() or 4, 4),
        },
    }
    try:
        resp = httpx.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        raw = body.get("message", {}).get("content", "").strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        return raw or None
    except Exception as exc:
        logger.warning("Ollama call in web synthesizer fell back to extraction: %s", exc)
        return None


def _extract_extractive_answer(page_text: str, query: str) -> tuple[str, list[dict], list[str]]:
    """Extract high-accuracy summary and steps directly from official government page text."""
    raw_lines = [l.strip() for l in page_text.splitlines() if len(l.strip()) > 10]
    lines = [
        l for l in raw_lines
        if l.count("|") < 2 and not re.search(r"\|\s*[-:]{3,}\s*\|", l) and not re.match(r"^[-=_|*]{3,}$", l)
    ]
    sentence_candidates = []
    for line in lines:
        for s in re.split(r"(?<=[.!?])\s+", line):
            if (
                len(s.strip()) > 15
                and s.count("|") < 2
                and not re.search(r"\b(?:format\s*:\s*pdf|pdfsize|filesize)\b", s, re.I)
            ):
                sentence_candidates.append(s.strip())

    query_words = set(re.findall(r"\b\w+\b", query.lower())) - {
        "how", "to", "the", "in", "is", "for", "a", "an", "what", "can", "i", "do", "we", "my", "of", "and", "or",
    }

    scored_sentences = []
    for s in sentence_candidates:
        s_words = set(re.findall(r"\b\w+\b", s.lower()))
        score = len(query_words & s_words)
        if score > 0:
            scored_sentences.append((score, s))

    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    top_candidates = set(s for _, s in scored_sentences[:6])
    # Maintain natural chronological reading order as they appear in the official document
    best_sentences = []
    for s in sentence_candidates:
        if s in top_candidates and s not in best_sentences:
            best_sentences.append(s)
            if len(best_sentences) >= 3:
                break

    steps: list[dict] = []
    step_patterns = [r"^[a-z0-9][\.\)]\s+", r"^step\s*\d+[:\-]?\s*"]
    step_verbs = (
        "visit ", "enter ", "click ", "select ", "submit ", "apply ", "go to ", "login ", "check ",
        "contact ", "call ", "dial ", "file ", "lodge ", "raise ", "register ", "open ", "provide ",
        "verify ", "upload ", "download ", "pay ", "ensure ", "forward ", "write to ", "mail to "
    )
    raw_step_candidates = []
    for s in sentence_candidates:
        is_step = any(re.match(p, s, re.I) for p in step_patterns) or any(
            s.lower().startswith(v) for v in step_verbs
        )
        if is_step and len(s) > 15:
            s_clean = s.lower()
            s_score = sum(1 for w in query_words if w in s_clean)
            raw_step_candidates.append((s_score, s))

    if any(score > 0 for score, _ in raw_step_candidates):
        filtered = [s for score, s in raw_step_candidates if score > 0]
        if len(filtered) < 3:
            filtered.extend([s for score, s in raw_step_candidates if score == 0])
    else:
        filtered = [s for _, s in raw_step_candidates]

    for s in filtered:
        if s not in [st["detail"] for st in steps]:
            clean_text = re.sub(r"^[a-z0-9][\.\)]\s+", "", s, flags=re.I).strip()
            clean_text = re.sub(r"\s+[b-z0-9][\.\)]\s*$", "", clean_text, flags=re.I).strip()
            clean_title = " ".join(clean_text.split()[:7])
            clean_title = re.sub(r"\s+[b-z0-9][\.\)]\s*$", "", clean_title, flags=re.I).strip()
            steps.append({"title": clean_title[:80], "detail": clean_text[:300]})
            if len(steps) >= 5:
                break

    docs: list[str] = []
    doc_keywords = ("aadhaar", "pan", "form", "certificate", "chassis", "challan", "rc", "receipt", "passbook")
    for s in sentence_candidates:
        if any(dk in s.lower() for dk in doc_keywords) and any(kw in s.lower() for kw in ("required", "needed", "attach", "upload", "submit", "bring")):
            docs.append(s[:100])
            if len(docs) >= 3:
                break

    # Filter out news ticker items ending in "Read More" or starting with "News:" or "Notification"
    clean_best = []
    for s in best_sentences:
        if re.search(r"\bread more\b", s, re.I):
            continue
        if s.lower().startswith(("news:", "jhansi news", "notification", "advisory")):
            continue
        clean_best.append(s)
    best_sentences = clean_best

    if is_navigation_or_boilerplate_text(page_text):
        return DISCRIMINATOR_FAILURE_PHRASE, [], []

    summary = " ".join(best_sentences) if best_sentences else (lines[0] if lines else "")
    summary = re.sub(r"^(?:and|or|but|then|also)\s+", "", summary.strip(), flags=re.I)
    if summary:
        summary = summary[0].upper() + summary[1:]

    if not steps and not best_sentences:
        return DISCRIMINATOR_FAILURE_PHRASE, [], []

    # If no steps were extracted and the summary lacks topical overlap with the question, reject
    query_key_terms = set(re.findall(r"\b\w{3,}\b", query.lower())) - {
        "how", "the", "for", "what", "can", "you", "tell", "show", "help", "with", "from", "portal", "website", "online", "official",
    }
    summary_words = set(re.findall(r"\b\w{3,}\b", summary.lower()))
    if not steps and not (query_key_terms & summary_words):
        return DISCRIMINATOR_FAILURE_PHRASE, [], []

    return summary[:600], steps, docs


def _select_focused_passages(page_text: str, query: str, max_chars: int = 1200) -> str:
    """Select the most relevant paragraphs from the page for the LLM context."""
    raw_lines = [l.strip() for l in page_text.splitlines() if len(l.strip()) > 10]
    lines = [l for l in raw_lines if l.count("|") < 2 and not re.search(r"\|\s*[-:]{3,}\s*\|", l)]
    query_words = set(re.findall(r"\b\w+\b", query.lower())) - {
        "how", "to", "the", "in", "is", "for", "a", "an", "what", "can", "i", "do", "we", "my",
    }
    scored = []
    for i in range(0, len(lines), 2):
        block = " ".join(lines[i : i + 3])
        score = len(query_words & set(re.findall(r"\b\w+\b", block.lower())))
        scored.append((score, block))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    total = 0
    for _, b in scored:
        if total + len(b) > max_chars:
            break
        selected.append(b)
        total += len(b)
        if len(selected) >= 3:
            break
    return "\n\n".join(selected) if selected else page_text[:max_chars]


def _parse_llm_response(raw: str) -> tuple[str, list[dict], list[str]]:
    """Parse LLM JSON response into (summary, steps, documents_needed)."""
    # Strip markdown code fences if present
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    summary = ""
    steps: list[dict] = []
    docs: list[str] = []

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            summary = str(data.get("summary", "")).strip()
            raw_steps = data.get("steps", [])
            if isinstance(raw_steps, list):
                steps = [
                    {"title": str(s.get("title", "")).strip(), "detail": str(s.get("detail", "")).strip()}
                    for s in raw_steps
                    if isinstance(s, dict) and s.get("title") and s.get("detail")
                ]
            raw_docs = data.get("documents_needed", [])
            if isinstance(raw_docs, list):
                docs = [_normalize_doc_item(d) for d in raw_docs]
                docs = [d for d in docs if d]
    except (json.JSONDecodeError, ValueError):
        # Fallback: treat the whole text as the summary, stripping trailing key boilerplate
        if cleaned and not cleaned.startswith("{"):
            cleaned_prose = re.split(r"\n\s*(?:documents_needed|steps)\s*:", cleaned, maxsplit=1, flags=re.I)[0]
            summary = cleaned_prose[:1000].strip()

    if not summary:
        # Last resort: extract just summary field with regex
        m = re.search(r'"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned)
        if m:
            try:
                summary = m.group(1).encode().decode("unicode_escape", errors="ignore").strip()
            except Exception:
                summary = m.group(1).strip()

    return summary, steps, docs


def synthesize_from_web(
    query: str,
    page_text: str,
    url: str,
    *,
    memory: tuple = (),
) -> Answer:
    """Synthesize a civic answer from ephemeral web page text using the local LLM.

    Args:
        query: The user's original query (PII masked).
        page_text: Clean plaintext extracted from the official government page.
        url: Source URL (used as citation and source_url in the answer).
        memory: Optional tuple of MemoryTurn objects for conversational context.

    Returns:
        An Answer object with confidence="low" and a web-search disclaimer.
        The answer is clearly marked as from live web search, not the verified corpus.
    """
    # Build conversational history context
    history_lines: list[str] = []
    for turn in (memory or [])[-5:]:
        if hasattr(turn, "user_text") and turn.user_text:
            history_lines.append(f"Citizen: {turn.user_text}")
        asst = getattr(turn, "assistant_text", None) or getattr(turn, "answer_title", None)
        if asst:
            history_lines.append(f"Nivaan: {asst}")
    history_block = "\n".join(history_lines) or "No prior context."

    today = date.today()
    from urllib.parse import urlparse
    domain_netloc = urlparse(url).netloc.lower().replace("www.", "")

    # Early rejection if page text is pure navigation or boilerplate
    if is_navigation_or_boilerplate_text(page_text):
        citation = Citation(
            title="Official Government Portal — Live Search Result",
            url=url,  # type: ignore[arg-type]
            excerpt=page_text[:350].strip() or "Official government page content.",
            reported_last_verified=today,
            factual_verification="unverified",
        )
        return Answer(
            entry_id=None,
            title=f"Official Civic Portal ({domain_netloc})",
            summary=f"{DISCRIMINATOR_FAILURE_PHRASE} Please visit the official portal directly at {url} to view the statutory procedure.",
            documents_needed=[],
            steps=[],
            warnings=[],
            source_url=url,  # type: ignore[arg-type]
            last_verified=today,
            confidence="low",
            masked_items=[],
            citations=[citation],
            disclaimer=(
                f"⚠️ This answer was retrieved live from the official government portal ({domain_netloc}). "
                "Please verify the information directly on the official portal before taking action."
            ),
        )

    # First, compute high-accuracy extractive answer directly from official page text
    ext_summary, ext_steps, ext_docs = _extract_extractive_answer(page_text, query)

    # Use focused passage excerpt for fast LLM inference
    page_excerpt = _select_focused_passages(page_text, query, max_chars=1200)

    prompt = (
        f"--- Conversation Context ---\n{history_block}\n\n"
        f"--- Citizen Question ---\n{query[:800]}\n\n"
        f"--- Official Government Web Page Content ---\nSource: {url}\n\n{page_excerpt}\n\n"
        "Instructions: Answer the citizen's question based ONLY on the official page content above."
    )

    raw_response = _call_ollama(_WEB_SYNTHESIS_SYSTEM, prompt, timeout=_LLM_TIMEOUT)

    summary = ""
    steps_data = []
    docs = []
    if raw_response:
        summary, steps_data, docs = _parse_llm_response(raw_response)

    refusal_phrases = (
        "does not contain", "could not find", "cannot find", "no specific instructions",
        "not found", "does not provide", "not mention", "no information", "not explicitly mention",
        "unable to find", "failed to extract", "no front page content", "read more",
    )
    has_refusal = any(rp in (summary or "").lower() for rp in refusal_phrases)

    # Check if LLM explicitly rejected the content via the discriminator rule:
    llm_rejected = DISCRIMINATOR_FAILURE_PHRASE.lower() in (summary or "").lower() or has_refusal

    if llm_rejected:
        summary = DISCRIMINATOR_FAILURE_PHRASE
        steps_data = []
        docs = []
    else:
        # If LLM timed out or returned empty, seamlessly use the high-accuracy extractive extraction
        if not summary or len(summary) < 20:
            summary = ext_summary
        if not steps_data and ext_steps:
            steps_data = ext_steps
        if not docs and ext_docs:
            docs = ext_docs

    query_key_terms = set(re.findall(r"\b\w{3,}\b", query.lower())) - {
        "how", "the", "for", "what", "can", "you", "tell", "show", "help", "with", "from", "portal", "website", "online", "official",
    }
    summary_words = set(re.findall(r"\b\w{3,}\b", (summary or "").lower()))
    has_topical_overlap = bool(query_key_terms & summary_words)

    is_rejected = (
        DISCRIMINATOR_FAILURE_PHRASE.lower() in (summary or "").lower()
        or any(rp in (summary or "").lower() for rp in refusal_phrases)
        or (not steps_data and not has_topical_overlap)
        or (not steps_data and len(summary or "") < 50)
    )

    if is_rejected:
        summary = (
            f"{DISCRIMINATOR_FAILURE_PHRASE} "
            f"Please visit the official portal directly at {url} to view the statutory procedure."
        )
        step_objects = []
        docs = []
        confidence_val = "low"
    else:
        # Build Step objects
        step_objects = [
            Step(title=s["title"][:80], detail=s["detail"][:700])
            for s in steps_data
            if s.get("title") and s.get("detail")
        ]
        # Live evidence remains unverified until it passes the offline review pipeline.
        confidence_val = "medium" if len(summary) >= 40 else "low"

    # Build Citation object
    citation = Citation(
        title="Official Government Portal — Live Search Result",
        url=url,  # type: ignore[arg-type]
        excerpt=page_excerpt[:350].strip() or "Official government page content.",
        reported_last_verified=today,
        factual_verification="unverified",
    )

    disclaimer = (
        f"⚠️ This answer was retrieved live from the official government portal ({domain_netloc}). "
        "Please verify the information directly on the official portal before taking action."
    )

    title_text = f"Official Civic Procedure ({domain_netloc})"

    return Answer(
        entry_id=None,
        title=title_text,
        summary=summary,
        documents_needed=docs,
        steps=step_objects,
        warnings=[],
        source_url=url,  # type: ignore[arg-type]
        last_verified=today,
        confidence=confidence_val,
        masked_items=[],
        citations=[citation],
        disclaimer=disclaimer,
    )


__all__ = ["synthesize_from_web", "DISCRIMINATOR_FAILURE_PHRASE"]
