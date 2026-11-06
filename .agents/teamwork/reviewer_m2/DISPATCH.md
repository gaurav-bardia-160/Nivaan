# Task Assignment: Milestone 2 Review & Verification

## Role
Teamwork Reviewer (`teamwork_reviewer`)

## Working Directory
`c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2`

## Files to Inspect
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2\handoff.md`
4. Code changes in:
   - `backend/modules/domain_router.py`
   - `backend/rag/retriever.py`
   - `backend/rag/runtime.py`
   - `backend/pipeline.py`
   - `tests/test_domain_router.py`

## Review Mission
1. Verify that `Domain.UNCOVERED` correctly classifies MCA/SPICe+, petroleum/LPG, and NSP scholarship queries.
2. Verify that `RagRetriever.search()` short-circuits immediately without running BM25, FastEmbed, or Qdrant vector search.
3. Verify that `runtime.py` and `pipeline.py` properly isolate uncovered queries and return honest, dynamic ungrounded refusals.
4. Run verification tests in Python 3.12:
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
5. Deliver verdict: **`APPROVE`** or **`REQUEST_CHANGES`**.
6. Write report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2\handoff.md` and notify parent via `send_message`.

## 2026-11-04T17:06:18Z
You are reviewer_m2.
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2

Read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2\DISPATCH.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2\handoff.md

Conduct an independent review of Milestone 2:
- Inspect `backend/modules/domain_router.py`, `backend/rag/retriever.py`, `backend/rag/runtime.py`, and `backend/pipeline.py`.
- Verify that Domain.UNCOVERED correctly classifies uncovered domains and that RagRetriever.search() short-circuits without vector or lexical retrieval.
- Verify that pipeline.py returns honest dynamic ungrounded refusals and logs to unresolved_queries.csv.
- Run test suites using Python 3.12:
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
- Render verdict: APPROVE or REQUEST_CHANGES.
- Write handoff to c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2\handoff.md and notify parent via send_message.
