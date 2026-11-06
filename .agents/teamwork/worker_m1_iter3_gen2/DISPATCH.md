## 2026-11-04T15:28:43Z
You are worker_m1_iter3_gen2.
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter3_gen2

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

First, read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter3_gen2\DISPATCH.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m1_iter2\handoff.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m1_iter2\handoff.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_m1_iter2\handoff.md

Tasks:
1. In `backend/web_search/fetcher.py`:
   - Fix `has_step_indicators` at line 206:
     ```python
     has_step_indicators = bool(
         re.search(
             r"(?:\b(?:step\s*\d+|steps)\b|(?:\b\d+[\.\)]|\b[a-g][\.\)])(?:\s+|$))",
             lowered,
         )
     )
     ```
   - In document catalog indicators at line 216:
     Ensure action verb density (`verb_count <= 2`) is checked so that legitimate procedural prose that mentions file upload size constraints (e.g. "Upload Aadhaar (scanned file size: 200 KB)") with verb_count >= 2 is preserved (`is_navigation_or_boilerplate_text == False`). Pipeless document catalog directory listings (with low action verbs verb_count <= 2) must continue to return `True`.
2. Augment tests in `tests/test_adversarial_m1_harness.py` and `tests/test_web_search.py`:
   - Verify numbered steps with file size e.g. `"1. Download Form 29 (PDF, 50 KB) from the portal.\n2. Fill out details.\n3. Submit to RTO."` -> `is_navigation_or_boilerplate_text == False`
   - Verify lettered steps with file size e.g. `"a) Download Form 29 (PDF, 50 KB)\nb) Fill out details"` -> `is_navigation_or_boilerplate_text == False`
   - Verify procedural prose with file size limits e.g. `"To apply for duplicate RC, visit Parivahan portal. Upload your Aadhaar card and police complaint (scanned file size: 200 KB). Submit the form and pay fee."` -> `is_navigation_or_boilerplate_text == False`
   - Verify pipeless document catalog directory listing from Tier 1 R5 (`test_tier1_r5_pdf_directory_catalog_rejection`) -> `is_navigation_or_boilerplate_text == True`
3. Run all test suites using Python 3.12:
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m1_harness.py tests/test_adversarial_m1_2_epfo_vector.py -v
4. Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter3_gen2\handoff.md` and notify the parent orchestrator via send_message.
