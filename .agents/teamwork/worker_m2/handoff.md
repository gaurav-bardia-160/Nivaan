# Milestone 2 Implementation Handoff Report: Hard Domain Routing & Retrieval Bleed Prevention (R2)

## 1. Observation
1. **Initial Baseline Failures**:
   - Running `pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v` initially produced 15 failures out of 15 selected tests:
     * `Domain` enum did not have `UNCOVERED`: `AssertionError: assert <Domain.UNKNOWN: 'unknown'> == 'uncovered'`.
     * Retriever executed lexical/vector search on uncovered queries instead of short-circuiting: `AssertionError: Expected uncovered_domain, got supported_lexical`.
     * Allowed categories returned `None` rather than `set()`: `AssertionError: assert None == set()`.
     * `run_pipeline` was not defined in `backend.pipeline`: `ImportError: cannot import name 'run_pipeline' from 'backend.pipeline'`.
2. **Corpus & Bleed Dynamics**:
   - Queries regarding MCA/SPICe+, Petroleum/LPG, and NSP scholarships were previously classified as `Domain.UNKNOWN`.
   - In `backend/rag/runtime.py:166-174`, queries containing words like "portal", "subsidy", "failed", or "scholarship" were coerced to `category = "civic"`.
   - Qdrant dense vector search in `backend/rag/retriever.py:103-119` returned nearest neighbors across unrelated civic documents (such as MSME Udyam, Ration card, EPFO passbook, or ITR-4), producing non-zero RRF scores and causing LLM synthesis hallucinations.
3. **Modified Files**:
   - `backend/modules/domain_router.py`:
     * Added `Domain.UNCOVERED = "uncovered"`.
     * Added `_UNCOVERED_DOMAIN_PATTERNS` dictionary covering `mca_spice`, `petroleum_lpg`, and `nsp_scholarships`.
     * Evaluated `_UNCOVERED_DOMAIN_PATTERNS` at the top of `classify_domain()` before all other domain checks.
     * Updated `get_allowed_rag_categories()` to return `set()` for `Domain.UNCOVERED`.
     * Updated `entry_matches_domain()` to return `False` for `Domain.UNCOVERED`.
   - `backend/rag/retriever.py`:
     * Added hard interception in `RagRetriever.search()`: if `resolved_domain == Domain.UNCOVERED`, immediately return `RetrievalResult(query=clean_query, hits=(), status="uncovered_domain", searched_documents=0)`.
     * Bypassed BM25 search, FastEmbed text embeddings, and Qdrant vector retrieval.
   - `backend/rag/runtime.py`:
     * Added checks in `supported_category()` and `retrieve_if_enabled()` returning `None` immediately if `domain in (Domain.UNCOVERED, "uncovered")` or `classify_domain(query) == Domain.UNCOVERED`.
   - `backend/pipeline.py`:
     * Added `_build_uncovered_domain_refusal()` creating a dynamic honest ungrounded refusal with `confidence="low"`, zero citations, and clear guidance without canned templates or mentions of "pre-verified guide".
     * Intercepted `query_domain == Domain.UNCOVERED` in both `run()` and `run_stream()`, logging to `backend/data/feedback/unresolved_queries.csv` with reason `"uncovered_domain"`.
     * Added and exported `run_pipeline(query: str | AskRequest | dict[str, Any]) -> Answer`.
   - `tests/test_domain_router.py`:
     * Implemented 35 unit tests covering enum definition, pattern classification, precedence over trouble words, allowed categories, retriever short-circuit, runtime isolation, and pipeline refusal.

## 2. Logic Chain
1. *Observation 1.2*: Uncovered domain queries (MCA, LPG, NSP) caused cosine bleed because dense embeddings and BM25 index searched the entire corpus and found nearest neighbors with score > 0.010.
2. *Observation 1.3*: By adding `_UNCOVERED_DOMAIN_PATTERNS` and evaluating them first in `classify_domain()`, any query matching MCA21/SPICe+/DIN/ROC, LPG/petroleum/MoPNG/PAHAL, or NSP/pre-matric/post-matric scholarships is deterministically identified as `Domain.UNCOVERED`.
3. *Observation 1.3*: In `RagRetriever.search()`, intercepting `resolved_domain == Domain.UNCOVERED` immediately returns an empty `RetrievalResult` with `status="uncovered_domain"` and `searched_documents=0`. This ensures 0 calls to Qdrant and 0 cosine computations, eliminating vector bleed at the root.
4. *Observation 1.3*: In `runtime.py`, ensuring `supported_category` and `retrieve_if_enabled` return `None` guarantees that trouble words ("failed", "stuck", "pending", "defect") never coerce an uncovered query to `category="civic"`.
5. *Observation 1.3*: In `pipeline.py`, intercepting `Domain.UNCOVERED` before web search or RAG allows the system to log the query to `unresolved_queries.csv` and return a genuine dynamic ungrounded refusal adhering to the `AGENTS.md` zero-predefined-response directive (without pre-canned templates or disclaimers referencing "pre-verified guides").
6. *Direct Conclusion*: Milestone 2 requirements (R2) are completely implemented and verified with zero vector bleed and zero regression.

## 3. Caveats
- Sub-procedure discrimination for Section 139(9) vs AIS feedback is part of Milestone 3 (R6), owned by `worker_m3`. The two tests testing AIS feedback discrimination (`test_tier2_ais_query_with_defect_keyword` and `test_tier2_139_query_with_ais_keyword`) are expectedly pending until Milestone 3 adds `itr_ais_feedback_manual_01`.
- General petroleum/LPG queries are uncovered, but specific PMUY Ujjwala 2.0 queries (if worded specifically as "PMUY" or "Ujjwala" without general cylinder/refill terms) remain classified under civic where official Ujjwala source chunks exist.

## 4. Conclusion
- All tasks for Milestone 2 (Hard Domain Routing & Retrieval Bleed Prevention - R2) have been genuinely implemented and tested.
- 100% of Tier 1 R2 tests (15/15) in `tests/test_scenes_1_to_3_regression.py` pass.
- 100% of newly added unit tests in `tests/test_domain_router.py` (35/35) pass.
- All baseline tests across R1, R5, web search, and RAG loader (52/52) continue to pass without regression.

## 5. Verification Method
Run the following commands using Python 3.12:

```powershell
# 1. Tier 1 R2 regression tests (15 tests, 100% pass)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v

# 2. Dedicated domain router and short-circuit unit tests (35 tests, 100% pass)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v

# 3. Related regression suites: R1, R5, web search, and rag loader (52 tests, 100% pass)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v
```

### Invalidation Conditions
- Any query containing MCA21/SPICe+, LPG/petroleum, or NSP keywords returning a status other than `"uncovered_domain"` or non-empty hits from `RagRetriever.search()`.
- Any uncovered domain query in `pipeline.py` triggering web search or returning a response mentioning "pre-verified guide" or hallucinated civic steps.
