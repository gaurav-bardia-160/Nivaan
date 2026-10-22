"""Privacy-preserving Ollama-compatible grounded answer enhancement.

The local model is optional and disabled by default. It can rewrite an already-grounded
extractive summary for readability, but it cannot replace citations, steps, warnings,
source metadata, or confidence. Any error returns the deterministic answer unchanged.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.modules.memory import MemoryTurn
from backend.schemas import Answer

_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class GroundedRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=20, max_length=1200)

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

    @classmethod
    def from_env(cls) -> "LocalLLMConfig":
        raw_timeout = os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "20")
        try:
            timeout = float(raw_timeout)
        except ValueError:
            timeout = 20.0
        return cls(
            enabled=os.getenv("LOCAL_LLM_ENABLED", "false").strip().lower() in _TRUE_VALUES,
            base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            model=os.getenv("LOCAL_LLM_MODEL", "qwen3.5:4b").strip() or "qwen3.5:4b",
            timeout_seconds=min(max(timeout, 1.0), 120.0),
            allow_remote=os.getenv("LOCAL_LLM_ALLOW_REMOTE", "false").strip().lower() in _TRUE_VALUES,
        )

    def validate_privacy_boundary(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("LOCAL_LLM_BASE_URL must be a valid HTTP URL")
        if not self.allow_remote and parsed.hostname.lower() not in _LOCAL_HOSTS:
            raise ValueError("Remote LLM endpoints require LOCAL_LLM_ALLOW_REMOTE=true")


class LocalLLMClient:
    def __init__(self, config: LocalLLMConfig | None = None):
        self.config = config or LocalLLMConfig.from_env()
        self.config.validate_privacy_boundary()

    def available(self) -> bool:
        if not self.config.enabled:
            return False
        try:
            response = httpx.get(f"{self.config.base_url}/api/tags", timeout=min(self.config.timeout_seconds, 2.0))
            return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    def rewrite_summary(
        self,
        *,
        question: str,
        answer: Answer,
        memory: tuple[MemoryTurn, ...] = (),
    ) -> str | None:
        if not self.config.enabled or not answer.citations:
            return None

        evidence = []
        for index, citation in enumerate(answer.citations[:5], 1):
            evidence.append(f"[{index}] {citation.title}\n{citation.excerpt}\nSource: {citation.url}")
        history = "\n".join(
            f"User: {turn.user_text}\nAssistant topic: {turn.answer_title}"
            for turn in memory[-4:]
        ) or "No previous context."
        evidence_text = "\n\n".join(evidence)

        system = (
            "You are GovBank Assistant, a civic information explainer. Rewrite the answer as one clear, "
            "concise paragraph using only the supplied evidence. Never invent fees, deadlines, eligibility, "
            "documents, laws, or procedures. If evidence is incomplete, state that limitation. Do not give a "
            "legal, tax, or financial verdict. Return JSON only with exactly one key: summary."
        )
        prompt = (
            f"Conversation context (already redacted):\n{history}\n\n"
            f"Citizen question (already redacted):\n{question[:1200]}\n\n"
            f"Official-source evidence:\n{evidence_text}"
        )
        payload = {
            "model": self.config.model,
            "stream": False,
            "format": "json",
            "think": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0, "num_predict": 350},
        }
        try:
            response = httpx.post(
                f"{self.config.base_url}/api/chat",
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body.get("message", {}).get("content", "")
            parsed = GroundedRewrite.model_validate(json.loads(content))
        except (httpx.HTTPError, OSError, ValueError, TypeError, json.JSONDecodeError, ValidationError):
            return None

        if not _is_grounded(parsed.summary, answer):
            return None
        return parsed.summary


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text.lower())
        if token not in {"the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "can"}
    }


def _is_grounded(summary: str, answer: Answer) -> bool:
    summary_tokens = _tokens(summary)
    if not summary_tokens:
        return False
    evidence_text = " ".join(citation.excerpt for citation in answer.citations)
    evidence_tokens = _tokens(evidence_text)
    overlap = len(summary_tokens & evidence_tokens) / max(len(summary_tokens), 1)
    return overlap >= 0.35


_health_lock = threading.Lock()
_health_cache: tuple[float, dict[str, object]] | None = None


def local_llm_enabled() -> bool:
    return LocalLLMConfig.from_env().enabled


def local_llm_health(*, force: bool = False) -> dict[str, object]:
    global _health_cache
    config = LocalLLMConfig.from_env()
    base = {
        "enabled": config.enabled,
        "provider": "ollama_compatible",
        "model": config.model,
        "base_url": config.base_url,
        "privacy_mode": "local_only" if not config.allow_remote else "remote_explicitly_allowed",
    }
    if not config.enabled:
        return {**base, "available": False}

    now = time.time()
    with _health_lock:
        if not force and _health_cache and now - _health_cache[0] < 10:
            return _health_cache[1]
        try:
            available = LocalLLMClient(config).available()
            result = {**base, "available": available}
        except ValueError as exc:
            result = {**base, "available": False, "error": str(exc)}
        _health_cache = (now, result)
        return result


def enhance_grounded_answer(
    answer: Answer,
    *,
    question: str,
    memory: tuple[MemoryTurn, ...] = (),
) -> Answer:
    """Return a locally rewritten summary or the exact deterministic answer on failure."""
    try:
        rewrite = LocalLLMClient().rewrite_summary(question=question, answer=answer, memory=memory)
    except ValueError:
        rewrite = None
    if not rewrite:
        return answer
    return answer.model_copy(update={"summary": rewrite})


__all__ = [
    "GroundedRewrite",
    "LocalLLMClient",
    "LocalLLMConfig",
    "enhance_grounded_answer",
    "local_llm_enabled",
    "local_llm_health",
]
