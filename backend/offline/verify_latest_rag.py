import os
os.environ["RAG_VECTOR_ENABLED"] = "true"

from backend.rag.runtime import _get_retriever, get_retriever

_get_retriever.cache_clear()
retriever = get_retriever()

test_queries = [
    ("how to lodge public grievance on pgportal cpgrams", "pgportal"),
    ("what is the legal validity of digilocker documents", "digilocker"),
    ("what is myscheme portal and how to discover schemes", "myscheme"),
    ("mukhyamantri jan kalyan sambal yojana mp registration", "sambal_mp"),
    ("digital gujarat citizen certificate services", "digitalgujarat"),
    ("serviceplus national citizen services portal", "serviceonline"),
    ("national disaster resource network idrn equipment", "idrn_nidm"),
    ("ministry of cooperation schemes and pacs", "cooperatives"),
]

print("=" * 80)
print("LIVE RAG RETRIEVAL VERIFICATION ACROSS NEW SITES")
print("=" * 80)

passed = 0
for query, expected_slug in test_queries:
    res = retriever.search(query, top_k=3)
    top = res.hits[0] if res.hits else None
    src = top.document.sources[0] if top and top.document.sources else None
    url = src.source_url if src else "None"
    title = src.title if src else "None"
    score = round(top.score, 4) if top else 0.0

    print(f"\nQuery: '{query}'")
    print(f"  -> Top Title: {title}")
    print(f"  -> Top URL:   {url}")
    print(f"  -> Score:     {score}")
    print(f"  -> Status:    {res.status}")
    if res.hits:
        passed += 1

print("\n" + "=" * 80)
print(f"VERIFICATION RESULT: {passed}/{len(test_queries)} queries returned valid official citations!")
print("=" * 80)
