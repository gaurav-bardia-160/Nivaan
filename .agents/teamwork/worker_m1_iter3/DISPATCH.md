# Task Assignment: Milestone 1 Iteration 3 Remediation (Scraper Procedural Preservation)

## Role
Milestone 1 Implementation Worker (Iteration 3)

## Working Directory
`c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter3`

## Mandatory Files to Read First
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m1_iter2\handoff.md`
4. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m1_iter2\handoff.md`
5. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_m1_iter2\handoff.md`

## Problem & Defects to Remediate
In `backend/web_search/fetcher.py` in `is_navigation_or_boilerplate_text`:
1. `has_step_indicators` regex at line 206:
   `bool(re.search(r"\b(?:step\s*\d+|steps|[a-g][\.\)]|\d+[\.\)]\s+[A-Z])\b", lowered))`
   - Dead regex: `\d+[\.\)]\s+[A-Z]` is evaluated on `lowered` (lowercase text) and will NEVER match.
   - Punctuation boundary bug: `[a-g][\.\)]\b` fails when followed by whitespace because both `)`/. and space are non-word characters `\W`.
   Fix `has_step_indicators` so it reliably matches numbered steps (`1.`, `2)`, etc.) and lettered steps (`a)`, `b.`, etc.) on `lowered`:
   ```python
   has_step_indicators = bool(
       re.search(
           r"(?:\b(?:step\s*\d+|steps)\b|(?:\b\d+[\.\)]|\b[a-g][\.\)])(?:\s+|$))",
           lowered,
       )
   )
   ```
2. Document catalog detection at line 216:
   Currently:
   ```python
   if not has_step_indicators and re.search(
       r"\b(?:format\s*:\s*pdf|pdfsize|filesize|\d+(?:\.\d+)?\s*(?:kb|mb|gb)|size\s*:\s*\d+|download\s*\(|language\s*:\s*(?:english|hindi))\b",
       lowered,
   ):
       return True
   ```
   This has an over-generalization false positive: any legitimate procedural prose that specifies file upload size constraints (e.g., "Upload Aadhaar (scanned file size: 200 KB)") without explicit "step" tokens gets discarded because `\d+ KB` matches before `verb_count` is considered.
   Fix: Ensure catalog detection requires low action verb density (`verb_count <= 2`) or composite catalog metadata (e.g. format + size, or download + format) so legitimate civic procedures with upload sizes and procedural verbs (`verb_count >= 2` or `has_step_indicators`) are preserved (`is_navigation_or_boilerplate_text == False`). Note: Compute `verb_count` before or in conjunction with catalog indicators.

3. Testing & Verification:
   - Add unit tests in `tests/test_web_search.py` and `tests/test_adversarial_m1_harness.py` covering:
     * Numbered steps with file size e.g. `"1. Download Form 29 (PDF, 50 KB) from the portal.\n2. Fill out details.\n3. Submit to RTO."` -> `is_navigation_or_boilerplate_text == False`
     * Lettered steps with file size e.g. `"a) Download Form 29 (PDF, 50 KB)\nb) Fill out details"` -> `is_navigation_or_boilerplate_text == False`
     * Procedural prose with file size limits e.g. `"To apply for duplicate RC, visit Parivahan portal. Upload your Aadhaar card and police complaint (scanned file size: 200 KB). Submit the form and pay fee."` -> `is_navigation_or_boilerplate_text == False`
     * Pipeless document catalog directory listing e.g. from Tier 1 R5 (`test_tier1_r5_pdf_directory_catalog_rejection`) -> `is_navigation_or_boilerplate_text == True`
     * Markdown table directory listing (`|---|`) -> `is_navigation_or_boilerplate_text == True`
   - Run verification commands:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v`
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m1_harness.py tests/test_adversarial_m1_2_epfo_vector.py -v`

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Output
Write report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1_iter3\handoff.md`. Include test commands, logs, and layout verification.
