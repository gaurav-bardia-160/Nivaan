"""Bounded, redacted, in-memory conversation context.

The store is intentionally process-local and never persists uploaded documents or raw
personal identifiers. Callers must pass text after server-side masking.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from backend.schemas import Answer


@dataclass(frozen=True)
class MemoryTurn:
    user_text: str
    answer_title: str
    entry_id: str | None
    created_at: float


@dataclass
class _Conversation:
    turns: list[MemoryTurn] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


class ConversationMemory:
    """Thread-safe TTL/LRU conversation context with strict size bounds."""

    def __init__(self, *, max_conversations: int = 500, max_turns: int = 6, ttl_seconds: int = 1800):
        if min(max_conversations, max_turns, ttl_seconds) < 1:
            raise ValueError("memory limits must be positive")
        self.max_conversations = max_conversations
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, _Conversation] = OrderedDict()
        self._lock = threading.RLock()

    def _prune(self, now: float) -> None:
        expired = [key for key, value in self._items.items() if now - value.updated_at > self.ttl_seconds]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) > self.max_conversations:
            self._items.popitem(last=False)

    def remember(self, conversation_id: str | None, *, user_text: str, answer: Answer) -> None:
        if not conversation_id:
            return
        now = time.time()
        turn = MemoryTurn(
            user_text=" ".join((user_text or "").split())[:400],
            answer_title=" ".join(answer.title.split())[:180],
            entry_id=answer.entry_id,
            created_at=now,
        )
        with self._lock:
            self._prune(now)
            conversation = self._items.pop(conversation_id, _Conversation())
            conversation.turns.append(turn)
            conversation.turns = conversation.turns[-self.max_turns :]
            conversation.updated_at = now
            self._items[conversation_id] = conversation
            self._prune(now)

    def recent(self, conversation_id: str | None, *, limit: int = 4) -> tuple[MemoryTurn, ...]:
        if not conversation_id or limit < 1:
            return ()
        now = time.time()
        with self._lock:
            self._prune(now)
            conversation = self._items.get(conversation_id)
            if conversation is None:
                return ()
            self._items.move_to_end(conversation_id)
            return tuple(conversation.turns[-min(limit, self.max_turns) :])

    def latest_entry_id(self, conversation_id: str | None) -> str | None:
        for turn in reversed(self.recent(conversation_id, limit=self.max_turns)):
            if turn.entry_id:
                return turn.entry_id
        return None

    def clear(self, conversation_id: str | None = None) -> None:
        with self._lock:
            if conversation_id is None:
                self._items.clear()
            else:
                self._items.pop(conversation_id, None)

    def health(self) -> dict[str, int | bool]:
        now = time.time()
        with self._lock:
            self._prune(now)
            return {
                "enabled": True,
                "conversations": len(self._items),
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
    max_conversations=_positive_env("MEMORY_MAX_CONVERSATIONS", 500),
    max_turns=_positive_env("MEMORY_MAX_TURNS", 6),
    ttl_seconds=_positive_env("MEMORY_TTL_SECONDS", 1800),
)


__all__ = ["ConversationMemory", "MemoryTurn", "conversation_memory"]
