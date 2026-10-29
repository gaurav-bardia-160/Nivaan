import os
os.environ["RAG_ENABLED"] = "true"
os.environ["RAG_VECTOR_ENABLED"] = "true"

from backend.rag.runtime import rag_health, retrieve_if_enabled
from backend.pipeline import run
from backend.schemas import AskRequest

print("=" * 70)
print("1. RAG HEALTH CHECK")
print("=" * 70)
health = rag_health()
for k, v in health.items():
    print(f"  {k}: {v}")

print("\n" + "=" * 70)
print("2. HYBRID VECTOR SEARCH TEST ACROSS PORTALS")
print("=" * 70)
test_queries = [
    ("National Cyber Crime Reporting", "How to report financial cyber fraud on national cybercrime portal 1930 helpline"),
    ("GIGW 3.0 Guidelines", "GIGW 3.0 accessibility guidelines compliance for government websites"),
    ("NTA Exams Portal", "NTA national testing agency entrance examination admit card slip download"),
    ("myScheme Portal", "Central government welfare schemes eligibility criteria application myScheme"),
    ("MEA Portal", "Ministry of External Affairs consular services attestation apostille procedures"),
    ("APAAR Education Registry", "APAAR ID creation for students automated permanent academic account registry"),
]

for label, q in test_queries:
    print(f"\n[Test Query: {label}]")
    print(f"Query: \"{q}\"")
    res = retrieve_if_enabled(q, top_k=2)
    if res and res.hits:
        print(f"Status: OK ({len(res.hits)} hits retrieved)")
        for i, hit in enumerate(res.hits, 1):
            print(f"  Hit #{i} | Score: {hit.score:.4f} | Category: {hit.document.category}")
            print(f"         ID: {hit.document.id}")
            src = hit.document.sources[0] if hit.document.sources else None
            src_url = src.source_url if src else "N/A"
            src_title = src.title if src else "N/A"
            print(f"         Source: {src_url}")
            print(f"         Title: {src_title}")
            print(f"         Snippet: {hit.document.text[:120].strip()}...")
    else:
        print("Status: FAILED (No hits)")

print("\n" + "=" * 70)
print("3. FULL PIPELINE END-TO-END RAG QUERIES")
print("=" * 70)

rag_pipeline_queries = [
    "What are the GIGW 3.0 accessibility guidelines for Indian government websites?",
    "How do I download my NTA entrance examination admit card from exams.nta.nic.in?",
    "How to create an APAAR ID for college students on apaar.education.gov.in?",
    "What is the fee and process for MEA consular attestation and apostille services?",
]

for q in rag_pipeline_queries:
    print(f"\n--- Pipeline Query: \"{q}\" ---")
    req = AskRequest(question=q)
    ans = run(req)
    print(f"Title: {ans.title}")
    print(f"Confidence: {ans.confidence}")
    print(f"Source URL: {ans.source_url}")
    print(f"Summary: {ans.summary[:150]}...")
    print(f"Citations ({len(ans.citations)}):")
    for c in ans.citations:
        print(f"  * {c.title} -> {c.url}")
    print(f"Steps count: {len(ans.steps)}")
    if ans.steps:
        print(f"  First step: {ans.steps[0].title} - {ans.steps[0].detail[:80]}...")

print("\n" + "=" * 70)
print("ALL RAG CHECKS COMPLETE")
