# Task Assignment: Milestone 2 Iteration 2 Adversarial Challenge & Stress Test

## Role
Empirical Challenger (`teamwork_challenger`)

## Working Directory
`c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2_iter2`

## Files to Inspect
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2\handoff.md` (previous challenge findings)
4. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2_iter2\handoff.md`
5. Implementation in `backend/modules/domain_router.py`, `backend/pipeline.py`, `backend/rag/retriever.py`.

## Challenge Mission
1. Empirically verify that all 10 attack bypass queries from `challenger_m2/handoff.md` are now intercepted:
   - `"pre matric scholarship"`
   - `"post matric scholarship"`
   - `"merit cum means scholarship"`
   - `"bharatgas online booking"`
   - `"hpgas booking"`
   - `"how to incorporate a new company"`
   - `"one person company registration"`
   - `"company registration online"`
   - `"cylinder delivery delay"`
   - `"cooking gas connection application"`
2. Verify that caller-passed domain argument bypass in `retriever.search(query, domain=Domain.GENERAL_CIVIC)` is completely blocked for uncovered queries.
3. Verify that Indic/Hinglish processing day queries ("kitne din") are not intercepted.
4. Run verification tests in Python 3.12:
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
5. Deliver verdict: **`APPROVE`** or **`REQUEST_CHANGES`**.
6. Write report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2_iter2\handoff.md` and notify parent via `send_message`.


## 2026-11-04T17:40:45Z
[Message from parent dbf15a36-ef58-4a18-a9f2-171e93acf6cc]
Conduct empirical challenge and stress-testing of Milestone 2 Iteration 2:
- Empirically verify that all 10 attack bypass queries from challenger_m2/handoff.md are now intercepted.
- Verify caller-passed domain argument bypass is blocked.
- Verify that Hindi "kitne din" queries are not intercepted as uncovered.
- Run test suites using Python 3.12:
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
- Render verdict: APPROVE or REQUEST_CHANGES.
- Write handoff to c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2_iter2\handoff.md and notify parent via send_message.
