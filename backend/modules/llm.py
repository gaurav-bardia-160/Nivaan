"""Privacy-preserving Ollama-compatible grounded answer enhancement."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.memory import MemoryTurn
from backend.modules.qa_check import run_qa_checks
from backend.schemas import Answer, Step

logger = logging.getLogger("local_llm")

_ORIGINAL_HTTPX_CLIENT = httpx.Client
_ORIGINAL_HTTPX_POST = httpx.post
_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_is_generating = False
_is_generating_lock = threading.RLock()
SEARCH_WEB_SENTINEL = "SEARCH_WEB_REQUIRED"


def _is_direct_or_binary_question(query: str) -> bool:
    if not query:
        return False
    lowered = query.strip().lower()
    return any(lowered.startswith(p) for p in (
        "can i", "can we", "can a", "should i", "should we", "do i need", "does it",
        "will it", "is it", "is there", "are we", "am i", "whether", "do we need"
    ))


def _clean_model_prose(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json|markdown|md)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    # Strip accidental trailing schema labels if the model appends them to natural text
    cleaned = re.split(
        r"(?:\r?\n|\s){1,2}(?:documents_needed|steps)\s*:\s*\[",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cleaned = re.sub(r"\n*(?:documents_needed|steps)\s*:\s*.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


class GroundedRewrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    summary: str = Field(min_length=20, max_length=4000)
    documents_needed: list[str] = Field(default_factory=list)
    steps: list[dict[str, str]] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, value):
        if not isinstance(value, str):
            return value
        lines = [" ".join(line.split()) for line in value.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
        text = "\n".join(lines).strip()
        return re.sub(r"\n{3,}", "\n\n", text)


class SummaryStreamFilter:
    """Streams the summary string tokens in real-time from natural prose or JSON outputs."""

    def __init__(self):
        self.buffer = ""
        self.mode = "detecting"
        self.full_raw_text = ""
        self.accumulated_summary = ""
        self.in_escape = False

    def feed(self, chunk: str) -> list[str]:
        self.full_raw_text += chunk
        tokens_to_yield: list[str] = []
        if self.mode in ("done_streaming", "suppressed"):
            return tokens_to_yield

        if self.mode == "detecting":
            self.buffer += chunk
            stripped = self.buffer.lstrip()
            if not stripped:
                return tokens_to_yield

            upper = stripped.upper()
            if stripped.startswith("{") or stripped.startswith("`"):
                m = re.search(r'"summary"\s*:\s*"', self.buffer)
                if m:
                    self.mode = "streaming_json"
                    after_quote = self.buffer[m.end():]
                    self.buffer = ""
                    chunk = after_quote
                elif len(stripped) > 120 and "summary" not in stripped:
                    self.mode = "streaming_raw"
                    tokens_to_yield.append(self.buffer)
                    self.accumulated_summary += self.buffer
                    self.buffer = ""
                    return tokens_to_yield
                else:
                    return tokens_to_yield
            elif SEARCH_WEB_SENTINEL.startswith(upper) and len(upper) <= len(SEARCH_WEB_SENTINEL):
                if upper == SEARCH_WEB_SENTINEL:
                    self.mode = "suppressed"
                    self.buffer = ""
                return tokens_to_yield
            elif upper.startswith(SEARCH_WEB_SENTINEL):
                self.mode = "suppressed"
                self.buffer = ""
                return tokens_to_yield
            elif len(stripped) >= 4:
                self.mode = "streaming_raw"
                tokens_to_yield.append(self.buffer)
                self.accumulated_summary += self.buffer
                self.buffer = ""
                return tokens_to_yield
            else:
                return tokens_to_yield

        if self.mode == "streaming_raw":
            tail_window = (self.accumulated_summary[-40:] + chunk).lower()
            if re.search(r"(?:\n|^)\s*(?:documents_needed|steps)\s*:", tail_window):
                self.mode = "done_streaming"
                return tokens_to_yield
            tokens_to_yield.append(chunk)
            self.accumulated_summary += chunk
            return tokens_to_yield

        if self.mode == "streaming_json":
            current_token = []
            for ch in chunk:
                if self.in_escape:
                    self.in_escape = False
                    if ch == "n":
                        current_token.append("\n")
                    elif ch == "t":
                        current_token.append("\t")
                    elif ch == '"':
                        current_token.append('"')
                    elif ch == "\\":
                        current_token.append("\\")
                    else:
                        current_token.append(ch)
                elif ch == "\\":
                    self.in_escape = True
                elif ch == '"':
                    self.mode = "done_streaming"
                    break
                else:
                    current_token.append(ch)
            if current_token:
                emitted = "".join(current_token)
                tokens_to_yield.append(emitted)
                self.accumulated_summary += emitted

            return tokens_to_yield

        return tokens_to_yield


@dataclass(frozen=True)
class LocalLLMConfig:
    enabled: bool
    base_url: str
    model: str
    timeout_seconds: float | None
    allow_remote: bool
    num_ctx: int = 4096
    num_predict: int = 512

    @classmethod
    def from_env(cls) -> "LocalLLMConfig":
        raw_timeout = os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "").strip().lower()
        if not raw_timeout or raw_timeout in {"0", "none", "unlimited", "off", "false"}:
            timeout: float | None = None
        else:
            try:
                parsed = float(raw_timeout)
                timeout = None if parsed <= 0 else parsed
            except ValueError:
                timeout = None

        try:
            num_ctx = int(os.getenv("LOCAL_LLM_NUM_CTX", "4096"))
        except ValueError:
            num_ctx = 4096

        try:
            num_predict = int(os.getenv("LOCAL_LLM_NUM_PREDICT", "512"))
        except ValueError:
            num_predict = 512

        local_only = os.getenv("LOCAL_LLM_ONLY", "false").strip().lower() in _TRUE_VALUES
        enabled = local_only or (os.getenv("LOCAL_LLM_ENABLED", "false").strip().lower() in _TRUE_VALUES)

        return cls(
            enabled=enabled,
            base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            model=os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b").strip() or "qwen2.5:7b",
            timeout_seconds=timeout,
            allow_remote=os.getenv("LOCAL_LLM_ALLOW_REMOTE", "false").strip().lower() in _TRUE_VALUES,
            num_ctx=min(max(num_ctx, 1024), 32768),
            num_predict=min(max(num_predict, 64), 2048),
        )

    def validate_privacy_boundary(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("LOCAL_LLM_BASE_URL must be a valid HTTP URL")
        if not self.allow_remote and parsed.hostname.lower() not in _LOCAL_HOSTS:
            raise ValueError("Remote LLM endpoints require LOCAL_LLM_ALLOW_REMOTE=true")


CIVIC_NUMBER_WHITELIST = {
    "1947", "1930", "1950", "14448", "15100", "1800", "1077", "112", "100", "108",
    "24", "48", "72", "5", "7", "10", "15", "21", "30", "60", "90", "180", "365",
    "50", "100", "200", "500", "1000", "1500",
    "139", "119", "49", "234", "44", "330", "19", "31", "10", "107", "629"
}
CIVIC_NUMBER_WHITELIST.update(str(y) for y in range(2000, 2036))


class GeminiLLMClient:
    """High-accuracy cloud inference client via Google Gemini API."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        if os.getenv("LOCAL_LLM_ONLY", "false").strip().lower() in _TRUE_VALUES:
            self.api_key = None
        else:
            self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

    def available(self) -> bool:
        if os.getenv("LOCAL_LLM_ONLY", "false").strip().lower() in _TRUE_VALUES:
            return False
        return bool(self.api_key and str(self.api_key).strip())

    def synthesize(self, *, system: str, prompt: str, temperature: float = 0.1) -> GroundedRewrite | None:
        if not self.available():
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 800,
                "responseMimeType": "application/json"
            }
        }
        try:
            resp = httpx.post(url, json=payload, timeout=None)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed_json = json.loads(raw_text)

            summary = str(parsed_json.get("summary", "")).strip()
            raw_docs = parsed_json.get("documents_needed", [])
            docs = [_normalize_document_item(d) for d in (raw_docs if isinstance(raw_docs, list) else [])]
            docs = [d for d in docs if d]
            steps = [
                {"title": str(s.get("title", "")).strip(), "detail": str(s.get("detail", "")).strip()}
                for s in parsed_json.get("steps", [])
                if isinstance(s, dict) and s.get("title") and s.get("detail")
            ]
            if summary:
                return GroundedRewrite.model_validate({
                    "summary": summary,
                    "documents_needed": docs,
                    "steps": steps,
                })
        except Exception as e:
            logger.info("Gemini inference exception (%s), falling back to local Ollama", e)
            return None
        return None


