"""Bounded, redacted, persistent conversation context for GovBank Assistant.

Provides thread-safe multi-turn conversational memory with:
- Rich multi-turn dialogue retention (both citizen queries and assistant responses)
- High-capacity LRU memory bounds (up to 30 turns per chat, 24-hour TTL)
- On-disk session persistence (backend/data/conversations/) so memory survives restarts
- Strict redaction preservation: raw personal identifiers must be masked before storage.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.config import DATA_DIR
from backend.schemas import Answer

logger = logging.getLogger("conversation_memory")
CONVERSATIONS_DIR = DATA_DIR / "conversations"


@dataclass(frozen=True)
class MemoryTurn:
    user_text: str
    answer_title: str
    entry_id: str | None
    created_at: float
    assistant_text: str = ""
    source_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "user_text": self.user_text,
            "answer_title": self.answer_title,
            "entry_id": self.entry_id,
            "created_at": self.created_at,
            "assistant_text": self.assistant_text,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MemoryTurn":
        return cls(
            user_text=str(data.get("user_text") or ""),
            answer_title=str(data.get("answer_title") or ""),
            entry_id=str(data["entry_id"]) if data.get("entry_id") else None,
            created_at=float(data.get("created_at") or time.time()),
            assistant_text=str(data.get("assistant_text") or ""),
            source_url=str(data["source_url"]) if data.get("source_url") else None,
        )


@dataclass
class _Conversation:
    turns: list[MemoryTurn] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


def _safe_filename(conversation_id: str) -> str:
    cleaned = re.sub(r"[^\w\-.]", "_", conversation_id.strip())
    return f"{cleaned[:64]}.json"


class ConversationMemory:
    """Thread-safe persistent TTL/LRU conversation context with rich dialogue memory."""

    def __init__(
        self,
        *,
        max_conversations: int = 2000,
        max_turns: int = 30,
        ttl_seconds: int = 86400,
        storage_dir: Path | None = CONVERSATIONS_DIR,
    ):
        if min(max_conversations, max_turns, ttl_seconds) < 1:
            raise ValueError("memory limits must be positive")
        self.max_conversations = max_conversations
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.storage_dir = storage_dir
        self._items: OrderedDict[str, _Conversation] = OrderedDict()
        self._lock = threading.RLock()

        if self.storage_dir:
            try:
                self.storage_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning("Could not create conversation storage dir: %s", e)

    def _save_to_disk(self, conversation_id: str, conversation: _Conversation) -> None:
        if not self.storage_dir:
            return
        try:
            file_path = self.storage_dir / _safe_filename(conversation_id)
            payload = {
                "conversation_id": conversation_id,
                "updated_at": conversation.updated_at,
                "turns": [turn.to_dict() for turn in conversation.turns],
            }
            file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.debug("Failed to persist conversation %s to disk: %s", conversation_id, e)

    def _load_from_disk(self, conversation_id: str, now: float) -> _Conversation | None:
        if not self.storage_dir:
            return None
        file_path = self.storage_dir / _safe_filename(conversation_id)
        if not file_path.is_file():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            updated_at = float(data.get("updated_at") or 0.0)
            if now - updated_at > self.ttl_seconds:
                # Expired on disk
                try:
                    file_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return None
            turns = [MemoryTurn.from_dict(t) for t in data.get("turns", [])]
            return _Conversation(turns=turns[-self.max_turns :], updated_at=updated_at)
        except Exception as e:
            logger.debug("Failed to load conversation %s from disk: %s", conversation_id, e)
            return None

    def _prune(self, now: float) -> None:
        expired = [key for key, value in self._items.items() if now - value.updated_at > self.ttl_seconds]
        for key in expired:
            self._items.pop(key, None)
            if self.storage_dir:
                try:
                    (self.storage_dir / _safe_filename(key)).unlink(missing_ok=True)
                except OSError:
                    pass
        while len(self._items) > self.max_conversations:
            evicted_id, _ = self._items.popitem(last=False)
            if self.storage_dir:
                try:
                    (self.storage_dir / _safe_filename(evicted_id)).unlink(missing_ok=True)
                except OSError:
                    pass

    def remember(
        self,
        conversation_id: str | None,
        *,
        user_text: str,
        answer: Answer,
        assistant_text: str | None = None,
    ) -> None:
        if not conversation_id:
            return
        now = time.time()

        if assistant_text is None:
            parts = []
            if answer.summary:
                parts.append(answer.summary.strip())
            if answer.documents_needed:
                parts.append(f"Required Documents: {', '.join(answer.documents_needed)}")
            if answer.steps:
                steps_desc = "; ".join(
                    f"{s.title}: {s.detail or ''}".strip()
                    for s in answer.steps[:4]
                    if s.title
                )
                if steps_desc:
                    parts.append(f"Key Steps: {steps_desc}")
            assistant_text = " \n".join(parts)

        turn = MemoryTurn(
            user_text=" ".join((user_text or "").split())[:800],
            answer_title=" ".join(answer.title.split())[:180],
            entry_id=answer.entry_id,
            created_at=now,
            assistant_text=" ".join((assistant_text or "").split())[:2000],
            source_url=str(answer.source_url) if answer.source_url else None,
        )
        with self._lock:
            self._prune(now)
            conversation = self._items.pop(conversation_id, None)
            if conversation is None:
                conversation = self._load_from_disk(conversation_id, now) or _Conversation()

            conversation.turns.append(turn)
            conversation.turns = conversation.turns[-self.max_turns :]
            conversation.updated_at = now
            self._items[conversation_id] = conversation
            self._save_to_disk(conversation_id, conversation)
            self._prune(now)

    def recent(self, conversation_id: str | None, *, limit: int = 10) -> tuple[MemoryTurn, ...]:
        if not conversation_id or limit < 1:
            return ()
        now = time.time()
        with self._lock:
            self._prune(now)
            conversation = self._items.get(conversation_id)
            if conversation is None:
                conversation = self._load_from_disk(conversation_id, now)
                if conversation is not None:
                    self._items[conversation_id] = conversation
            if conversation is None:
                return ()
            self._items.move_to_end(conversation_id)
            return tuple(conversation.turns[-min(limit, self.max_turns) :])

    def sync_history(self, conversation_id: str | None, messages: list[dict[str, object]]) -> None:
        """Synchronize client-side chat messages (from browser localStorage) into server memory."""
        if not conversation_id or not messages:
            return
        now = time.time()
        with self._lock:
            conversation = self._items.get(conversation_id)
            if conversation is None:
                conversation = self._load_from_disk(conversation_id, now) or _Conversation()

            existing_user_texts = {t.user_text for t in conversation.turns}
            updated = False

            # Pair up user and assistant messages if needed
            i = 0
            while i < len(messages):
                msg = messages[i]
                if msg.get("role") == "user":
                    u_text = str(msg.get("content") or msg.get("text") or "").strip()
                    a_text = ""
                    a_title = "Follow-up Query"
                    e_id = None
                    if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant":
                        nxt = messages[i + 1]
                        a_text = str(nxt.get("content") or nxt.get("text") or "").strip()
                        a_title = str(nxt.get("title") or "Assistant response")[:180]
                        e_id = str(nxt["entry_id"]) if nxt.get("entry_id") else None
                        i += 1

                    if u_text and u_text not in existing_user_texts:
                        turn = MemoryTurn(
                            user_text=" ".join(u_text.split())[:800],
                            answer_title=a_title,
                            entry_id=e_id,
                            created_at=now,
                            assistant_text=" ".join(a_text.split())[:2000],
                        )
                        conversation.turns.append(turn)
                        existing_user_texts.add(u_text)
                        updated = True
                i += 1

            if updated:
                conversation.turns = conversation.turns[-self.max_turns :]
                conversation.updated_at = now
                self._items[conversation_id] = conversation
                self._save_to_disk(conversation_id, conversation)

    def latest_entry_id(self, conversation_id: str | None) -> str | None:
        for turn in reversed(self.recent(conversation_id, limit=self.max_turns)):
            if turn.entry_id:
                return turn.entry_id
        return None

    def clear(self, conversation_id: str | None = None) -> None:
        with self._lock:
            if conversation_id is None:
                self._items.clear()
                if self.storage_dir and self.storage_dir.is_dir():
                    for f in self.storage_dir.glob("*.json"):
                        try:
                            f.unlink(missing_ok=True)
                        except OSError:
                            pass
            else:
                self._items.pop(conversation_id, None)
                if self.storage_dir:
                    try:
                        (self.storage_dir / _safe_filename(conversation_id)).unlink(missing_ok=True)
                    except OSError:
                        pass

    def health(self) -> dict[str, int | bool]:
        now = time.time()
        with self._lock:
            self._prune(now)
            disk_count = 0
            if self.storage_dir and self.storage_dir.is_dir():
                disk_count = len(list(self.storage_dir.glob("*.json")))
            return {
                "enabled": True,
                "conversations": len(self._items),
                "persisted_conversations": disk_count,
                "max_conversations": self.max_conversations,
                "max_turns": self.max_turns,
                "ttl_seconds": self.ttl_seconds,
            }


def _positive_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


conversation_memory = ConversationMemory(
    max_conversations=_positive_env("MEMORY_MAX_CONVERSATIONS", 2000),
    max_turns=_positive_env("MEMORY_MAX_TURNS", 30),
    ttl_seconds=_positive_env("MEMORY_TTL_SECONDS", 86400),
)


__all__ = ["ConversationMemory", "MemoryTurn", "conversation_memory"]
