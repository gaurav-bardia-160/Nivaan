# Dispatch for reviewer_cases_m1_1

## Task
You are `reviewer_cases_m1_1`, an independent review agent (`teamwork_reviewer`).
Working directory: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m1_1`
Original request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
Project roadmap: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
Worker handoff: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1\handoff.md`

## Mission & Objectives
Perform independent code review and verification of Milestone M1 (Corpus Ingestion & Retriever Coverage):
1. Inspect the code changes made by `worker_cases_m1` in:
   - `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`
   - `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`
   - `backend/data/rag_manifest.json`
   - `backend/modules/domain_router.py`
   - `backend/rag/retriever.py`
   - `backend/rag/runtime.py`
2. Verify statutory correctness:
   - Sections 147, 148, 148A, 149, 151: 7-30 day reply window under 148A(b); 3-year limitation expired 31 March 2022 for AY 2018-19; 10-year extended limitation requires escaped income >= ₹50 Lakhs; notice for ₹6.5L is time-barred; Section 151 sanction.
   - Rule 114AAA, CBDT Circular 03/2023, Section 234H: 30-day reactivation timeline upon Aadhaar intimation and ₹1,000 late fee payment.
   - Section 206AA: Employer statutory obligation to deduct 20% TDS and deposit; employer cannot refund deposited TDS via payroll; employee must claim credit/refund via ITR after PAN is operative.
3. Verify tests and run:
   - `py -m pytest tests/test_case1_case2_gating_regression.py -k "corpus_existence or domain_routing or dual_category or conflict_penalties" -v`
   - `py -m pytest tests/test_domain_router.py tests/test_rag_retriever.py -v`
4. Confirm Zero Predefined Responses compliance per `AGENTS.md` and `GEMINI.md`.
5. Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m1_1\handoff.md` with explicit verdict `APPROVE` or `REQUEST_CHANGES`.

## 2026-11-09T12:47:38Z
You are reviewer_cases_m1_1, an independent review agent (teamwork_reviewer).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m1_1
You MUST read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m1_1\DISPATCH.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1\handoff.md

Review Milestone M1 (Corpus Ingestion & Retriever Coverage):
1. Inspect code changes in troubleshooting_tax.jsonl, troubleshooting_pan.jsonl, rag_manifest.json, domain_router.py, retriever.py, and runtime.py.
2. Verify statutory accuracy (Sections 147-151, Rule 114AAA, Circular 03/2023, Section 234H, Section 206AA).
3. Run verification tests:
   py -m pytest tests/test_case1_case2_gating_regression.py -k "corpus_existence or domain_routing or dual_category or conflict_penalties" -v
   py -m pytest tests/test_domain_router.py tests/test_rag_retriever.py -v
4. Render verdict: APPROVE or REQUEST_CHANGES.
Write report to c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m1_1\handoff.md.
When complete, send a message to caller with verdict, summary, and report path.
