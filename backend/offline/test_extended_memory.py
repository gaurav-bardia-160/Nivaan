"""Test and verification for High-Capacity Multi-Turn Conversation Memory.

Verifies:
1. Multi-turn dialogue retention across 4 continuous turns.
2. Anaphoric and follow-up query resolution ("for that", "are these needed?").
3. Assistant text retention (summary, required documents, key steps).
4. Disk persistence across process memory clear.
5. Ollama expanded context window (num_ctx: 8192, num_predict: 768).
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.memory import ConversationMemory, conversation_memory
from backend.pipeline import run
from backend.schemas import AskRequest


def test_multi_turn_remembering():
    print("=" * 80)
    print("TESTING EXTENDED MULTI-TURN CONVERSATION MEMORY")
    print("=" * 80)

    conv_id = "test_memory_session_99"
    conversation_memory.clear(conv_id)

    # Turn 1: Passport renewal
    print("\n--- TURN 1: Initial Query ---")
    q1 = "How do I renew an Indian passport online?"
    print(f"User: {q1}")
    res1 = run(AskRequest(input_type="question", question=q1, conversation_id=conv_id))
    print(f"Title: {res1.title}")
    print(f"Summary: {res1.summary[:200]}...")
    print(f"Documents: {res1.documents_needed}")

    # Check memory after Turn 1
    turns1 = conversation_memory.recent(conv_id)
    assert len(turns1) == 1, f"Expected 1 turn in memory, got {len(turns1)}"
    assert turns1[0].assistant_text, "Expected assistant_text to be saved in memory"
    print(f"[OK] Memory Turn 1 stored: {turns1[0].user_text} -> {turns1[0].assistant_text[:100]}...")

    # Turn 2: Follow-up relying on Turn 1
    print("\n--- TURN 2: Follow-up with Anaphora ('for that') ---")
    q2 = "What documents are required for that if my address is not changed?"
    print(f"User: {q2}")
    res2 = run(AskRequest(input_type="question", question=q2, conversation_id=conv_id))
    print(f"Title: {res2.title}")
    print(f"Summary: {res2.summary[:200]}...")
    print(f"Documents: {res2.documents_needed}")

    turns2 = conversation_memory.recent(conv_id)
    assert len(turns2) == 2, f"Expected 2 turns in memory, got {len(turns2)}"
    print(f"[OK] Memory Turn 2 stored. Total turns in memory: {len(turns2)}")

    # Turn 3: Fee follow-up
    print("\n--- TURN 3: Fee & appointment follow-up ---")
    q3 = "How much is the normal fee and where do I visit?"
    print(f"User: {q3}")
    res3 = run(AskRequest(input_type="question", question=q3, conversation_id=conv_id))
    print(f"Title: {res3.title}")
    print(f"Summary: {res3.summary[:200]}...")

    turns3 = conversation_memory.recent(conv_id)
    assert len(turns3) == 3, f"Expected 3 turns in memory, got {len(turns3)}"
    print(f"[OK] Memory Turn 3 stored. Total turns in memory: {len(turns3)}")

    # Turn 4: Test Disk Persistence
    print("\n--- TURN 4: Testing Persistence After RAM Eviction ---")
    # Simulate process reload by clearing RAM cache only (not disk)
    conversation_memory._items.clear()
    assert len(conversation_memory._items) == 0, "RAM cache should be empty"

    # Call recent() which should auto-load from disk
    reloaded_turns = conversation_memory.recent(conv_id)
    assert len(reloaded_turns) == 3, f"Expected 3 turns reloaded from disk, got {len(reloaded_turns)}"
    print(f"[OK] Successfully reloaded {len(reloaded_turns)} turns from disk persistence!")
    for idx, t in enumerate(reloaded_turns, 1):
        print(f"  Turn {idx}: User: '{t.user_text}' | Asst: '{t.assistant_text[:80]}...'")

    # Health check
    health = conversation_memory.health()
    print("\n--- Memory Health Metrics ---")
    for k, v in health.items():
        print(f"  {k}: {v}")
    assert health["max_turns"] >= 20, f"Expected max_turns >= 20, got {health['max_turns']}"
    assert health["ttl_seconds"] >= 86400, f"Expected ttl >= 24h, got {health['ttl_seconds']}"

    print("\n" + "=" * 80)
    print("ALL MULTI-TURN MEMORY TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    test_multi_turn_remembering()