def _normalize_document_item(item: Any) -> str | None:
    if not item:
        return None
    if isinstance(item, dict):
        title = item.get("title") or item.get("name") or item.get("document") or item.get("doc") or ""
        detail = item.get("detail") or item.get("url") or ""
        title = str(title).strip()
        detail = str(detail).strip()
        if title and detail and not detail.startswith("http"):
            return f"{title} ({detail})"
        if title:
            return title
        if detail:
            return detail
        return None
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        if (text.startswith("{") and text.endswith("}")) or ("'title'" in text or '"title"' in text):
            try:
                import ast
                val = ast.literal_eval(text)
                if isinstance(val, dict):
                    return _normalize_document_item(val)
            except Exception:
                try:
                    val = json.loads(text.replace("'", '"'))
                    if isinstance(val, dict):
                        return _normalize_document_item(val)
                except Exception:
                    pass
        m = re.search(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]", text)
        if m:
            return m.group(1).strip()
        return text
    return str(item).strip() or None


def _build_llm_prompt(
    question: str,
    answer: Answer,
    memory: tuple[MemoryTurn, ...] = (),
    *,
    stream_mode: bool = False,
    rag_passages: tuple[str, ...] = (),
) -> tuple[str, str, bool]:
    evidence = []
    if answer.entry_id and answer.steps:
        steps_text = " ".join(f"{s.title}: {s.detail}" for s in answer.steps[:4])
        docs_text = ", ".join(answer.documents_needed) if answer.documents_needed else "None"
        evidence.append(f"[Primary Verified Procedure] {answer.title}\nSummary: {answer.summary}\nProcedural Steps: {steps_text}\nDocuments Needed: {docs_text}\nOfficial Portal: {answer.source_url}")

    if rag_passages:
        total_chars = 0
        for idx, passage in enumerate(rag_passages[:3], 1):
            remaining = max(0, 2800 - total_chars)
            if remaining < 200:
                break
            chunk_text = passage[:min(1300, remaining)].strip()
            if chunk_text:
                total_chars += len(chunk_text)
                src_url = answer.citations[idx - 1].url if idx - 1 < len(answer.citations) else answer.source_url
                src_title = answer.citations[idx - 1].title if idx - 1 < len(answer.citations) else answer.title
                evidence.append(f"[Supporting Source {idx}] {src_title}\n{chunk_text}\nSource: {src_url}")
    elif answer.citations:
        total_chars = 0
        for idx, c in enumerate(answer.citations[:3], 1):
            remaining = max(0, 2800 - total_chars)
            if remaining < 200:
                break
            excerpt = c.excerpt[:min(1300, remaining)].strip()
            total_chars += len(excerpt)
            evidence.append(f"[Supporting Source {idx}] {c.title}\n{excerpt}\nSource: {c.url}")
    elif answer.summary or answer.steps:
        steps_text = " ".join(f"{s.title}: {s.detail}" for s in answer.steps[:4])
        docs_text = ", ".join(answer.documents_needed) if answer.documents_needed else "None"
        evidence.append(f"[1] {answer.title}\n{answer.summary}\nDocuments: {docs_text}\n{steps_text}\nSource: {answer.source_url}")
    else:
        return "", "", False

    dialogue_turns = []
    for turn in (memory or ())[-4:]:
        dialogue_turns.append(f"Citizen: {turn.user_text}")
        asst = getattr(turn, "assistant_text", None) or turn.answer_title
        if asst:
            dialogue_turns.append(f"Nivaan: {asst}")
    history = "\n".join(dialogue_turns) or "No previous context."
    evidence_text = "\n\n".join(evidence)

    is_greeting = "welcome" in answer.title.lower() or (not answer.steps and not answer.citations)
    if is_greeting:
        if stream_mode:
            system = (
                "You are Nivaan, a friendly AI civic assistant for India. "
                "Respond warmly in 1 to 2 conversational sentences and mention they can ask about official Indian government procedures "
                "(PAN, Passport, Aadhaar, Voter ID, ITR, EPF, Banking, State Services) or upload a document. "
                "Write plain conversational text only (no JSON)."
            )
        else:
            system = (
                "You are Nivaan, a friendly AI civic assistant for India. "
                "Respond warmly in 1 to 2 sentences and mention they can ask about official procedures "
                "(PAN, Passport, Aadhaar, Voter ID, ITR, EPF, State Services) or upload a document. "
                "Return JSON with key 'summary' (e.g. {\"summary\": \"...\"})."
            )
        prompt = f"Citizen greeting: {question[:300]}"
    elif stream_mode:
        system = (
            "You are Nivaan, an intelligent and helpful Indian Civic & Banking AI assistant. "
            "First, understand the user's exact question, intent, and specific facts (dates, amounts, portal, problem). "
            "ANTI-FABRICATION DIRECTIVE: Never assume unstated facts or premises (for example, never assume an employer or establishment is closed or non-operational when unstated by the citizen or stated as active). "
            "Then evaluate the Official Government Evidence provided below:\n"
            f"- If the evidence is completely off-topic or does NOT answer the citizen's specific question, output ONLY: {SEARCH_WEB_SENTINEL}\n"
            "- Otherwise, write a clear, natural, conversational response directly answering the citizen's question in the very first sentence.\n"
            "- Apply exact statutory rules, dates, monetary limits, and step-by-step instructions to the citizen's scenario.\n"
            "- Format cleanly with Markdown (bold key portals/figures, bullet points or numbered steps when helpful).\n"
            "- NEVER copy-paste manual headers or raw evidence verbatim.\n"
            "- NEVER output JSON, curly braces {}, or field labels like 'documents_needed:' or 'steps:'.\n"
            "- Only cite official .gov.in, .nic.in, or statutory portal URLs that appear in the evidence."
        )
        prompt = (
            f"--- Conversation Context ---\n{history}\n\n"
            f"--- Citizen Question ---\n{question[:1200]}\n\n"
            f"--- Official Government Evidence ---\n{evidence_text}\n\n"
            "Instructions: Answer directly in natural conversational English based ONLY on the evidence above."
        )
    else:
        system = (
            "You are Nivaan, an Indian Civic AI. Read the Citizen Question and Official Government Evidence. "
            "Understand the citizen's question first. "
            "ANTI-FABRICATION DIRECTIVE: Never assume unstated facts or premises (for example, never assume an employer or establishment is closed or non-operational when unstated by the citizen or stated as active). "
            f"If the evidence does NOT answer the citizen's specific question, return JSON with 'summary': '{SEARCH_WEB_SENTINEL}'. "
            "Otherwise, answer directly in the first sentence in clear, natural language, applying exact dates, monetary thresholds, "
            "and conditional rules to the user's facts. NEVER copy-paste the reference text verbatim. "
            "Cite only official .gov.in or .nic.in portals present in the evidence. "
            "Return valid JSON ONLY with keys: 'summary' (string), 'documents_needed' (list of strings, or []), "
            "and 'steps' (list of {'title', 'detail'}, or [])."
        )
        prompt = (
            f"--- Conversation Context ---\n{history}\n\n"
            f"--- Citizen Question ---\n{question[:1200]}\n\n"
            f"--- Official Government Evidence ---\n{evidence_text}\n\n"
            "Instructions: Synthesize a direct, natural-language answer applying the rules above to the citizen's exact facts. Return JSON only."
        )

    return system, prompt, is_greeting


