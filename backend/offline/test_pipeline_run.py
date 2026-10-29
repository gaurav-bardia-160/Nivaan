import os
os.environ["RAG_VECTOR_ENABLED"] = "true"

from backend.pipeline import run
from backend.schemas import AskRequest

req = AskRequest(
    question="how do I lodge a public grievance on CPGRAMS and what is the process?",
    conversation_id="test_session_cpgrams",
)

ans = run(req)
print("=" * 80)
print("PIPELINE ANSWER GENERATED SUCCESSFULLY")
print("=" * 80)
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("Title:", ans.title)
print("\nSummary:\n", ans.summary)
print("\nDocuments Needed:")
for d in ans.documents_needed:
    print(f"  - {d}")
print("\nSteps:")
for idx, s in enumerate(ans.steps, 1):
    print(f"  {idx}. {s.title}: {s.detail}")
print(f"\nOfficial Source URL: {ans.source_url}")
print(f"Confidence: {ans.confidence}")
print("\nCitations:")
for c in ans.citations:
    print(f"  - {c.title} ({c.url})")
print("=" * 80)
