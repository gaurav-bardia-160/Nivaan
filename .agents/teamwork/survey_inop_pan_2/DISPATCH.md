# Dispatch for survey_inop_pan_2

## Task
You are `survey_inop_pan_2`, a read-only exploration agent (`teamwork_explorer`).
Working directory: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_inop_pan_2`
Original request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`

## Mission & Objectives
Investigate the codebase for Case 2: Inoperative PAN / 20% TDS Refund under R1, R3, R4:
1. Examine `backend/data/rag_manifest.json` and corpus files for PAN & TDS provisions: Section 206AA, Rule 114AAA, CBDT Circular 03/2023, Section 234H. Verify what documents currently exist and what are missing.
2. Investigate how queries like:
   "My salary credit in August came with a flat 20% TDS deduction because my PAN became 'Inoperative' for missing the Aadhaar linking deadline. I just paid the ₹1,000 late fee under Section 234H on the portal. How long before my PAN becomes active, and how do I get my company to refund the excess 20% TDS?"
   are retrieved, routed, and answered.
3. Analyze why multi-part queries fail in the current pipeline:
   - Sub-question 1: How long before PAN becomes active? (CBDT Circular 03/2023 / Rule 114AAA: within 30 days from date of linking request after fee payment).
   - Sub-question 2: How to get the company to refund the excess 20% TDS? (Employer deducted 20% under Section 206AA and deposited with Govt; employer cannot adjust/refund via subsequent payroll once deposited; employee must file an Income Tax Return (ITR) after PAN becomes operative to claim credit/refund).
4. Identify how the current synthesis scaffolding forces responses into generic 3-step procedural checklists ("Review [Doc 1], Review [Doc 2], Verify Official Portal") and why it fails to answer both analytical sub-questions directly.
5. Recommend the exact corpus texts, manifest updates, and query decomposition changes required.

## Boundaries
- Read-only: DO NOT modify any source code or run build/test commands.
- Write your findings to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_inop_pan_2\handoff.md`.
