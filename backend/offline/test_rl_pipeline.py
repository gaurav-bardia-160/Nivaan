"""End-to-End Test Suite for Reinforcement Learning (RL) in GovBank Assistant.

Verifies:
1. RewardEngine (Grounding, Citations, Completeness, Privacy enforcement, User signals)
2. LinUCBBanditPolicy (Action selection, covariance updates, state persistence)
3. End-to-End Pipeline integration (Bandit arm attribution on answers)
4. Feedback & RL status API endpoints
5. DPO Preference Dataset curation
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.bandit_policy import ARMS, BanditAction, LinUCBBanditPolicy
from backend.modules.reward import RewardEngine
from backend.pipeline import run
from backend.schemas import Answer, AskRequest, Citation, FeedbackRequest, Step
from backend.offline.rl_dpo_pipeline import extract_preference_pairs


def test_reward_engine():
    print("[TEST 1/5] Testing RewardEngine...")
    temp_dir = Path(tempfile.mkdtemp())
    log_file = temp_dir / "test_feedback.jsonl"
    engine = RewardEngine(feedback_file=log_file)

    good_answer = Answer(
        title="Apply for New PAN Card",
        summary="Submit Form 49A on the Protean e-Gov portal with Aadhaar for online identity verification.",
        documents_needed=["Aadhaar Card", "Proof of Address"],
        steps=[
            Step(title="Visit Portal", detail="Go to onlineservices.nsdl.com"),
            Step(title="Submit Form", detail="Fill Form 49A and authenticate using Aadhaar OTP"),
        ],
        source_url="https://www.onlineservices.nsdl.com",
        citations=[
            Citation(
                title="Protean PAN Portal",
                url="https://tin.tin.nsdl.com/pan",
                excerpt="Online application for PAN through Form 49A",
                reported_last_verified=date.today(),
                factual_verification="verified",
            )
        ],
        last_verified=date.today(),
        confidence="high",
    )

    # 1. Grounded & verified answer should get high positive reward
    reward = engine.compute_reward(
        query="How to apply for PAN card?",
        answer=good_answer,
        evidence_text="Apply for PAN card online on onlineservices.nsdl.com Form 49A using Aadhaar",
    )
    assert reward.total_reward > 0.3, f"Expected positive reward, got {reward.total_reward}"
    assert reward.citations > 0, "Expected positive citation reward for .nsdl.com"
    assert reward.completeness > 0.5, "Expected high completeness for steps and docs"
    assert reward.privacy_penalty == 0.0, "Expected zero penalty for clean answer"

    # 2. Privacy violation check: Raw unmasked Aadhaar leak must be heavily penalized (-2.0)
    leak_answer = good_answer.model_copy(
        update={"summary": "Here is citizen Aadhaar 2345 6789 0123 leaked in plain text."}
    )
    penalized_reward = engine.compute_reward(
        query="Check Aadhaar",
        answer=leak_answer,
        evidence_text="",
    )
    assert penalized_reward.privacy_penalty == -2.0, "Expected -2.0 penalty for unmasked Aadhaar"
    assert penalized_reward.total_reward < 0.0, "Total reward must be negative on PII leak"

    # 3. User feedback incorporation
    fb = FeedbackRequest(
        query="How to apply for PAN?",
        answer_title="Apply for New PAN Card",
        feedback_type="thumbs_up",
        rating=1,
    )
    user_reward = engine.compute_reward(
        query="How to apply for PAN?",
        answer=good_answer,
        evidence_text="evidence",
        feedback=fb,
    )
    assert user_reward.user_feedback == 1.0

    # 4. Feedback logging and stats
    engine.log_feedback(fb, user_reward)
    stats = engine.get_stats()
    assert stats["total_feedbacks"] == 1
    assert stats["thumbs_up"] == 1
    assert stats["average_reward"] > 0

    shutil.rmtree(temp_dir, ignore_errors=True)
    print("  -> RewardEngine tests PASSED.")


def test_bandit_policy():
    print("[TEST 2/5] Testing LinUCBBanditPolicy...")
    temp_dir = Path(tempfile.mkdtemp())
    state_file = temp_dir / "test_weights.json"
    policy = LinUCBBanditPolicy(state_file=state_file)

    # 1. Select action for tax query
    act1 = policy.select_action("What are income tax slab rates for FY 2024-25?")
    assert isinstance(act1, BanditAction)
    assert 0 <= act1.arm_id < len(ARMS)
    assert act1.top_k in (2, 3, 4, 5)

    # 2. Update with high reward and verify pull count and matrix adaptation
    init_pulls = policy.pull_counts[act1.arm_id]
    policy.update(act1, reward=1.5)
    assert policy.pull_counts[act1.arm_id] == init_pulls + 1
    assert policy.total_reward[act1.arm_id] == 1.5

    # 3. Verify persistence
    assert state_file.is_file()
    reloaded_policy = LinUCBBanditPolicy(state_file=state_file)
    assert reloaded_policy.pull_counts[act1.arm_id] == init_pulls + 1

    # 4. Action cache correlation
    policy.record_action("conv_123", "apply for passport", act1)
    retrieved = policy.get_action("conv_123", "apply for passport")
    assert retrieved is not None
    assert retrieved.arm_id == act1.arm_id

    shutil.rmtree(temp_dir, ignore_errors=True)
    print("  -> LinUCBBanditPolicy tests PASSED.")


def test_pipeline_integration():
    print("[TEST 3/5] Testing Pipeline End-to-End Attribution...")
    # Greeting query
    res_greet = run(AskRequest(question="Hello"))
    assert res_greet.rl_arm is not None, f"Expected rl_arm on answer, got {res_greet.rl_arm}"

    # Verified civic guide query
    res_pan = run(AskRequest(question="How to apply for a PAN card?"))
    assert res_pan.rl_arm is not None
    assert "pan" in res_pan.title.lower()

    print("  -> Pipeline integration tests PASSED.")


def test_api_endpoints():
    print("[TEST 4/5] Testing API Endpoints (/api/feedback, /api/rl-status)...")
    client = TestClient(app)

    # 1. Feedback submission
    fb_payload = {
        "conversation_id": "test_conv_999",
        "query": "How to register voter id?",
        "answer_title": "Voter ID Registration",
        "feedback_type": "thumbs_up",
        "rating": 1,
        "comment": "Very clear instructions!",
    }
    resp = client.post("/api/feedback", json=fb_payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert "reward" in data
    assert "breakdown" in data
    assert "applied_arm" in data

    # 2. RL status endpoint
    resp_status = client.get("/api/rl-status")
    assert resp_status.status_code == 200
    st_data = resp_status.json()
    assert st_data["status"] == "healthy"
    assert "bandit" in st_data
    assert "rewards" in st_data
    assert st_data["bandit"]["algorithm"] == "LinUCB"

    # 3. Metrics endpoint
    resp_metrics = client.get("/api/metrics")
    assert resp_metrics.status_code == 200
    met_data = resp_metrics.json()
    assert "rl" in met_data
    assert "bandit" in met_data["rl"]

    print("  -> API endpoint tests PASSED.")


def test_dpo_preference_extraction():
    print("[TEST 5/5] Testing DPO Preference Extraction...")
    pairs = extract_preference_pairs(include_seed=True)
    assert len(pairs) >= 5
    for p in pairs:
        assert "prompt" in p and len(p["prompt"]) > 0
        assert "chosen" in p and len(p["chosen"]) > 0
        assert "rejected" in p and len(p["rejected"]) > 0
        assert p["chosen"] != p["rejected"]
    print("  -> DPO preference extraction tests PASSED.")


def main():
    print("=====================================================================")
    print("      GovBank Assistant - Reinforcement Learning Test Suite           ")
    print("=====================================================================")
    test_reward_engine()
    test_bandit_policy()
    test_pipeline_integration()
    test_api_endpoints()
    test_dpo_preference_extraction()
    print("=====================================================================")
    print("               ALL REINFORCEMENT LEARNING TESTS PASSED!              ")
    print("=====================================================================")


if __name__ == "__main__":
    main()
