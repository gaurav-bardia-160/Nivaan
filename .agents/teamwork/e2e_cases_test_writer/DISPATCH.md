# Dispatch for e2e_cases_test_writer

## Task
You are `e2e_cases_test_writer`, a specialist test writer agent (`teamwork_test_writer`).
Working directory: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_cases_test_writer`
Original request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
Project roadmap: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`

## Mission & Objectives
Design and write a comprehensive, requirement-driven automated test suite for Case 1, Case 2, Relevance/Confidence Gating, and Multi-Part Query Decomposition:
1. Target Test File: `tests/test_case1_case2_gating_regression.py`
2. Structure the test suite following the 4-tier methodology:
   - **Tier 1 (Feature Coverage)**:
     - Case 1 query returns direct analytical answer (no 3-step checklist, limitation under Section 149, 7-30 days reply window under 148A(b)).
     - Case 2 query returns direct analytical answer (no 3-step checklist, ~30 days reactivation timeline under Rule 114AAA/Circular 03/2023, Section 206AA employer cannot refund deposited TDS / claim via ITR).
     - Relevance and confidence gating: off-topic chunks (e.g. 119(2)(b), PAN FAQ) do not produce HIGH confidence badges for 148A queries, confidence < 0.35.
     - Multi-part query decomposition decomposes Case 1 and Case 2 into distinct sub-questions.
     - Corpus existence and verification for Sections 147-151 and 206AA/114AAA/Circular 03/2023.
   - **Tier 2 (Boundary & Corner Cases)**:
     - Edge cases: ₹50 Lakhs boundary under Section 149 (e.g. ₹49.9L vs ₹50L), 3-year date boundary (31 March 2022 vs 1 April 2022), minimum 7-day reply window boundary, offline pytest execution without live LLM.
   - **Tier 3 (Cross-Feature Combinations)**:
     - Query decomposition + confidence gating.
     - Analytical shape + multi-part synthesis.
     - Dual-category retrieval (`tax` + `pan`) for PAN-TDS inquiries.
   - **Tier 4 (Real-World Application Scenarios)**:
     - Exact verbatim Case 1 user query.
     - Exact verbatim Case 2 user query.
3. Baseline Execution:
   - Run `py -m pytest tests/test_case1_case2_gating_regression.py -v` to record initial failure state.
4. Coordination Signal:
   - When tests are written, update or create `c:\Users\gaura\Documents\nivaan\TEST_READY.md` documenting test runner command, tier breakdown, and initial baseline pass/fail results.
5. Report:
   - Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_cases_test_writer\handoff.md`.

## Boundaries
- Write tests ONLY in `tests/test_case1_case2_gating_regression.py`.
- Do NOT modify any implementation source code in `backend/`.
- Verify your test file syntax and execute the baseline test command.


## 2026-11-09T12:13:02Z
Sender: 39a4200a-88ea-4d70-9ed4-ca0bc59538f8
Content: You are e2e_cases_test_writer, a specialist test writer agent (teamwork_test_writer).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_cases_test_writer
You MUST read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_cases_test_writer\DISPATCH.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\handoff.md (specifically Section 6: Automated Test Specifications with exact code and assertions!)
5. c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_reassess_1\handoff.md
6. c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_inop_pan_2\handoff.md

Your mission:
Write the comprehensive 4-tier automated test suite in `tests/test_case1_case2_gating_regression.py` covering:
- Tier 1: Feature Coverage (Case 1 148A analytical shape, Case 2 inoperative PAN TDS decomposition, relevance/confidence gating on off-topic chunks, query decomposition, corpus existence).
- Tier 2: Boundary & Corner Cases (₹50 Lakhs limit boundary, 3-year date boundary, 7-day minimum reply window, offline pytest execution).
- Tier 3: Cross-Feature Combinations (decomposition + gating, analytical shape + multi-part synthesis, dual category tax+pan).
- Tier 4: Real-World Scenarios (exact Case 1 and Case 2 user queries).

Run the tests to document the initial baseline failure state.
Publish `TEST_READY.md` at project root `c:\Users\gaura\Documents\nivaan\TEST_READY.md`.
Write your handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_cases_test_writer\handoff.md`.
When complete, send a message to your caller with summary and handoff path.
