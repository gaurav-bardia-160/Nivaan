# Dispatch: m3_explorer_1

## Mission
Investigate codebase and design the technical strategy for Milestone M3: Response Shape & Multi-Part Query Decomposition (Requirements R1 and R3, Features 7 and 8).

## Inputs & Scope
- Original Request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md` (MUST read first)
- Project Scope: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
- Test Suite: `c:\Users\gaura\Documents\nivaan\tests\test_case1_case2_gating_regression.py`
- Code Files to Investigate:
  - `backend/modules/explainer.py` (lines 330-365 where `steps` are constructed, e.g. "Review [Doc]", "Verify Official Portal")
  - `backend/modules/llm.py` (lines 750-850 where prompt directives and steps enhancement are handled)
  - `backend/rag/retriever.py` (or `backend/rag/decomposition.py` / `backend/modules/query_decomposer.py` for query decomposition)
  - `backend/pipeline.py` (where retrieval and synthesis coordinate multi-part queries and pass modality)
  - `backend/web_search/synthesizer.py` (lines 380-410 where checklist/steps might be added)

## Exploration Objectives
1. **Query Modality Classification (Feature 7 / R1)**:
   - Identify where `classify_query_modality(query: str) -> QueryModality` should live (`backend/modules/explainer.py` or `backend/modules/domain_router.py`).
   - Define `QueryModality` enum: `PROCEDURAL`, `ANALYTICAL`, `CALCULATION`, `LEGAL_INTERPRETATION`.
   - Determine rules/patterns to classify Case 1 and Case 2 (and analytical queries involving "limitation", "notice", "time limit", "expire", "refund", "how long before", etc.) as non-procedural (`ANALYTICAL`), while preserving `PROCEDURAL` for standard operational step-by-step guides (e.g. Form 49A, DL renewal).
   - Trace how `explain_rag_result` in `explainer.py` constructs steps: ensure `dynamic_steps = []` when query is analytical, eliminating artificial "Review [Doc 1]", "Review [Doc 2]", "Verify Official Portal" checklists.
   - Trace `enhance_grounded_answer` in `llm.py`: ensure prompt instructs LLM not to generate steps when modality is non-procedural (`steps = []`), and post-processing does not inject default steps.
2. **Query Decomposition (Feature 8 / R3)**:
   - Identify how `decompose_query(query: str) -> list[str]` should be implemented and exposed (tests check `backend.rag.retriever`, `backend.rag.decomposition`, or `backend.modules.query_decomposer`).
   - Determine rule-based and semantic decomposition logic to split compound queries (e.g., splitting on `and`, `or`, multiple `?`, phrases like "Did ... and how many days...", "How long before ... and how do I get...").
   - Determine how decomposed sub-questions should feed into `RagRetriever.search` or `run_pipeline` so all distinct facets are retrieved and synthesized into a direct multi-part analytical answer.
3. **Synthesis Directives for Case 1 and Case 2**:
   - Ensure the synthesis prompt in `llm.py` / `explainer.py` explicitly demands answering ALL sub-questions with exact statutory calculations (3-year normal limitation date, 10-year ₹50L threshold, 7-30 days reply window, ~30 days PAN reactivation, employer cannot refund 20% TDS via payroll, claim via ITR).
4. **Deliver Report**:
   - Write comprehensive exploration report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m3_explorer_1\handoff.md`.
   - Send completion message to orchestrator.
