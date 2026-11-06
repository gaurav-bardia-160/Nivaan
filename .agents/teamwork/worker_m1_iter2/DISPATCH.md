# Task Assignment: Worker M1 Iteration 2 - Forensic Audit Remediation Implementation

## Mission
Implement the remediation for Milestone 1 (R5 pipeless catalog detection and step_verbs sanitization) to resolve the Forensic Audit Integrity Violation.

## Mandatory Inputs & Files to Read
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_iter2_explorer\handoff.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_m1\handoff.md`
4. Patch: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_iter2_explorer\fetcher.patch`

## Exclusive Write Ownership
You exclusively own and may modify:
- `backend/web_search/fetcher.py`
- `tests/test_web_search.py`

## Instructions
1. Apply the exact code changes specified in `m1_iter2_explorer/handoff.md §4.2`:
   - In `backend/web_search/fetcher.py`:
     * Decouple catalog regex matching from `pipe_count >= 2`:
       ```python
       # Document catalog indicators (Format: PDF, file sizes, download matrices without procedural steps)
       if not has_step_indicators and re.search(
           r"\b(?:format\s*:\s*pdf|pdfsize|filesize|\d+(?:\.\d+)?\s*(?:kb|mb|gb)|size\s*:\s*\d+|download\s*\(|language\s*:\s*(?:english|hindi))\b",
           lowered,
       ):
           return True
       ```
     * In `step_verbs`, change `"form"` to `"form "` so `"format"` in catalog headers does not match as an action verb.
   - In `tests/test_web_search.py`:
     * Add `test_identifies_pipeless_document_catalog_noise`.
2. Run full verification commands:
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
     (MUST PASS 10/10 with 0 failures!)
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v`
     (MUST PASS 39/39 with 0 failures!)
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m1_harness.py -v`
     (MUST PASS 12/12 with 0 failures!)
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db --check-only`
3. Document all command executions and raw outputs in your handoff report:
   `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter2\handoff.md`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## 2026-11-04T14:54:56Z
You are worker_m1_iter2, an implementation worker (teamwork_worker).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter2
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read:
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter2\DISPATCH.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_iter2_explorer\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_m1\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_iter2_explorer\fetcher.patch

Exclusive write ownership:
- backend/web_search/fetcher.py
- tests/test_web_search.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Apply the genuine fix to `backend/web_search/fetcher.py` and `tests/test_web_search.py`.
Run all required tests:
- `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
- `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v`
- `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m1_harness.py -v`
- `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db --check-only`

Document all passing command outputs in your handoff report:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter2\handoff.md
When done, notify me via send_message.

