import os
import json
os.environ["RAG_VECTOR_ENABLED"] = "true"

from backend.modules.query_engine import answer_query

query = "how do I lodge a public grievance on CPGRAMS and what is the process?"
print("Testing query:", query)
ans = answer_query(query)
print("\n=== AI ANSWER GENERATED ===")
print("Summary:", ans.summary)
print("\nDocuments Needed:", ans.documents_needed)
print("\nSteps:", ans.steps)
print("\nOfficial Sources:", [(s.title, s.url) for s in ans.sources])
