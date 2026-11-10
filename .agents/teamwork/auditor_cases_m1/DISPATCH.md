# Dispatch for auditor_cases_m1

## Task
You are `auditor_cases_m1`, a forensic integrity auditor (`teamwork_auditor`).
Working directory: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_cases_m1`
Original request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
Project roadmap: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
Worker handoff: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1\handoff.md`

## Mission & Objectives
Perform strict forensic audit on Milestone M1:
1. Inspect git diff and changes made by `worker_cases_m1`:
   - `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`
   - `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`
   - `backend/data/rag_manifest.json`
   - `backend/modules/domain_router.py`
   - `backend/rag/retriever.py`
   - `backend/rag/runtime.py`
2. Check for Integrity Violations:
   - Check if any test strings or query-specific answers were hardcoded in source code.
   - Check if any dummy or facade logic was introduced to bypass genuine search or routing.
   - Check if any test files were modified or tampered with by the worker.
   - Verify strict compliance with the Zero Predefined Responses directive in `AGENTS.md` and `GEMINI.md`.
3. Render your forensic verdict:
   - Must be explicitly `CLEAN` or `INTEGRITY VIOLATION`.
   - Provide supporting forensic evidence.
4. Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_cases_m1\handoff.md`.

## 2026-11-09T12:48:14Z
You are auditor_cases_m1, a forensic integrity auditor (teamwork_auditor).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_cases_m1
You MUST read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_cases_m1\DISPATCH.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m1\handoff.md

Perform forensic integrity audit on Milestone M1:
1. Inspect git diff and changes made by worker_cases_m1 in troubleshooting_tax.jsonl, troubleshooting_pan.jsonl, rag_manifest.json, domain_router.py, retriever.py, and runtime.py.
2. Verify zero hardcoded test outputs or dummy facades.
3. Verify zero modifications to test files.
4. Verify strict compliance with the Zero Predefined Responses directive in AGENTS.md and GEMINI.md.
5. Render binary verdict: CLEAN or INTEGRITY VIOLATION.
Write report to c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_cases_m1\handoff.md.
When complete, send a message to caller with verdict, evidence, and report path.
