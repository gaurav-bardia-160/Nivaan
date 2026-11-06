# Exploration Task: Milestone 3 Iteration 3 Root Cause & Fix Strategy (R6 Sub-Procedure Granularity)

## Objective
Analyze the root causes of the Forensic Audit failure (INTEGRITY VIOLATION) and Challenger changes request in Milestone 3 Iteration 2, and formulate a comprehensive, robust fix strategy for the Worker in Iteration 3.

## Authoritative Reference Paths
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\GATE_STATUS.md`
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_m3_iter2\handoff.md` (FULL AUDIT EVIDENCE)
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m3_iter2_2\handoff.md` (WORD BOUNDARY & COMPARISON QUERY EVIDENCE)
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m3_iter2\handoff.md`

## Full Forensic Audit Evidence (DO NOT CIRCUMVENT)
The auditor identified the following failure in `tests/test_adversarial_m3_1_harness.py::TestAdversarialStressScenarios::test_pipeline_citation_isolation`:
1. Query: `"Received Section 139(9) defective return notice because AIS income differed from ITR"`
2. Downstream `run_pipeline()` leaked `Income Tax Department User Guide on Submitting Feedback on Annual Information Statement (AIS)` as Citation #2.
3. Root Cause: `itr_ais_feedback_manual_01` contains the text *"AIS feedback is NOT a Section 139(9) defective return proceeding..."*.
   - Because the query contains `"139(9)"` and the document contains `"139(9)"`, `retriever.py` awards it `exact_statutory_boost (+0.12)`.
   - In `_SYMPTOM_CLUSTERS`, `defective_return` boost terms contain `"139(9)"`, awarding `symptom_boost (+0.08)`.
   - Along with `troubleshooting_boost (+0.05)`, it receives +0.25 in boosts.
   - The sub-procedure penalty is -0.40, but +0.25 offsets it to net -0.15 (score -0.1330).
   - Because other candidate documents have lower scores, `itr_ais_feedback_manual_01` surfaces at rank 2 and leaks into pipeline citations!

## Full Challenger Evidence (Word Boundary Defect)
In `challenger_m3_iter2_2/handoff.md`:
In `backend/rag/retriever.py:307`:
`is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))`
The trailing `\b` asserts a word boundary after `)`, which is a non-word character (`\W`). When followed by whitespace, punctuation (e.g. `"139(9) vs AIS"`), or end-of-string, `\b` evaluates to `False`. Thus `139(9)` fails to match, leaving `is_139_query = False` while `is_ais_query = True`, applying false -0.40 penalty on 139(9).

## Your Tasks
1. Investigate `backend/rag/retriever.py` and `tests/test_adversarial_m3_1_harness.py`.
2. Formulate a complete fix strategy that:
   - Fixes the `\b` word boundary regex for `139(9)` (e.g. `(?!\w)` instead of `\b` after `\)`).
   - Prevents `exact_statutory_boost` and symptom boosts from applying to conflicting sub-procedure documents that only mention the statutory code in negative/disclaimer clauses.
   - Ensures that single-intent queries for 139(9) completely suppress AIS feedback (ensuring it never leaks into top 3 citations in `run_pipeline()`), and vice versa for AIS queries.
   - Keeps comparison queries working cleanly without mismatch penalties.
   - Maintains genuine Zero Predefined Responses compliance.
3. Write your findings and recommendations to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m3_iter3_explorer_2\handoff.md` and message back when complete.


## 2026-11-04T20:33:37Z
Sender: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
Message:
Investigate the root causes of the citation leakage in test_adversarial_m3_1_harness.py and the word boundary regex bug in retriever.py. Formulate a complete fix strategy for Worker Iteration 3. Write your report to c:\Users\gaura\Documents\nivaan\.agents\teamwork\m3_iter3_explorer_2\handoff.md and message back.
