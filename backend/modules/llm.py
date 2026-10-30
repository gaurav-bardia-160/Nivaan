"""Privacy-preserving Ollama-compatible grounded answer enhancement.

The local model is optional and disabled by default. It can rewrite an already-grounded
extractive summary for readability, but every sentence must stay tethered to the retrieved
facts and cannot introduce new external claims, URLs, or unsupported steps.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.modules.memory import MemoryTurn
from backend.modules.qa_check import run_qa_checks
from backend.schemas import Answer, Step

logger = logging.getLogger("local_llm")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_is_generating = False
_is_generating_lock = threading.Lock()


class GroundedRewrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = Field(min_length=20, max_length=2400)
    documents_needed: list[str] = Field(default_factory=list)
    steps: list[dict[str, str]] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, value):
        if not isinstance(value, str):
            return value
        return " ".join(value.strip().split())


@dataclass(frozen=True)
class LocalLLMConfig:
    enabled: bool
    base_url: str
    model: str
    timeout_seconds: float
    allow_remote: bool
    num_ctx: int = 4096
    num_predict: int = 384

    @classmethod
    def from_env(cls) -> "LocalLLMConfig":
        raw_timeout = os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "180")
        try:
            timeout = float(raw_timeout)
        except ValueError:
            timeout = 90.0

        try:
            num_ctx = int(os.getenv("LOCAL_LLM_NUM_CTX", "4096"))
        except ValueError:
            num_ctx = 3072

        try:
            num_predict = int(os.getenv("LOCAL_LLM_NUM_PREDICT", "384"))
        except ValueError:
            num_predict = 384

        return cls(
            enabled=os.getenv("LOCAL_LLM_ENABLED", "false").strip().lower() in _TRUE_VALUES,
            base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            model=os.getenv("LOCAL_LLM_MODEL", "qwen2.5:3b").strip() or "qwen2.5:3b",
            timeout_seconds=min(max(timeout, 1.0), 180.0),
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
    "2011", "2012", "2013", "2014", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026",
    "1949", "1952", "1961", "1987", "1995", "2005", "2019",
    "139", "119", "49", "234", "44", "330", "19", "31", "10", "107", "629"
}


class GeminiLLMClient:
    """High-accuracy cloud inference client via Google Gemini API."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

    def available(self) -> bool:
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
            resp = httpx.post(url, json=payload, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed_json = json.loads(raw_text)

            summary = str(parsed_json.get("summary", "")).strip()
            docs = [str(d).strip() for d in parsed_json.get("documents_needed", []) if str(d).strip()]
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


class LocalLLMClient:
    def __init__(self, config: LocalLLMConfig | None = None):
        self.config = config or LocalLLMConfig.from_env()
        self.config.validate_privacy_boundary()

    def probe(self) -> dict[str, object]:
        if not self.config.enabled:
            return {"available": False, "server_available": False, "model_available": False}
        try:
            probe_timeout = httpx.Timeout(min(self.config.timeout_seconds, 2.0), connect=min(self.config.timeout_seconds, 1.0))
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

    def synthesize_grounded_answer(
        self,
        *,
        question: str,
        answer: Answer,
        memory: tuple[MemoryTurn, ...] = (),
        temperature: float | None = None,
    ) -> GroundedRewrite | None:
        if not self.config.enabled:
            return None

        evidence = []
        if answer.citations:
            for index, citation in enumerate(answer.citations[:3], 1):
                excerpt = citation.excerpt[:400].strip()
                evidence.append(f"[{index}] {citation.title}\n{excerpt}\nSource: {citation.url}")
        elif answer.summary or answer.steps:
            steps_text = " ".join(f"{s.title}: {s.detail}" for s in answer.steps[:4])
            docs_text = ", ".join(answer.documents_needed) if answer.documents_needed else "None"
            evidence.append(f"[1] {answer.title}\n{answer.summary}\nDocuments: {docs_text}\n{steps_text}\nSource: {answer.source_url}")
        else:
            return None

        # Build multi-turn conversational dialogue from up to the last 10 turns
        dialogue_turns = []
        for turn in memory[-25:]:
            dialogue_turns.append(f"Citizen: {turn.user_text}")
            asst = getattr(turn, "assistant_text", None) or turn.answer_title
            if asst:
                dialogue_turns.append(f"Nivaan: {asst}")
        history = "\n".join(dialogue_turns) or "No previous context."
        evidence_text = "\n\n".join(evidence)

        is_greeting = "welcome" in answer.title.lower() or (not answer.steps and not answer.citations)
        if is_greeting:
            system = (
                "You are Nivaan, a friendly and intelligent AI civic assistant for India. "
                "Respond warmly, naturally, and conversationally to the citizen's greeting in 1 to 2 sentences. "
                "Mention that they can ask about official procedures (like PAN, Passport, Aadhaar, Voter ID, ITR, EPF, State Services) "
                "or upload a document to review. Do not invent numbered steps. "
                "Return JSON with key 'summary' (e.g. {\"summary\": \"...\"})."
            )
            prompt = f"Citizen greeting: {question[:300]}"
        else:
            system = (
                "You are Nivaan, an intelligent, conversational AI civic guide for Indian citizens. "
                "Carefully analyze the citizen's question and any previous conversation history and official evidence. "
                "If the citizen asks a follow-up or asks to clarify previously mentioned details (e.g. documents, rules, fees, address changes), "
                "maintain conversational continuity with the previous turns while adhering strictly to the official evidence. "
                "Explain the exact procedure or required actions directly, helpfully, and conversationally. "
                "Return JSON with keys: 'summary' (string), 'documents_needed' (list of specific required documents, or [] if none), "
                "and 'steps' (list of 2-5 actionable objects with 'title' and 'detail', or [] if none).\n\n"
                "STRICT GROUNDING RULES (never violate these):\n"
                "- Use ONLY terms, abbreviations, and labels that appear verbatim in the source text. "
                "Do not invent or standardize abbreviations (e.g., do not write 'PoB' unless the source text uses that exact term). "
                "If the source says 'date of birth proof,' use that phrase, not an invented acronym.\n"
                "- Every fact in the answer must be traceable to a specific sentence in the source text. "
                "If you cannot point to the sentence, do not include the fact.\n"
                "- Do not upgrade an optional or implied action into a mandatory numbered step. "
                "If the source does not explicitly sequence something as a required step, do not present it as 'Step N.'\n"
                "- If the source text states something is free of cost, exempt, optional, or not required, "
                "you MUST include that detail. Do not drop qualifying or exempting facts for brevity.\n"
                "- List facts separately for special cases (children, exemptions, special categories) "
                "rather than omitting them or folding them into the general procedure.\n"
                "- When the citizen reports an error, rejection, stuck status, transaction failure, or processing delay:\n"
                "  1. Explain the specific Root Cause from the official evidence.\n"
                "  2. Give the exact Direct Resolution steps (forms, portal path, correction procedure).\n"
                "  3. State the statutory Turnaround Time (TAT) and the official Escalation Desk (Ombudsman, EPFiGMS, CPGRAMS, or helpline) if unresolved."
            )
            prompt = (
                f"--- Conversation Context ---\n{history}\n\n"
                f"--- Citizen Question ---\n{question[:1200]}\n\n"
                f"--- Official Government Evidence ---\n{evidence_text}\n\n"
                "Instructions: Answer the citizen's question helpfully using the official evidence and conversation context above. "
                "If this is a follow-up, refer back to the context smoothly."
            )

        # 1. Accelerated Cloud Inference: Try Gemini first if API key is present for sub-3s high-accuracy response
        gemini = GeminiLLMClient()
        if gemini.available():
            try:
                gemini_rewrite = gemini.synthesize(
                    system=system,
                    prompt=prompt,
                    temperature=temperature if temperature is not None else 0.1,
                )
                if gemini_rewrite and _is_grounded(gemini_rewrite.summary, answer):
                    return gemini_rewrite
            except Exception as e:
                logger.debug("Gemini fallback triggered: %s", e)

        # 2. Local Fallback Path: Ollama on CPU

        # Allocate threads safely (leave 1 thread free for OS and Uvicorn on 2-core/4-thread CPUs)
        avail_cpus = os.cpu_count() or 4
        optimal_threads = max(1, min(avail_cpus, 3))

        payload = {
            "model": self.config.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": temperature if temperature is not None else (0.2 if is_greeting else 0.1),
                "num_predict": self.config.num_predict,
                "num_ctx": self.config.num_ctx,
                "num_thread": optimal_threads,
            },
        }
        global _is_generating
        with _is_generating_lock:
            _is_generating = True
        try:
            response = httpx.post(
                f"{self.config.base_url}/api/chat",
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            raw_content = body.get("message", {}).get("content", "").strip()
            raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
            if raw_content.startswith("```"):
                raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
                raw_content = re.sub(r"\s*```$", "", raw_content)
            raw_content = raw_content.strip()

            summary_candidate = None
            docs_candidate = []
            steps_candidate = []
            try:
                data = json.loads(raw_content)
                if isinstance(data, dict):
                    if "summary" in data:
                        summary_candidate = str(data["summary"]).strip()
                    if "documents_needed" in data and isinstance(data["documents_needed"], list):
                        docs_candidate = [str(d).strip() for d in data["documents_needed"] if str(d).strip()]
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
                    summary_candidate = raw_content.strip()

            if not summary_candidate:
                return None

            parsed = GroundedRewrite.model_validate({
                "summary": summary_candidate,
                "documents_needed": docs_candidate,
                "steps": steps_candidate,
            })
        except Exception as e:
            logger.debug("Local LLM answer generation failed: %s", e)
            return None
        finally:
            with _is_generating_lock:
                _is_generating = False

        if not _is_grounded(parsed.summary, answer):
            return None
        return parsed

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


def _is_grounded(summary: str, answer: Answer) -> bool:
    if "welcome" in answer.title.lower() or (not answer.steps and not answer.citations):
        return True
    summary_tokens = _tokens(summary)
    if not summary_tokens:
        return False
    if answer.citations:
        evidence_text = " ".join(f"{c.title} {c.excerpt} {c.url}" for c in answer.citations)
        citation_token_sets = tuple(_tokens(f"{c.title} {c.excerpt} {c.url}") for c in answer.citations)
    else:
        steps_text = " ".join(f"{s.title} {s.detail}" for s in answer.steps)
        docs_text = " ".join(answer.documents_needed)
        evidence_text = f"{answer.title} {answer.summary} {docs_text} {steps_text} {answer.source_url}"
        citation_token_sets = (_tokens(evidence_text),)

    evidence_tokens = _tokens(evidence_text)
    overlap = len(summary_tokens & evidence_tokens) / max(len(summary_tokens), 1)
    if overlap < 0.12:
        return False

    summary_urls = set(re.findall(r"https?://[^\s)\]]+", summary.lower()))
    evidence_urls = set(re.findall(r"https?://[^\s)\]]+", evidence_text.lower()))
    if not summary_urls <= evidence_urls:
        return False

    sentences = tuple(part.strip() for part in re.split(r"(?<=[.!?])\s+", summary) if part.strip())
    for sentence in sentences:
        s_tokens = _tokens(sentence)
        if len(s_tokens) < 4:
            continue
        best_overlap = max(
            (len(s_tokens & c_tokens) / len(s_tokens) for c_tokens in citation_token_sets),
            default=0.0,
        )
        if best_overlap < 0.12:
            return False

    summary_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", summary)) - {str(i) for i in range(1, 11)}
    evidence_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", evidence_text))
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
        # If inference is actively generating, Ollama is alive and busy; return cached healthy status
        if _is_generating and _health_cache and _health_cache[1].get("available"):
            return _health_cache[1]
        # Reuse cache for 30s to prevent opening redundant sockets every 4 seconds
        if not force and _health_cache and now - _health_cache[0] < 30:
            return _health_cache[1]
        try:
            result = {**base, **LocalLLMClient(config).probe()}
            # If probe temporarily failed while under heavy CPU load, don't flap if previously healthy
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
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", summary) if s.strip()]
    action_keywords = {
        "visit", "open", "go", "fill", "apply", "submit", "upload", "provide",
        "bring", "carry", "verify", "track", "download", "pay", "book", "register",
        "check", "ensure", "select", "click", "log", "enter", "contact"
    }
    steps = []
    for s in sentences:
        words = {w.lower().strip("',.!") for w in s.split()}
        if words & action_keywords or any(s.lower().startswith(p) for p in ("first", "then", "next", "after", "finally", "step")):
            clean_s = re.sub(r"^(First|Then|Next|After that|Finally|Also|Please)[,\s]+", "", s, flags=re.IGNORECASE)
            title_words = clean_s.split()[:7]
            step_title = " ".join(title_words).rstrip(",.:;")
            steps.append(Step(title=step_title[:80], detail=s))
    return steps


def enhance_grounded_answer(
    answer: Answer,
    *,
    question: str,
    memory: tuple[MemoryTurn, ...] = (),
    temperature: float | None = None,
) -> Answer:
    """Return a locally synthesized dynamic answer or the exact deterministic answer on failure."""
    try:
        rewrite = LocalLLMClient().synthesize_grounded_answer(
            question=question,
            answer=answer,
            memory=memory,
            temperature=temperature,
        )
    except Exception:
        rewrite = None
    if not rewrite:
        return answer

    updates: dict[str, object] = {"summary": rewrite.summary}
    if rewrite.documents_needed and len(rewrite.documents_needed) > 0:
        updates["documents_needed"] = rewrite.documents_needed
    if rewrite.steps and len(rewrite.steps) >= 2:
        new_steps = [
            Step(title=s["title"][:80], detail=s["detail"])
            for s in rewrite.steps
            if s.get("title") and s.get("detail")
        ]
        if len(new_steps) >= 2:
            updates["steps"] = new_steps
    elif answer.citations and len(answer.steps) <= 3 and any("review" in s.title.lower() or "read" in s.title.lower() for s in answer.steps):
        ai_steps = _extract_dynamic_steps_from_summary(rewrite.summary)
        if len(ai_steps) >= 2:
            updates["steps"] = ai_steps

    enhanced = answer.model_copy(update=updates)

    # --- Post-generation QA check ---
    # Build source text from the original answer evidence
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


__all__ = [
    "GroundedRewrite",
    "LocalLLMClient",
    "LocalLLMConfig",
    "enhance_grounded_answer",
    "local_llm_enabled",
    "local_llm_health",
]