def _call_ollama(payload: dict, base_url: str = "http://localhost:11434", timeout_seconds: float | None = None) -> str:
    response = httpx.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    raw_content = body.get("message", {}).get("content", "").strip()
    raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
    if raw_content.startswith("```"):
        raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
        raw_content = re.sub(r"\s*```$", "", raw_content)
    return raw_content.strip()


class LocalLLMClient:
    def __init__(self, config: LocalLLMConfig | None = None):
        self.config = config or LocalLLMConfig.from_env()
        self.config.validate_privacy_boundary()

    def probe(self) -> dict[str, object]:
        if not self.config.enabled:
            return {"available": False, "server_available": False, "model_available": False}
        try:
            probe_timeout = httpx.Timeout(2.0, connect=1.0)
            response = httpx.get(f"{self.config.base_url}/api/tags", timeout=probe_timeout)
            response.raise_for_status()
            body = response.json()
            models = body.get("models", []) if isinstance(body, dict) else []
            installed = {
                str(value).strip()
                for item in models
                if isinstance(item, dict)
                for value in (item.get("name"), item.get("model"))
                if value
            }
            configured = self.config.model
            aliases = {configured}
            if ":" not in configured:
                aliases.add(f"{configured}:latest")
            model_available = bool(installed & aliases)
            return {
                "available": model_available,
                "server_available": True,
                "model_available": model_available,
                "error": None if model_available else "configured_model_not_installed",
            }
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            return {
                "available": False,
                "server_available": False,
                "model_available": False,
                "error": "ollama_unavailable",
            }

    def available(self) -> bool:
        return bool(self.probe()["available"])

    def understand_query(
        self,
        question: str,
        memory: tuple[MemoryTurn, ...] = (),
    ) -> tuple[str | None, bool]:
        """Use the local 7B model to understand conversational/colloquial queries and emit search keywords."""
        if not self.config.enabled or not question or not question.strip():
            return None, True
        if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("TEST_LIVE_LLM") and httpx.post is _ORIGINAL_HTTPX_POST:
            return None, True

        history_lines = []
        for turn in (memory or ())[-3:]:
            if turn.user_text:
                history_lines.append(f"Citizen: {turn.user_text}")
            if turn.answer_title:
                history_lines.append(f"Nivaan: {turn.answer_title}")
        history_block = "\n".join(history_lines) or "None"

        system = (
            "You understand Indian civic, tax, banking, legal, identity, transport, and government service questions "
            "(including Hinglish, typos, or indirect descriptions). "
            "Extract the core topic as 3-10 crisp English search keywords for official government portals. "
            "Set is_civic to false ONLY for clearly unrelated non-civic requests (cooking recipes, sports scores, jokes, movies, weather, cryptocurrency or stock prices). "
            "Return JSON ONLY: {\"search_query\": \"...\", \"is_civic\": true}."
        )
        prompt = f"Context:\n{history_block}\n\nUser Question: {question[:600]}"
        payload = {
            "model": self.config.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": 0.0,
                "num_predict": 64,
                "num_ctx": min(self.config.num_ctx, 1024),
                "num_thread": min(os.cpu_count() or 4, 4),
            },
        }
        try:
            with _is_generating_lock:
                raw = _call_ollama(payload, self.config.base_url, self.config.timeout_seconds)
            data = json.loads(raw)
            if isinstance(data, dict):
                sq = str(data.get("search_query", "")).strip()
                is_civic = bool(data.get("is_civic", True))
                return (sq or None), is_civic
        except Exception as exc:
            logger.debug("Query understanding skipped (%s)", exc)
        return None, True

    def synthesize_grounded_answer(
        self,
        question: str,
        answer: Answer,
        memory: tuple[MemoryTurn, ...] = (),
        temperature: float | None = None,
        rag_passages: tuple[str, ...] = (),
    ) -> GroundedRewrite | None:
        if not self.config.enabled:
            return None

        system, prompt, is_greeting = _build_llm_prompt(
            question, answer, memory, stream_mode=False, rag_passages=rag_passages,
        )
        if not system or not prompt:
            return None

        gemini = GeminiLLMClient()
        if gemini.available():
            try:
                gemini_rewrite = gemini.synthesize(
                    system=system,
                    prompt=prompt,
                    temperature=temperature if temperature is not None else 0.1,
                )
                if gemini_rewrite and _is_grounded(gemini_rewrite.summary, answer, question):
                    return gemini_rewrite
            except Exception as e:
                logger.debug("Gemini fallback triggered: %s", e)

        avail_cpus = os.cpu_count() or 4
        optimal_threads = min(avail_cpus, 4)
        predict_limit = min(self.config.num_predict, 800)
        ctx_limit = min(self.config.num_ctx, 4096)

        payload = {
            "model": self.config.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": temperature if temperature is not None else (0.2 if is_greeting else 0.1),
                "num_predict": predict_limit,
                "num_ctx": ctx_limit,
                "num_thread": optimal_threads,
            },
        }
        global _is_generating
        with _is_generating_lock:
            _is_generating = True
            try:
                raw_content = _call_ollama(payload, self.config.base_url, self.config.timeout_seconds)

                summary_candidate = None
                docs_candidate = []
                steps_candidate = []
                try:
                    data = json.loads(raw_content)
                    if isinstance(data, dict):
                        if "summary" in data:
                            summary_candidate = str(data["summary"]).strip()
                        if "documents_needed" in data and isinstance(data["documents_needed"], list):
                            docs_candidate = [_normalize_document_item(d) for d in data["documents_needed"]]
                            docs_candidate = [d for d in docs_candidate if d]
                        if "steps" in data and isinstance(data["steps"], list):
                            steps_candidate = [
                                {"title": str(s.get("title", "")).strip(), "detail": str(s.get("detail", "")).strip()}
                                for s in data["steps"]
                                if isinstance(s, dict) and s.get("title") and s.get("detail")
                            ]
                except (json.JSONDecodeError, ValueError):
                    pass

                if not summary_candidate:
                    match = re.search(r'\{\s*"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*\}', raw_content)
                    if match:
                        try:
                            summary_candidate = match.group(1).encode().decode("unicode_escape", errors="ignore").strip()
                        except Exception:
                            summary_candidate = match.group(1).strip()
                    elif raw_content and not raw_content.startswith("{"):
                        summary_candidate = _clean_model_prose(raw_content)

                if not summary_candidate:
                    return None

                if SEARCH_WEB_SENTINEL in summary_candidate.upper():
                    return GroundedRewrite.model_validate({
                        "title": "__SEARCH_WEB__",
                        "summary": SEARCH_WEB_SENTINEL,
                        "documents_needed": [],
                        "steps": [],
                    })

                is_refusal = (
                    "does not contain the specific procedure for this issue" in summary_candidate.lower()
                    or "verified knowledge base does not contain" in summary_candidate.lower()
                    or "insufficient data in the verified civic knowledge base" in summary_candidate.lower()
                    or "does not explicitly mention the specific government portal" in summary_candidate.lower()
                )
                parsed = GroundedRewrite.model_validate({
                    "title": "No verified guide found" if is_refusal else None,
                    "summary": _clean_model_prose(summary_candidate),
                    "documents_needed": [] if is_refusal else docs_candidate,
                    "steps": [] if is_refusal else steps_candidate,
                })
            except Exception as e:
                logger.debug("Local LLM answer generation failed: %s", e)
                return None
            finally:
                _is_generating = False

        if is_refusal:
            return parsed

        if not _is_grounded(parsed.summary, answer, question, rag_passages=rag_passages):
            return None
        return parsed

    def stream_grounded_answer(
        self,
        *,
        question: str,
        answer: Answer,
        memory: tuple[MemoryTurn, ...] = (),
        temperature: float | None = None,
        rag_passages: tuple[str, ...] = (),
    ) -> Generator[tuple[str, object], None, None]:
        if not self.config.enabled:
            return
        if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("TEST_LIVE_LLM") and httpx.Client is _ORIGINAL_HTTPX_CLIENT:
            return

        system, prompt, is_greeting = _build_llm_prompt(
            question, answer, memory, stream_mode=True, rag_passages=rag_passages,
        )
        if not system or not prompt:
            return

        avail_cpus = os.cpu_count() or 4
        optimal_threads = min(avail_cpus, 4)
        predict_limit = min(self.config.num_predict, 800)
        ctx_limit = min(self.config.num_ctx, 4096)

        payload = {
            "model": self.config.model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": temperature if temperature is not None else (0.2 if is_greeting else 0.1),
                "num_predict": predict_limit,
                "num_ctx": ctx_limit,
                "num_thread": optimal_threads,
            },
        }

        stream_filter = SummaryStreamFilter()
        global _is_generating
        with _is_generating_lock:
            _is_generating = True
            try:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    with client.stream("POST", f"{self.config.base_url}/api/chat", json=payload) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if not line:
                                continue
                            try:
                                chunk_data = json.loads(line)
                            except Exception:
                                continue
                            content_chunk = chunk_data.get("message", {}).get("content", "")
                            if content_chunk:
                                tokens = stream_filter.feed(content_chunk)
                                for t in tokens:
                                    yield ("token", t)
                            if chunk_data.get("done"):
                                break
            except Exception as e:
                logger.debug("Local LLM streaming error: %s", e)
            finally:
                _is_generating = False

        raw_content = _clean_model_prose(stream_filter.full_raw_text)
        if SEARCH_WEB_SENTINEL in raw_content.upper():
            yield ("needs_web_search", None)
            return

        summary_candidate = None
        docs_candidate = []
        steps_candidate = []
        if raw_content.startswith("{"):
            try:
                data = json.loads(raw_content)
                if isinstance(data, dict):
                    if "summary" in data:
                        summary_candidate = str(data["summary"]).strip()
                    if "documents_needed" in data and isinstance(data["documents_needed"], list):
                        docs_candidate = [_normalize_document_item(d) for d in data["documents_needed"]]
                        docs_candidate = [d for d in docs_candidate if d]
                    if "steps" in data and isinstance(data["steps"], list):
                        steps_candidate = [
                            {"title": str(s.get("title", "")).strip(), "detail": str(s.get("detail", "")).strip()}
                            for s in data["steps"]
                            if isinstance(s, dict) and s.get("title") and s.get("detail")
                        ]
            except (json.JSONDecodeError, ValueError):
                pass

        if not summary_candidate:
            match = re.search(r'\{\s*"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*\}', raw_content)
            if match:
                try:
                    summary_candidate = match.group(1).encode().decode("unicode_escape", errors="ignore").strip()
                except Exception:
                    summary_candidate = match.group(1).strip()
            elif raw_content and not raw_content.startswith("{"):
                summary_candidate = raw_content

        if not summary_candidate and stream_filter.accumulated_summary:
            summary_candidate = _clean_model_prose(stream_filter.accumulated_summary)

        if summary_candidate:
            summary_candidate = _clean_model_prose(summary_candidate)
            if SEARCH_WEB_SENTINEL in summary_candidate.upper():
                yield ("needs_web_search", None)
                return

            is_refusal = (
                "does not contain the specific procedure for this issue" in summary_candidate.lower()
                or "verified knowledge base does not contain" in summary_candidate.lower()
                or "insufficient data in the verified civic knowledge base" in summary_candidate.lower()
                or "does not explicitly mention the specific government portal" in summary_candidate.lower()
            )
            try:
                parsed = GroundedRewrite.model_validate({
                    "summary": summary_candidate,
                    "documents_needed": [] if is_refusal else docs_candidate,
                    "steps": [] if is_refusal else steps_candidate,
                })
                if is_refusal or _is_grounded(parsed.summary, answer, question, rag_passages=rag_passages):
                    yield ("final", parsed)
                    return
            except Exception:
                pass

        yield ("final", None)

    def rewrite_summary(
        self,
        *,
        question: str,
        answer: Answer,
        memory: tuple[MemoryTurn, ...] = (),
    ) -> str | None:
        res = self.synthesize_grounded_answer(question=question, answer=answer, memory=memory)
        return res.summary if res else None


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text.lower())
        if token not in {
            "the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "can",
            "will", "have", "been", "here", "what", "when", "where", "how", "who", "they",
            "them", "their", "our", "all", "any", "some", "such", "into", "onto", "then",
            "than", "more", "also", "just", "must", "should", "could", "would", "about",
        }
    }


