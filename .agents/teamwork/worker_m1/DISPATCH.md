# Task Assignment: Worker M1 - Corpus Integrity & Scraper Cleanup (R1 & R5)

## Mission
Implement the technical changes for Milestone 1 (R1 and R5) as specified by `m1_explorer_1`, `m1_explorer_2`, and `m1_spec_miner_3`.

## Exclusive Write Ownership
You exclusively own and may modify:
- `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl`
- `backend/web_search/fetcher.py`
- `backend/web_search/synthesizer.py`
- `backend/web_search/discriminator.py`
- `tests/test_web_search.py`
- `tests/test_rag_loader.py`
- `tests/test_build_vector_db.py`

## Instructions
1. Read the explorer reports:
   - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_1\handoff.md`
   - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_2\handoff.md`
   - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_spec_miner_3\handoff.md`
2. **R1 Implementation**:
   - In `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl` line 10 (`epfo_claim_passbook_cheque_standards_01`), replace the mismatched inspector manual URL with authentic circular URL:
     `"https://www.epfindia.gov.in/site_docs/PDFs/Circulars/Y2024-2025/WSU_IssueOfBKG_49885_16.pdf"`
     and refine tags: replace `"manual"` with `"sop"`, `"epf_claim_rejected"`, `"epf_bank_kyc"`.
   - Update `tests/test_rag_loader.py` lines 134 & 136 to reconcile with the 11 new official datasets (1415 records seen, 48 rejected records at 2026-10-30).
   - Rebuild the Qdrant vector database:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db`
     and verify with `--check-only` (must report `ready: true`, 1387 points).
3. **R5 Implementation**:
   - In `backend/web_search/fetcher.py`:
     * In `_extract_text()`: configure `trafilatura.extract(html, include_links=False, include_images=False, include_tables=False, favor_precision=True, include_comments=False)`.
     * Add `"table"` to `_NOISE_TAGS`.
     * In `is_navigation_or_boilerplate_text()`: add detection for Markdown table rows (`| ... |`), PDF catalogs, and download directories.
   - In `backend/web_search/synthesizer.py`:
     * Filter table rows (`line.count("|") < 2`) in extractive sentence scoring and prompt context.
   - In `backend/web_search/discriminator.py`:
     * Create module exporting `is_navigation_or_boilerplate_text` and `DISCRIMINATOR_FAILURE_PHRASE`.
   - In `tests/test_web_search.py`:
     * Add the 4 new unit test cases covering table noise detection and Trafilatura table omission.
4. **Verification**:
   - Run tests:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_web_search.py tests\test_rag_loader.py tests\test_build_vector_db.py -v`
   - Run regression test:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_scenes_1_to_3_regression.py -k "test_tier1_r1" -v`
   - Run the Scene 3 Turn 2 reproduction script from `m1_explorer_2/handoff.md §5.2`.
5. Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1\handoff.md`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.


## 2026-11-04T13:52:37Z
[Message] timestamp=2026-11-04T13:52:37Z sender=dbf15a36-ef58-4a18-a9f2-171e93acf6cc priority=MESSAGE_PRIORITY_HIGH
You are worker_m1, an implementation worker (teamwork_worker).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read:
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1\DISPATCH.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_1\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_2\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_spec_miner_3\handoff.md

Implement the changes for Milestone 1 (R1 and R5) according to DISPATCH.md.
Exclusive write ownership:
- backend/data/refined/troubleshooting/troubleshooting_civic.jsonl
- backend/web_search/fetcher.py
- backend/web_search/synthesizer.py
- backend/web_search/discriminator.py
- tests/test_web_search.py
- tests/test_rag_loader.py
- tests/test_build_vector_db.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Execute builds, rebuild the Qdrant vector database, run the unit and regression tests, and document all commands and passing outputs in your handoff report:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1\handoff.md
When done, notify me via send_message.
