# Dispatch for worker_cases_m1

## Task
You are `worker_cases_m1`, an implementation worker agent (`teamwork_worker`).
Working directory: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1`
Original request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
Project roadmap: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`

## Mandatory Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Rule: Zero Predefined Responses
NEVER use or re-introduce predefined, hardcoded, or pre-canned responses. All answers must be dynamically generated from RAG retrieval, live search, and dynamic local LLM synthesis.

## Scope & File Ownership
You exclusively own and may edit ONLY the following files:
- `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`
- `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`
- `backend/data/rag_manifest.json`
- `backend/modules/domain_router.py`
- `backend/rag/retriever.py`
- `backend/rag/runtime.py`

You MUST NOT edit `backend/modules/explainer.py`, `backend/modules/llm.py`, `backend/web_search/confidence.py`, `backend/web_search/synthesizer.py`, or test files.

## Detailed Implementation Directives
Refer to the exact findings, JSON schemas, and code recommendations in:
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_reassess_1\handoff.md` (Sections 3 & 4)
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_inop_pan_2\handoff.md` (Section 5)

1. **Corpus Ingestion (R4)**:
   - Add canonical statutory records for Reassessment (Sections 147, 148, 148A, 149, 151) to `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`:
     - Must detail: Section 148A(b) show-cause procedure and statutory reply window (minimum 7 days up to 30 days, or as extended); Section 149 limitation (3-year normal limitation from end of relevant AY, 10-year extended limitation only if escaped income in form of asset/expenditure/entry is >= ₹50 Lakhs; for AY 2018-19 ended 31 March 2019, 3-year period expired 31 March 2022; notice for ₹6.5 Lakhs is time-barred); Section 151 sanction authority.
   - Add canonical statutory record for Inoperative PAN & TDS (Rule 114AAA, Circular 03/2023, Section 234H) to `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`:
     - Must detail: Reactivation timeline of within 30 days from date of Aadhaar linking request after payment of ₹1,000 late fee under Section 234H.
   - Add canonical statutory record for Section 206AA TDS Deduction & ITR Refund Procedure to `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`:
     - Must detail: Employer's statutory duty to deduct 20% TDS under Section 206AA and remit to Govt; employer CANNOT refund or adjust deposited tax via payroll; taxpayer must claim credit/refund by filing an Income Tax Return (ITR) for the relevant Assessment Year after PAN is operative.
   - Update `backend/data/rag_manifest.json` with the updated chunk counts / sha256 as appropriate.

2. **Domain Routing & Category Resolution**:
   - In `backend/modules/domain_router.py`:
     - Expand `_DOMAIN_PATTERNS[Domain.TAXATION]` to recognize `147`, `148`, `148a`, `149`, `151`, `206aa`, `234h`, `reassessment`, `escaped income`, `time-barred`, `limitation period`, `inoperative pan`.
     - In `get_allowed_rag_categories`: Allow dual-category access `{"tax", "pan", "civic"}` for `Domain.TAXATION` or `Domain.IDENTITY` when query involves PAN-Aadhaar linking and TDS/tax consequences.
   - In `backend/rag/runtime.py`:
     - Expand `_CATEGORY_TERMS["tax"]` to include `"148"`, `"148a"`, `"147"`, `"149"`, `"151"`, `"reassessment"`, `"escaped income"`, `"206aa"`, `"234h"`.

3. **Retriever Clusters & Conflict Discrimination**:
   - In `backend/rag/retriever.py`:
     - Add exact codes: `"148a(b)"`, `"148a"`, `"148"`, `"149"`, `"147"`, `"151"`, `"206aa"`, `"114aaa"`, `"234h"`.
     - Add `tax_reassessment` symptom cluster:
       - Match terms: `"148a"`, `"148"`, `"reassessment"`, `"149"`, `"escaped income"`, `"time-barred"`, `"unexplained share"`, `"3-year vs 10-year"`.
       - Boost terms: `"section 148a"`, `"section 149"`, `"reassessment"`, `"escaped income"`, `"limitation"`.
       - Conflicts: `"139(9)"`, `"defective return"`, `"119(2)(b)"`, `"condonation"`, `"bank validation"`.
     - Add `inoperative_pan_tds` symptom cluster:
       - Match terms: `"inoperative"`, `"206aa"`, `"234h"`, `"114aaa"`, `"circular 03/2023"`, `"flat 20%"`, `"excess 20% tds"`.
       - Boost terms: `"circular 03/2023"`, `"rule 114aaa"`, `"section 206aa"`, `"section 234h"`, `"reactivation"`, `"30 days"`, `"refund via itr"`.
       - Conflicts: `"protean"`, `"tin-nsdl"`, `"paperless"`, `"challan mismatch"`, `"physical documentation"`.

4. **Verification**:
   - Run existing unit tests via `py -m pytest tests/test_retriever.py tests/test_domain_router.py tests/test_rag_pipeline.py -v`.
   - Ensure all existing tests pass and no regressions are introduced.
   - Document verification commands and output in `handoff.md`.



## 2026-11-09T12:13:33Z
You are worker_cases_m1, an implementation worker agent (teamwork_worker).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1
You MUST read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1\DISPATCH.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_reassess_1\handoff.md
5. c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_inop_pan_2\handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Rule: Zero Predefined Responses: NEVER use or re-introduce predefined, hardcoded, or pre-canned responses.

File ownership:
- backend/data/refined/troubleshooting/troubleshooting_tax.jsonl
- backend/data/refined/troubleshooting/troubleshooting_pan.jsonl
- backend/data/rag_manifest.json
- backend/modules/domain_router.py
- backend/rag/retriever.py
- backend/rag/runtime.py
Do not edit any other backend files or test files.

Implement Milestone M1 (Corpus Ingestion & Retriever Coverage):
1. Ingest official statutory records for Income Tax Reassessment (147, 148, 148A, 149, 151) into troubleshooting_tax.jsonl.
2. Ingest official statutory records for Inoperative PAN (Rule 114AAA, Circular 03/2023, Section 234H) into troubleshooting_pan.jsonl.
3. Ingest official statutory records for Section 206AA Higher TDS & ITR Refund Procedure into troubleshooting_tax.jsonl.
4. Update domain_router.py with statutory patterns and cross-category retrieval allowance.
5. Update retriever.py with exact codes, symptom clusters, and conflict penalties.
6. Update runtime.py category terms.
7. Run tests to verify build & syntax: py -m pytest tests/test_retriever.py tests/test_domain_router.py -v.
8. Write your complete handoff report to c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1\handoff.md.
When complete, send a message to your caller with your handoff path and summary.
