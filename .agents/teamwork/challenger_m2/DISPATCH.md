# Task Assignment: Milestone 2 Adversarial Verification & Stress Test

## Role
Empirical Challenger (`teamwork_challenger`)

## Working Directory
`c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2`

## Files to Inspect
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2\handoff.md`
4. Code in `backend/modules/domain_router.py`, `backend/rag/retriever.py`, `backend/rag/runtime.py`, `backend/pipeline.py`.

## Challenge Mission
1. Empirically verify that uncovered domains are intercepted:
   - Formulate adversarial queries attempting to bypass domain classification using spelling variations, mixed tokens (e.g., combining MCA with civic words like "apply", "subsidy", "portal", "registration", "delay").
   - Confirm that `RagRetriever.search()` NEVER fetches nearest-neighbor civic chunks (e.g. Udyam MSME, Ration card, EPFO) for any uncovered query.
   - Verify that `pipeline.py` does not perform web search or hallucinate civic procedures.
2. Verify boundary cases:
   - Covered civic queries mentioning words like "company", "director", "scholarship", or "cylinder" where valid (e.g. PMUY Ujjwala 2.0).
3. Run verification test suites in Python 3.12:
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
4. Deliver verdict: **`APPROVE`** or **`REQUEST_CHANGES`**.
5. Write report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2\handoff.md` and notify parent via `send_message`.


## 2026-11-04T17:06:30Z
You are challenger_m2.
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2

Read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2\DISPATCH.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2\handoff.md

Conduct empirical challenge and stress-testing of Milestone 2:
- Empirically test adversarial attack queries attempting to bypass domain classification using spelling variations, mixed tokens, or trouble words combined with MCA, LPG, or NSP.
- Verify that `RagRetriever.search()` NEVER fetches nearest-neighbor civic chunks (e.g. Udyam MSME, Ration card, EPFO) for any uncovered query.
- Test boundary cases (such as PMUY Ujjwala 2.0 vs general LPG).
- Run test suites using Python 3.12:
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
- Render verdict: APPROVE or REQUEST_CHANGES.
- Write handoff to c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2\handoff.md and notify parent via send_message.
