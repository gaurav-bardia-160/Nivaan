"""Contextual Bandit Policy for Adaptive RAG Retrieval in GovBank Assistant.

Implements LinUCB (Linear Upper Confidence Bound) reinforcement learning
to dynamically select optimal retrieval and generation strategies based on query context.

Action Space (Arms):
- Arm 0: Conservative Precision  (top_k=2, min_score=0.035, temp=0.05)
- Arm 1: Balanced Official       (top_k=3, min_score=0.028, temp=0.10) [Default]
- Arm 2: Broad Comprehensive     (top_k=5, min_score=0.020, temp=0.15)
- Arm 3: Focused Actionable      (top_k=3, min_score=0.030, temp=0.08)
- Arm 4: Multi-Pass Deep Search  (top_k=4, min_score=0.025, temp=0.10)
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR

logger = logging.getLogger("bandit_policy")
BANDIT_STATE_FILE = DATA_DIR / "feedback" / "bandit_weights.json"

ARMS = [
    {"arm_id": 0, "name": "conservative_precision", "top_k": 2, "min_score": 0.035, "temperature": 0.05},
    {"arm_id": 1, "name": "balanced_official",      "top_k": 3, "min_score": 0.028, "temperature": 0.10},
    {"arm_id": 2, "name": "broad_comprehensive",    "top_k": 5, "min_score": 0.020, "temperature": 0.15},
    {"arm_id": 3, "name": "focused_actionable",     "top_k": 3, "min_score": 0.030, "temperature": 0.08},
    {"arm_id": 4, "name": "multi_pass_deep",        "top_k": 4, "min_score": 0.025, "temperature": 0.10},
]
FEATURE_DIM = 7


@dataclass
class BanditAction:
    arm_id: int
    name: str
    top_k: int
    min_score: float
    temperature: float
    context_vector: list[float]


class LinUCBBanditPolicy:
    """Contextual Linear Upper Confidence Bound bandit policy for RAG."""

    def __init__(
        self,
        alpha: float = 0.6,
        feature_dim: int = FEATURE_DIM,
        state_file: Path = BANDIT_STATE_FILE,
    ):
        self.alpha = alpha
        self.d = feature_dim
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # Matrices: A[a] is dxd (init as identity), b[a] is dx1 (init as zeros)
        self.A: list[list[list[float]]] = [
            [[1.0 if i == j else 0.0 for j in range(self.d)] for i in range(self.d)]
            for _ in range(len(ARMS))
        ]
        self.b: list[list[float]] = [[0.0 for _ in range(self.d)] for _ in range(len(ARMS))]
        self.pull_counts: list[int] = [0 for _ in range(len(ARMS))]
        self.total_reward: list[float] = [0.0 for _ in range(len(ARMS))]
        self._action_cache: dict[str, BanditAction] = {}

        self._load_state()

    def _load_state(self) -> None:
        if not self.state_file.is_file():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if "A" in data and "b" in data:
                self.A = data["A"]
                self.b = data["b"]
                self.pull_counts = data.get("pull_counts", self.pull_counts)
                self.total_reward = data.get("total_reward", self.total_reward)
        except Exception as e:
            logger.debug("Could not load bandit weights: %s", e)

    def _save_state(self) -> None:
        try:
            payload = {
                "alpha": self.alpha,
                "A": self.A,
                "b": self.b,
                "pull_counts": self.pull_counts,
                "total_reward": self.total_reward,
            }
            self.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Could not save bandit weights: %s", e)

    def extract_context(self, query: str, is_followup: bool = False) -> list[float]:
        q = query.lower()
        words = q.split()
        return [
            1.0,  # Bias term
            1.0 if any(w in q for w in ("tax", "itr", "gst", "tds", "pan")) else 0.0,
            1.0 if any(w in q for w in ("passport", "visa", "court", "legal", "fir", "police")) else 0.0,
            1.0 if any(w in q for w in ("scheme", "subsidy", "samagra", "kisan", "yojana")) else 0.0,
            1.0 if is_followup or any(w in q for w in ("that", "these", "this", "fee", "how much", "documents")) else 0.0,
            1.0 if len(words) <= 5 else 0.0,
            1.0 if len(words) >= 12 else 0.0,
        ]

    def _invert_matrix(self, matrix: list[list[float]]) -> list[list[float]]:
        # Lightweight Gauss-Jordan inversion for small 7x7 matrix
        n = len(matrix)
        augmented = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
        for i in range(n):
            pivot = augmented[i][i]
            if abs(pivot) < 1e-9:
                pivot = 1e-9
            for j in range(2 * n):
                augmented[i][j] /= pivot
            for k in range(n):
                if k != i:
                    factor = augmented[k][i]
                    for j in range(2 * n):
                        augmented[k][j] -= factor * augmented[i][j]
        return [row[n:] for row in augmented]

    def select_action(self, query: str, is_followup: bool = False) -> BanditAction:
        x = self.extract_context(query, is_followup)
        best_arm = 1
        best_p = -float("inf")

        with self._lock:
            for a in range(len(ARMS)):
                A_inv = self._invert_matrix(self.A[a])
                # theta_a = A_inv * b[a]
                theta_a = [sum(A_inv[i][j] * self.b[a][j] for j in range(self.d)) for i in range(self.d)]
                # mean = theta_a^T * x
                mean = sum(theta_a[i] * x[i] for i in range(self.d))
                # var = x^T * A_inv * x
                var = sum(x[i] * sum(A_inv[i][j] * x[j] for j in range(self.d)) for i in range(self.d))
                ucb = self.alpha * math.sqrt(max(var, 0.0))
                p = mean + ucb

                if p > best_p:
                    best_p = p
                    best_arm = a

        chosen = ARMS[best_arm]
        return BanditAction(
            arm_id=chosen["arm_id"],
            name=chosen["name"],
            top_k=chosen["top_k"],
            min_score=chosen["min_score"],
            temperature=chosen["temperature"],
            context_vector=x,
        )

    def record_action(self, conversation_id: str | None, query: str, action: BanditAction) -> None:
        """Cache the action taken for a conversation query to correlate with future feedback."""
        key = f"{conversation_id or ''}::{query.strip().lower()}"
        with self._lock:
            self._action_cache[key] = action
            if len(self._action_cache) > 2000:
                oldest = next(iter(self._action_cache))
                self._action_cache.pop(oldest, None)

    def get_action(self, conversation_id: str | None, query: str) -> BanditAction | None:
        """Retrieve recent action taken for this query context."""
        key = f"{conversation_id or ''}::{query.strip().lower()}"
        with self._lock:
            if key in self._action_cache:
                return self._action_cache[key]
            # Suffix match on query
            clean_q = query.strip().lower()
            for k, act in reversed(list(self._action_cache.items())):
                if k.endswith(f"::{clean_q}"):
                    return act
        return None

    def update(self, action: BanditAction, reward: float) -> None:
        """Update LinUCB policy parameters using observed reward."""
        a = action.arm_id
        x = action.context_vector
        with self._lock:
            self.pull_counts[a] += 1
            self.total_reward[a] += reward

            # A[a] += x * x^T
            for i in range(self.d):
                for j in range(self.d):
                    self.A[a][i][j] += x[i] * x[j]

            # b[a] += reward * x
            for i in range(self.d):
                self.b[a][i] += reward * x[i]

            self._save_state()

    def get_stats(self) -> dict[str, object]:
        with self._lock:
            arm_stats = []
            for a in range(len(ARMS)):
                count = self.pull_counts[a]
                tot = self.total_reward[a]
                arm_stats.append({
                    "arm_id": a,
                    "name": ARMS[a]["name"],
                    "top_k": ARMS[a]["top_k"],
                    "temperature": ARMS[a]["temperature"],
                    "pull_count": count,
                    "avg_reward": round(tot / count, 3) if count > 0 else 0.0,
                })
            return {
                "algorithm": "LinUCB",
                "alpha": self.alpha,
                "arms": arm_stats,
            }


bandit_policy = LinUCBBanditPolicy()

__all__ = ["LinUCBBanditPolicy", "BanditAction", "bandit_policy", "ARMS"]