def _is_grounded(summary: str, answer: Answer, question: str = "", *, rag_passages: tuple[str, ...] = ()) -> bool:
    if "welcome" in answer.title.lower() or (not answer.steps and not answer.citations):
        return True
    summary_tokens = _tokens(summary)
    if not summary_tokens:
        return False
    evidence_parts = []
    if answer.summary or answer.steps:
        steps_text = " ".join(f"{s.title} {s.detail}" for s in answer.steps)
        docs_text = " ".join(answer.documents_needed)
        evidence_parts.append(f"{answer.title} {answer.summary} {docs_text} {steps_text} {answer.source_url}")
    if answer.citations:
        evidence_parts.extend(f"{c.title} {c.excerpt} {c.url}" for c in answer.citations)
    if rag_passages:
        evidence_parts.extend(rag_passages)

    evidence_text = " ".join(evidence_parts)
    evidence_tokens = _tokens(evidence_text)
    combined_grounding_tokens = evidence_tokens | _tokens(question)

    overlap = len(summary_tokens & combined_grounding_tokens) / max(len(summary_tokens), 1)
    if overlap < 0.10:
        return False

    summary_urls = set(re.findall(r"https?://[^\s)\]]+", summary.lower()))
    evidence_urls = set(re.findall(r"https?://[^\s)\]]+", evidence_text.lower()))
    if not summary_urls <= evidence_urls:
        return False

    sentences = tuple(part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", summary) if part.strip())
    for sentence in sentences:
        s_tokens = _tokens(sentence)
        if len(s_tokens) < 4:
            continue
        sentence_overlap = len(s_tokens & combined_grounding_tokens) / len(s_tokens)
        if sentence_overlap < 0.10:
            return False

    summary_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", summary)) - {str(i) for i in range(1, 11)}
    evidence_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", f"{evidence_text} {question}"))
    unmatched = summary_numbers - evidence_numbers
    for num in unmatched:
        if num in CIVIC_NUMBER_WHITELIST:
            continue
        try:
            val = float(num.replace(",", ""))
            if val >= 100:
                return False
        except ValueError:
            pass

    return True


_health_lock = threading.Lock()
_health_cache: tuple[float, dict[str, object]] | None = None


def local_llm_enabled() -> bool:
    return LocalLLMConfig.from_env().enabled


def local_llm_health(*, force: bool = False) -> dict[str, object]:
    global _health_cache
    config = LocalLLMConfig.from_env()
    gemini = GeminiLLMClient()
    base = {
        "enabled": config.enabled or gemini.available(),
        "active_engine": "gemini_cloud" if gemini.available() else "ollama_local",
        "gemini_available": gemini.available(),
        "gemini_model": gemini.model if gemini.available() else None,
        "provider": "gemini_api" if gemini.available() else "ollama_compatible",
        "model": gemini.model if gemini.available() else config.model,
        "base_url": "https://generativelanguage.googleapis.com" if gemini.available() else config.base_url,
        "privacy_mode": "google_api_confidential" if gemini.available() else ("local_only" if not config.allow_remote else "remote_explicitly_allowed"),
        "num_ctx": config.num_ctx,
        "num_predict": config.num_predict,
    }
    if not config.enabled:
        return {**base, "available": False}

    now = time.time()
    with _health_lock:
        if _is_generating and _health_cache and _health_cache[1].get("available"):
            return _health_cache[1]
        if not force and _health_cache and now - _health_cache[0] < 30:
            return _health_cache[1]
        try:
            result = {**base, **LocalLLMClient(config).probe()}
            if not result.get("available") and _health_cache and _health_cache[1].get("available"):
                return _health_cache[1]
            _health_cache = (now, result)
            return result
        except Exception as exc:
            if _health_cache and _health_cache[1].get("available"):
                return _health_cache[1]
            result = {**base, "available": False, "error": str(exc)}
            _health_cache = (now, result)
            return result


def _extract_dynamic_steps_from_summary(summary: str) -> list[Step]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", summary) if s.strip()]
    action_keywords = {
        "visit", "open", "go", "fill", "apply", "submit", "upload", "provide",
        "bring", "carry", "verify", "track", "download", "pay", "book", "register",
        "check", "ensure", "select", "click", "log", "enter", "contact", "file", "request"
    }
    steps = []
    for s in sentences:
        clean_line = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", s).strip()
        if not clean_line or len(clean_line) < 12:
            continue
        words = {w.lower().strip("',.!:*") for w in clean_line.split()}
        if words & action_keywords or any(clean_line.lower().startswith(p) for p in ("first", "then", "next", "after", "finally", "step")):
            clean_s = re.sub(r"^(First|Then|Next|After that|Finally|Also|Please)[,\s]+", "", clean_line, flags=re.IGNORECASE)
            title_words = clean_s.replace("**", "").split()[:7]
            step_title = " ".join(title_words).rstrip(",.:;")
            steps.append(Step(title=step_title[:80], detail=clean_line))
    return steps[:6]


def apply_rewrite_to_answer(
    answer: Answer,
    rewrite: GroundedRewrite | None,
    question: str,
) -> Answer:
    """Applies a GroundedRewrite to the Answer schema with direct-question and QA checks."""
    if not rewrite or rewrite.title == "__SEARCH_WEB__":
        return answer

    is_refusal = (
        "does not contain the specific procedure for this issue" in rewrite.summary.lower()
        or "verified knowledge base does not contain" in rewrite.summary.lower()
        or "insufficient data in the verified civic knowledge base" in rewrite.summary.lower()
        or "does not explicitly mention the specific government portal" in rewrite.summary.lower()
    )
    if is_refusal:
        from backend.modules.explainer import not_found_answer
        return not_found_answer(question)

    is_direct_q = _is_direct_or_binary_question(question)
    updates: dict[str, object] = {"summary": rewrite.summary}
    if is_direct_q and not rewrite.documents_needed:
        updates["documents_needed"] = []
    elif rewrite.documents_needed and len(rewrite.documents_needed) > 0:
        updates["documents_needed"] = rewrite.documents_needed

    if rewrite.steps and len(rewrite.steps) >= 2:
        new_steps = [
            Step(title=s["title"][:80], detail=s["detail"])
            for s in rewrite.steps
            if s.get("title") and s.get("detail")
        ]
        if len(new_steps) >= 2:
            updates["steps"] = new_steps
    elif is_direct_q:
        updates["steps"] = []
    elif answer.citations and len(answer.steps) <= 3 and any("review" in s.title.lower() or "read" in s.title.lower() for s in answer.steps):
        ai_steps = _extract_dynamic_steps_from_summary(rewrite.summary)
        if len(ai_steps) >= 2:
            updates["steps"] = ai_steps
        else:
            # Avoid showing raw placeholder "Review <excerpt>" cards when prose already explains clearly
            updates["steps"] = []

    enhanced = answer.model_copy(update=updates)

    source_parts = []
    if answer.citations:
        for c in answer.citations:
            source_parts.append(f"{c.title} {c.excerpt} {c.url}")
    else:
        source_parts.append(f"{answer.title} {answer.summary}")
    source_parts.append(" ".join(answer.documents_needed))
    source_parts.append(" ".join(f"{s.title} {s.detail}" for s in answer.steps))
    source_text = " ".join(source_parts)
    qa_warnings = run_qa_checks(
        answer_text=rewrite.summary,
        source_text=source_text,
        source_url=answer.source_url,
    )
    if qa_warnings:
        logger.info("QA warnings for question '%s': %s", question[:60], qa_warnings)

    return enhanced


def enhance_grounded_answer(
    answer: Answer,
    *,
    question: str,
    memory: tuple[MemoryTurn, ...] = (),
    temperature: float | None = None,
) -> Answer:
    """Return a locally synthesized dynamic answer or the exact deterministic answer on failure."""
    if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("TEST_LIVE_LLM"):
        return answer
    try:
        rewrite = LocalLLMClient().synthesize_grounded_answer(
            question=question,
            answer=answer,
            memory=memory,
            temperature=temperature,
        )
    except Exception:
        rewrite = None
    return apply_rewrite_to_answer(answer, rewrite, question)


__all__ = [
    "GroundedRewrite",
    "LocalLLMClient",
    "LocalLLMConfig",
    "SEARCH_WEB_SENTINEL",
    "SummaryStreamFilter",
    "apply_rewrite_to_answer",
    "enhance_grounded_answer",
    "local_llm_enabled",
    "local_llm_health",
]
