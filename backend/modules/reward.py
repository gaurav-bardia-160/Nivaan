"""Multi-Criteria Reward Engine for Reinforcement Learning in GovBank Assistant.

Calculates composite reward signals to guide RL agents, Contextual Bandits,
and Direct Preference Optimization (DPO).

Reward Component Formulation:
1. R_ground: Semantic/lexical overlap with official retrieved corpus [0.0, 1.0]
2. R_cite:   Verified .gov.in/.nic.in domain citation presence [+1.0] vs hallucination [-1.0]
3. R_comp:   Presence of concrete documents and actionable steps [0.0, 1.0]
4. R_priv:   Privacy preservation (massive penalty -2.0 if unmasked PII leaks)
5. R_user:   Explicit and implicit user feedback (+1.0 thumbs up, -1.0 thumbs down, +0.5 copy/click)
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from backend.config import DATA_DIR
from backend.modules.guardrails import find_flags
from backend.schemas import Answer, FeedbackRequest

logger = logging.getLogger("reward_engine")
FEEDBACK_DIR = DATA_DIR / "feedback"
FEEDBACK_LOG_FILE = FEEDBACK_DIR / "feedback_log.jsonl"


@dataclass(frozen=True)
class RewardBreakdown:
    grounding: float
    citations: float
    completeness: float
    privacy_penalty: float
    user_feedback: float
    total_reward: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


class RewardEngine:
    def __init__(self, feedback_file: Path = FEEDBACK_LOG_FILE):
        self.feedback_file = feedback_file
        self.feedback_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._counts = {
            "total_feedbacks": 0,
            "thumbs_up": 0,
            "thumbs_down": 0,
            "citation_clicks": 0,
            "copy_events": 0,
            "rewards": [],
        }
        self._init_counts()

    def _init_counts(self) -> None:
        if not self.feedback_file.is_file():
            return
        try:
            with self.feedback_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    self._counts["total_feedbacks"] += 1
                    ftype = data.get("feedback_type")
                    if ftype == "thumbs_up":
                        self._counts["thumbs_up"] += 1
                    elif ftype == "thumbs_down":
                        self._counts["thumbs_down"] += 1
                    elif ftype == "click_citation":
                        self._counts["citation_clicks"] += 1
                    elif ftype == "copy_steps":
                        self._counts["copy_events"] += 1
                    r_val = data.get("reward", {}).get("total_reward")
                    if r_val is not None:
                        self._counts["rewards"].append(float(r_val))
        except Exception:
            pass

    def evaluate_grounding(self, summary: str, evidence_text: str) -> float:
        if not summary or not evidence_text:
            return 0.2
        sum_tokens = set(re.findall(r"[a-z0-9]{3,}", summary.lower()))
        ev_tokens = set(re.findall(r"[a-z0-9]{3,}", evidence_text.lower()))
        if not sum_tokens or not ev_tokens:
            return 0.2
        overlap = len(sum_tokens & ev_tokens) / max(len(sum_tokens), 1)
        return min(max(overlap * 2.0, 0.0), 1.0)

    def evaluate_citations(self, answer: Answer) -> float:
        if not answer.citations and not answer.source_url:
            return 0.0
        score = 0.0
        urls = [str(c.url) for c in answer.citations]
        if answer.source_url:
            urls.append(str(answer.source_url))

        for u in urls:
            host = urlsplit(u).hostname or ""
            if any(host.endswith(tld) for tld in (".gov.in", ".nic.in", ".ac.in", ".org.in", ".in", ".nsdl.com", ".utiitsl.com")):
                score += 0.5
            else:
                score -= 1.0
        return min(max(score, -1.0), 1.0)

    def evaluate_completeness(self, answer: Answer) -> float:
        score = 0.0
        if len(answer.summary.split()) >= 25:
            score += 0.3
        if answer.documents_needed and len(answer.documents_needed) > 0:
            score += 0.35
        if answer.steps and len(answer.steps) >= 2:
            score += 0.35
        return min(max(score, 0.0), 1.0)

    def evaluate_privacy(self, text: str) -> float:
        """Penalize heavily if raw unmasked PII (PAN, Aadhaar, Phone) appears in output."""
        flags = find_flags(text)
        if any(f.severity == "critical" for f in flags):
            return -2.0
        # Check raw 12 digit Aadhaar
        if re.search(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b", text):
            return -2.0
        # Check raw PAN pattern
        if re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", text):
            return -2.0
        return 0.0

    def compute_reward(
        self,
        *,
        query: str,
        answer: Answer | None = None,
        evidence_text: str = "",
        feedback: FeedbackRequest | None = None,
    ) -> RewardBreakdown:
        r_ground = self.evaluate_grounding(answer.summary, evidence_text) if answer and answer.summary else 0.5
        r_cite = self.evaluate_citations(answer) if answer else 0.0
        r_comp = self.evaluate_completeness(answer) if answer else 0.5
        r_priv = self.evaluate_privacy(answer.summary) if answer and answer.summary else 0.0

        r_user = 0.0
        if feedback:
            if feedback.feedback_type == "thumbs_up" or feedback.rating == 1:
                r_user = 1.0
            elif feedback.feedback_type == "thumbs_down" or feedback.rating == -1:
                r_user = -1.0
            elif feedback.feedback_type in ("copy_steps", "click_citation"):
                r_user = 0.5
            elif feedback.feedback_type == "corrective_follow_up":
                r_user = -0.5

        if feedback and feedback.reward is not None:
            total = feedback.reward
        else:
            # Composite weighted formula
            total = (
                0.35 * r_ground
                + 0.25 * r_cite
                + 0.15 * r_comp
                + 1.0 * r_priv
                + 0.25 * r_user
            )

        return RewardBreakdown(
            grounding=round(r_ground, 3),
            citations=round(r_cite, 3),
            completeness=round(r_comp, 3),
            privacy_penalty=round(r_priv, 3),
            user_feedback=round(r_user, 3),
            total_reward=round(total, 3),
        )

    def log_feedback(
        self,
        feedback: FeedbackRequest,
        reward_breakdown: RewardBreakdown | None = None,
        chosen_response: str | None = None,
        rejected_response: str | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "conversation_id": feedback.conversation_id,
            "query": feedback.query,
            "answer_title": feedback.answer_title,
            "answer_summary": feedback.answer_summary,
            "url": feedback.url,
            "feedback_type": feedback.feedback_type,
            "rating": feedback.rating,
            "comment": feedback.comment,
            "reward": reward_breakdown.to_dict() if reward_breakdown else {"total_reward": feedback.reward or 0.0},
            "chosen": chosen_response or (feedback.answer_summary if (feedback.rating or 0) > 0 or feedback.feedback_type == "thumbs_up" else None),
            "rejected": rejected_response or (feedback.answer_summary if (feedback.rating or 0) < 0 or feedback.feedback_type == "thumbs_down" else None),
        }
        with self._lock:
            with self.feedback_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._counts["total_feedbacks"] += 1
            if feedback.feedback_type == "thumbs_up":
                self._counts["thumbs_up"] += 1
            elif feedback.feedback_type == "thumbs_down":
                self._counts["thumbs_down"] += 1
            elif feedback.feedback_type == "click_citation":
                self._counts["citation_clicks"] += 1
            elif feedback.feedback_type == "copy_steps":
                self._counts["copy_events"] += 1
            tot = reward_breakdown.total_reward if reward_breakdown else (feedback.reward or 0.0)
            self._counts["rewards"].append(float(tot))

    def get_stats(self) -> dict[str, object]:
        with self._lock:
            rewards = self._counts["rewards"]
            avg_reward = round(sum(rewards) / len(rewards), 3) if rewards else 0.0
            return {
                "total_feedbacks": self._counts["total_feedbacks"],
                "thumbs_up": self._counts["thumbs_up"],
                "thumbs_down": self._counts["thumbs_down"],
                "citation_clicks": self._counts["citation_clicks"],
                "copy_events": self._counts["copy_events"],
                "average_reward": avg_reward,
            }


reward_engine = RewardEngine()

__all__ = ["RewardEngine", "RewardBreakdown", "reward_engine"]
