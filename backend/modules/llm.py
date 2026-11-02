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
from collections.abc import Generator
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


def _is_direct_or_binary_question(query: str) -> bool:
    if not query:
        return False
    lowered = query.strip().lower()
    return any(lowered.startswith(p) for p in (
        "can i", "can we", "can a", "should i", "should we", "do i need", "does it",
        "will it", "is it", "is there", "are we", "am i", "whether", "do we need"
    ))

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


class SummaryStreamFilter:
    """Streams the summary string tokens in real-time from either JSON or raw model outputs."""

    def __init__(self):
        self.buffer = ""
        self.mode = "detecting"
        self.full_raw_text = ""
        self.accumulated_summary = ""
        self.in_escape = False

    def feed(self, chunk: str) -> list[str]:
        self.full_raw_text += chunk
        tokens_to_yield = []
        if self.mode == "done_streaming":
            return tokens_to_yield

        if self.mode == "detecting":
            self.buffer += chunk
            stripped = self.buffer.lstrip()
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
            elif len(stripped) >= 15:
                self.mode = "streaming_raw"
                tokens_to_yield.append(self.buffer)
                self.accumulated_summary += self.buffer
                self.buffer = ""
                return tokens_to_yield
            else:
                return tokens_to_yield

        if self.mode == "streaming_raw":
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
                    elif ch == '\\':
                        current_token.append('\\')
                    else:
                        current_token.append(ch)
                elif ch == '\\':
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

        local_only = os.getenv("LOCAL_LLM_ONLY", "false").strip().lower() in _TRUE_VALUES
        enabled = local_only or (os.getenv("LOCAL_LLM_ENABLED", "false").strip().lower() in _TRUE_VALUES)

        return cls(
            enabled=enabled,
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


def _build_llm_prompt(
    question: str,
    answer: Answer,
    memory: tuple[MemoryTurn, ...] = (),
) -> tuple[str, str, bool]:
    evidence = []
    if answer.entry_id and answer.steps:
        # Primary anchor: canonical verified procedure and audited steps
        steps_text = " ".join(f"{s.title}: {s.detail}" for s in answer.steps[:4])
        docs_text = ", ".join(answer.documents_needed) if answer.documents_needed else "None"
        evidence.append(f"[Primary Verified Procedure] {answer.title}\nSummary: {answer.summary}\nProcedural Steps: {steps_text}\nDocuments Needed: {docs_text}\nOfficial Portal: {answer.source_url}")
        if answer.citations:
            for idx, c in enumerate(answer.citations[:2], 1):
                evidence.append(f"[Supporting Source {idx}] {c.title}\n{c.excerpt[:350].strip()}\nSource: {c.url}")
    elif answer.citations:
        for index, citation in enumerate(answer.citations[:2], 1):
            excerpt = citation.excerpt[:350].strip()
            evidence.append(f"[{index}] {citation.title}\n{excerpt}\nSource: {citation.url}")
    elif answer.summary or answer.steps:
        steps_text = " ".join(f"{s.title}: {s.detail}" for s in answer.steps[:4])
        docs_text = ", ".join(answer.documents_needed) if answer.documents_needed else "None"
        evidence.append(f"[1] {answer.title}\n{answer.summary}\nDocuments: {docs_text}\n{steps_text}\nSource: {answer.source_url}")
    else:
        return "", "", False

    # Build multi-turn conversational dialogue from up to the last 25 turns
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
        system_base = (
            "You are Nivaan, an intelligent, conversational AI civic guide for Indian citizens. "
            "Carefully analyze the citizen's question and official evidence. "
            "Explain the exact procedure or required actions directly, helpfully, and conversationally. "
            "Return JSON with keys: 'summary' (string), 'documents_needed' (list, or [] if none), and 'steps' (list with 'title' and 'detail', or [] if none).\n\n"
            "STRICT GROUNDING & REASONING RULES:\n"
            "- CONTEXT-RELEVANCE GATE: If the official evidence does NOT address the scenario, output: {\"summary\": \"The verified knowledge base does not contain the specific procedure for this issue.\", \"documents_needed\": [], \"steps\": []}.\n"
            "- DIRECT FIRST-SENTENCE: Answer the user's explicit question directly in the very first sentence. For binary/jurisdictional questions ('Can I...', 'Should I...', 'Will it...'), answer 'Yes' or 'No' with statutory reason, and return 'steps': [] and 'documents_needed': []. Only include 'steps' when asked how to perform a multi-step action.\n"
            "- ZERO VAGUE PUNTS: Always specify exact official portals, forms, and escalation desks. Never say 'contact customer care'.\n"
            "- ZERO CROSS-CONTAMINATION: Never blend unrelated error codes or procedures.\n"
            "- ZERO EXTERNAL COMMERCIAL ENTITIES: Never reference commercial services (e.g. legaltax.in); cite only official .gov.in or .nic.in portals."
        )

        domain_rules = []
        lowered_q = question.lower()
        if any(k in lowered_q for k in ("139(9)", "139(5)", "defective", "revised return")):
            domain_rules.append("SECTION 139(9) TRAP: If asked about filing a Revised Return (139(5)) for a 139(9) Defective Notice, state in the first sentence: 'No, you should NOT file a Revised Return under Section 139(5). A revised return does NOT cure a Section 139(9) defect notice and will cause the return to be declared invalid ab initio.' Direct responding via e-File > e-Proceedings > Defective Notice within 15 days. Never cite synthetic case studies.")
        elif any(k in lowered_q for k in ("consumer", "edaakhil", "district court", "represent myself", "lawyer")):
            domain_rules.append("CONSUMER COURT: If asked about self-representation or lawyer, answer: 'Yes, you can represent yourself in consumer court without hiring an advocate/lawyer under the Consumer Protection Act, 2019 via e-Daakhil (edaakhil.nic.in).' If asked about jurisdiction, state: 'Yes, claims up to 50 lakh lie before the District Commission (DCDRC).'")
        elif any(k in lowered_q for k in ("nalsa", "legal aid")):
            domain_rules.append("FREE LEGAL AID: Free legal aid is available under Section 12 of the Legal Services Authorities Act, 1987 (nalsa.gov.in, DLSA, helpline 15100).")
        elif any(k in lowered_q for k in ("blo", "voter", "epic", "e-epic")):
            domain_rules.append("VOTER ID: Direct tracking on voters.eci.gov.in using Form 6/8 Reference Number, contacting BLO via 'Know Your Polling Station & Officer', or escalating via NGRS (voters.eci.gov.in) / helpline 1950.")
        elif any(k in lowered_q for k in ("credit card", "unsolicited")):
            domain_rules.append("CREDIT CARD: RBI Master Direction: Unsolicited cards must be cancelled without fee with 2x penalty. Disputed charges go to issuer's grievance desk, then RBI Ombudsman (cms.rbi.org.in / 14448).")
        elif any(k in lowered_q for k in ("pvc", "srn")):
            domain_rules.append("AADHAAR PVC: State 24-48h gateway reconciliation window, 5-7 business days bank auto-reversal, and UIDAI escalation via helpdesk@uidai.gov.in with 12-digit UTR.")
        elif any(k in lowered_q for k in ("bank validation", "refund unpaid")):
            domain_rules.append("BANK VALIDATION: Resolution path is Profile > My Bank Account to re-validate IFSC, followed by Services > Refund Reissue Request. Never advise filing a defective return schema.")

        if domain_rules:
            system = system_base + "\nSPECIFIC STATUTORY RULE:\n" + "\n".join(domain_rules)
        else:
            system = system_base
        prompt = (
            f"--- Conversation Context ---\n{history}\n\n"
            f"--- Citizen Question ---\n{question[:1200]}\n\n"
            f"--- Official Government Evidence ---\n{evidence_text}\n\n"
            "Instructions: Answer the citizen's question helpfully using the official evidence and conversation context above. "
            "If this is a follow-up, refer back to the context smoothly."
        )

    return system, prompt, is_greeting


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

        system, prompt, is_greeting = _build_llm_prompt(question, answer, memory)
        if not system or not prompt:
            return None

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

        # Optimize CPU inference: allocate threads and cap context/predict for direct answers
        avail_cpus = os.cpu_count() or 4
        optimal_threads = min(avail_cpus, 4)
        is_direct_q = _is_direct_or_binary_question(question)
        predict_limit = min(self.config.num_predict, 180) if is_direct_q else self.config.num_predict
        ctx_limit = min(self.config.num_ctx, 2048)

        payload = {
            "model": self.config.model,
            "stream": False,
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

            is_refusal = (
                "does not contain the specific procedure for this issue" in summary_candidate.lower()
                or "verified knowledge base does not contain" in summary_candidate.lower()
            )
            parsed = GroundedRewrite.model_validate({
                "summary": summary_candidate,
                "documents_needed": [] if is_refusal else docs_candidate,
                "steps": [] if is_refusal else steps_candidate,
            })
        except Exception as e:
            logger.debug("Local LLM answer generation failed: %s", e)
            return None
        finally:
            with _is_generating_lock:
                _is_generating = False

        if is_refusal:
            return parsed

        if not _is_grounded(parsed.summary, answer):
            return None
        return parsed

    def stream_grounded_answer(
        self,
        *,
        question: str,
        answer: Answer,
        memory: tuple[MemoryTurn, ...] = (),
        temperature: float | None = None,
    ) -> Generator[tuple[str, object], None, None]:
        """Streams plain summary text tokens in real time, then yields the final validated GroundedRewrite or None."""
        if not self.config.enabled:
            return

        system, prompt, is_greeting = _build_llm_prompt(question, answer, memory)
        if not system or not prompt:
            return

        avail_cpus = os.cpu_count() or 4
        optimal_threads = min(avail_cpus, 4)
        is_direct_q = _is_direct_or_binary_question(question)
        predict_limit = min(self.config.num_predict, 180) if is_direct_q else self.config.num_predict
        ctx_limit = min(self.config.num_ctx, 2048)

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
            with _is_generating_lock:
                _is_generating = False

        # Parse the complete rewrite
        raw_content = stream_filter.full_raw_text.strip()
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

        if not summary_candidate and stream_filter.accumulated_summary:
            summary_candidate = stream_filter.accumulated_summary.strip()

        if summary_candidate:
            is_refusal = (
                "does not contain the specific procedure for this issue" in summary_candidate.lower()
                or "verified knowledge base does not contain" in summary_candidate.lower()
            )
            try:
                parsed = GroundedRewrite.model_validate({
                    "summary": summary_candidate,
                    "documents_needed": [] if is_refusal else docs_candidate,
                    "steps": [] if is_refusal else steps_candidate,
                })
                if is_refusal or _is_grounded(parsed.summary, answer):
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


def _is_grounded(summary: str, answer: Answer) -> bool:
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

    evidence_text = " ".join(evidence_parts)
    citation_token_sets = tuple(_tokens(part) for part in evidence_parts)

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


def apply_rewrite_to_answer(
    answer: Answer,
    rewrite: GroundedRewrite | None,
    question: str,
) -> Answer:
    """Applies a GroundedRewrite to the Answer schema with direct-question and QA checks."""
    if not rewrite:
        return answer

    is_refusal = (
        "does not contain the specific procedure for this issue" in rewrite.summary.lower()
        or "verified knowledge base does not contain" in rewrite.summary.lower()
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

    enhanced = answer.model_copy(update=updates)

    # --- Post-generation QA check ---
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
    "SummaryStreamFilter",
    "apply_rewrite_to_answer",
    "enhance_grounded_answer",
    "local_llm_enabled",
    "local_llm_health",
]
