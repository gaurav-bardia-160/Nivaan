# Dispatch for survey_arch_gating_3

## Task
You are `survey_arch_gating_3`, a specification and architecture investigation agent (`teamwork_spec_miner`).
Working directory: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3`
Original request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`

## Mission & Objectives
Investigate the pipeline architecture for R1, R2, R3, and test suite specs:
1. **R1 Response Shape & Scaffolding**:
   - Trace in `backend/modules/explainer.py`, `backend/modules/llm.py`, `backend/web_search/synthesizer.py`, and prompts where the 3-step checklist ("Review [Doc 1], Review [Doc 2], Verify Official Portal") is enforced or templated.
   - Design how the system should classify/differentiate procedural/checklist queries from analytical, calculation, and legal-interpretation queries (e.g. limitation calculations, legal consequences, refund rules).
   - Formulate prompts/templates that provide direct analytical answers without artificial checklists.
2. **R2 Relevance and Confidence Gating**:
   - Trace `evaluate_relevance` and confidence calculation in `backend/modules/explainer.py` and `backend/web_search/confidence.py`.
   - Identify why unrelated documents (e.g., PAN FAQ or 119(2)(b) for reassessment queries) currently produce HIGH confidence badges.
   - Formulate semantic alignment / cross-attention / keyword & term overlap checks prior to synthesis, ensuring off-topic chunks cannot receive HIGH confidence and will trigger live CRAG or honest refusal.
3. **R3 Multi-part Query Decomposition**:
   - Analyze query processing in `backend/rag/retriever.py`, `backend/rag/runtime.py`, and `backend/modules/explainer.py`.
   - Design a clean query decomposition mechanism that breaks compound queries (like Case 1 and Case 2) into sub-questions, retrieves/evaluates support for each, and synthesizes answers covering every sub-question.
4. **Automated Test Specifications**:
   - Inspect existing tests in `tests/` (`test_pipeline.py`, `test_retriever.py`, `test_explainer.py`, etc.).
   - Define exact test requirements and assertions for Case 1, Case 2, confidence gating, and query decomposition.

## Boundaries
- Read-only: DO NOT modify any source code or run build/test commands.
- Write your findings to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\handoff.md`.


## 2026-11-09T11:57:51Z
You are survey_arch_gating_3, a specification and architecture investigation agent (teamwork_spec_miner).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3
You MUST read c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md and c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\DISPATCH.md before starting.

Investigate the pipeline architecture for R1, R2, R3, and test suite specs:
1. R1 Response Shape & Scaffolding:
   - Trace in `backend/modules/explainer.py`, `backend/modules/llm.py`, `backend/web_search/synthesizer.py`, and prompts where the 3-step checklist ("Review [Doc 1], Review [Doc 2], Verify Official Portal") is enforced or templated.
   - Design how the system should classify/differentiate procedural/checklist queries from analytical, calculation, and legal-interpretation queries (e.g. limitation calculations, legal consequences, refund rules).
   - Formulate prompts/templates that provide direct analytical answers without artificial checklists.
2. R2 Relevance and Confidence Gating:
   - Trace `evaluate_relevance` and confidence calculation in `backend/modules/explainer.py` and `backend/web_search/confidence.py`.
   - Identify why unrelated documents (e.g., PAN FAQ or 119(2)(b) for reassessment queries) currently produce HIGH confidence badges.
   - Formulate semantic alignment / cross-attention / keyword & term overlap checks prior to synthesis, ensuring off-topic chunks cannot receive HIGH confidence and will trigger live CRAG or honest refusal.
3. R3 Multi-part Query Decomposition:
   - Analyze query processing in `backend/rag/retriever.py`, `backend/rag/runtime.py`, and `backend/modules/explainer.py`.
   - Design a clean query decomposition mechanism that breaks compound queries (like Case 1 and Case 2) into sub-questions, retrieves/evaluates support for each, and synthesizes answers covering every sub-question.
4. Automated Test Specifications:
   - Inspect existing tests in `tests/` (`test_pipeline.py`, `test_retriever.py`, `test_explainer.py`, etc.).
   - Define exact test requirements and assertions for Case 1, Case 2, confidence gating, and query decomposition.

Do not write or modify any source code or execute tests.
Write your complete structured report to c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\handoff.md.
When done, send a message to your caller with your handoff path and summary.
