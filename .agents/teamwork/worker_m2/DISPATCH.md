# Task Assignment: Milestone 2 — Hard Domain Routing & Retrieval Bleed Prevention (R2)

## Role
Milestone 2 Implementation Worker (`teamwork_worker`)

## Working Directory
`c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2`

## Mandatory Files to Read First
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1\handoff.md` (Section 4.1 contains exact regexes and architecture)
4. Existing implementations:
   - `backend/modules/domain_router.py`
   - `backend/rag/retriever.py`
   - `backend/rag/runtime.py`
   - `backend/pipeline.py`
   - `tests/test_scenes_1_to_3_regression.py` (specifically Tier 1 R2 tests: `test_tier1_r2_mca_spice_short_circuit_no_rag_bleed`, `test_tier1_r2_petroleum_lpg_short_circuit`, `test_tier1_r2_nsp_scholarships_short_circuit`, `test_tier1_r2_uncovered_domain_zero_predefined_response`)

## Write Ownership
`worker_m2` exclusively owns:
- `backend/modules/domain_router.py`
- `backend/rag/retriever.py` (search method domain check and short-circuit)
- `backend/rag/runtime.py`
- `backend/pipeline.py` (uncovered domain handling)
- `tests/test_domain_router.py` (or new test file for unit tests)

## Detailed Requirements
1. `backend/modules/domain_router.py`:
   - Add `Domain.UNCOVERED = "uncovered"` to `Domain(str, Enum)`.
   - Add `_UNCOVERED_DOMAIN_PATTERNS` regex dictionary for:
     * `mca_spice`: `re.compile(r"\b(?:mca|mca21|spice\+?|spice\s+plus|roc|registrar\s+of\s+companies|director\s+identification\s+number|\bdin\b|\bcin\b|corporate\s+affairs|incorporat(?:e|ion)\s+(?:of\s+)?company|private\s+limited\s+company|inc-?29|inc-?32|dir-?3|mgt-?7)\b", re.IGNORECASE)`
     * `petroleum_lpg`: `re.compile(r"\b(?:lpg|liquefied\s+petroleum|gas\s+cylinder|cylinder\s+booking|commercial\s+cylinder|domestic\s+cylinder|indane|bharat\s+gas|hp\s+gas|omc|refill\s+booking|subsidized\s+cylinder|pahal\b|dbtl)\b", re.IGNORECASE)`
     * `nsp_scholarships`: `re.compile(r"\b(?:nsp|national\s+scholarship\s+portal|pre-?matric\s+scholarship|post-?matric\s+scholarship|merit-?cum-?means|scholarship\s+disbursement|scholarship\s+scheme|scholarships\.gov\.in)\b", re.IGNORECASE)`
   - In `classify_domain(query: str) -> Domain`: evaluate `_UNCOVERED_DOMAIN_PATTERNS` before civic/fallback checks. If matched, return `Domain.UNCOVERED`.
   - In `get_allowed_rag_categories`: if `domain == Domain.UNCOVERED`, return `set()` (empty set).

2. `backend/rag/retriever.py`:
   - In `RagRetriever.search(query, category=None, domain=None, top_k=None)`:
     Before running BM25, vector search, or computing embeddings, check:
     ```python
     if resolved_domain == Domain.UNCOVERED:
         return RetrievalResult(
             query=clean_query,
             hits=(),
             status="uncovered_domain",
             searched_documents=0,
         )
     ```
     Ensure zero nearest-neighbor vectors are fetched from Qdrant, preventing cosine bleed into unrelated civic topics (e.g., Udyam, Ration card, EPFO).

3. `backend/rag/runtime.py` and `backend/pipeline.py`:
   - In `runtime.py`: ensure queries matching uncovered domains do NOT coerce to `category="civic"`.
   - In `pipeline.py`: when `query_domain == Domain.UNCOVERED`:
     * Log to `unresolved_queries.csv` with reason `"uncovered_domain"`.
     * Bypass web search / CRAG fallback (do not scrape random web pages for unsupported portals).
     * Return an honest ungrounded refusal explaining that the requested service (MCA/SPICe+, petroleum/LPG, or NSP scholarships) is currently not covered in the verified civic knowledge base, strictly adhering to `AGENTS.md` Zero Predefined Responses.

4. Test Verification:
   - Run using Python 3.12:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_retriever.py -v` (if applicable)
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v`

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Output
Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2\handoff.md` and notify the orchestrator via `send_message`.

## 2026-11-04T16:48:41Z
Received dispatch message:
You are worker_m2.
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2
Tasks:
1. Implement Domain.UNCOVERED in `backend/modules/domain_router.py`
2. Implement hard short-circuit in `backend/rag/retriever.py`
3. Update `backend/rag/runtime.py` and `backend/pipeline.py`
4. Run all tests with Python 3.12
5. Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2\handoff.md` and notify orchestrator.
