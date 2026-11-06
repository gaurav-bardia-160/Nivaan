# Task Assignment: Milestone 2 Iteration 2 Review & Verification

## Role
Teamwork Reviewer (`teamwork_reviewer`)

## Working Directory
`c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2_iter2`

## Files to Inspect
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2\handoff.md` (previous review)
4. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2\handoff.md` (previous challenge)
5. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2_iter2\handoff.md`
6. Code diffs in `backend/modules/domain_router.py`, `backend/pipeline.py`, `backend/rag/retriever.py`, `tests/test_domain_router.py`, `tests/test_adversarial_m2_harness.py`.

## Review Mission
1. Verify that Hindi "din" queries (e.g. `"Passport banne me kitne din lagte hai?"`) are no longer intercepted by `mca_spice`.
2. Verify that `_build_uncovered_domain_refusal()` in `pipeline.py` correctly attributes domains without substring confusion on "process" or "pending".
3. Verify that spelling/spacing variations and caller-passed domain bypasses are resolved.
4. Run verification tests in Python 3.12:
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
5. Deliver verdict: **`APPROVE`** or **`REQUEST_CHANGES`**.
6. Write report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2_iter2\handoff.md` and notify parent via `send_message`.


## 2026-11-04T17:40:38Z
You are reviewer_m2_iter2.
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2_iter2

Read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2_iter2\DISPATCH.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2\handoff.md
5. c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2\handoff.md
6. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2_iter2\handoff.md

Conduct an independent review of Milestone 2 Iteration 2:
- Verify that Hindi "din" queries (e.g. "Passport banne me kitne din lagte hai?") route to covered domains and are not hijacked.
- Verify that _build_uncovered_domain_refusal() uses direct pattern matching and does not misattribute NSP/LPG queries to MCA.
- Verify that caller-passed domain argument bypass in retriever.py is blocked.
- Run test suites using Python 3.12:
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v
  & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.py" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
- Render verdict: APPROVE or REQUEST_CHANGES.
- Write handoff to c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2_iter2\handoff.md and notify parent via send_message.
