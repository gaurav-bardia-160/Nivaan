# Dispatch for worker_cases_m2

## Task
You are `worker_cases_m2`, an implementation worker agent (`teamwork_worker`).
Working directory: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m2`
Original request: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
Project roadmap: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
Survey architecture report: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\handoff.md`

## Mandatory Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Rule: Zero Predefined Responses
NEVER use or re-introduce predefined, hardcoded, or pre-canned responses. All answers must be dynamically generated from RAG retrieval, live search, and dynamic local LLM synthesis.

## Scope & File Ownership
You exclusively own and may edit ONLY the following files:
- `backend/web_search/confidence.py`
- `backend/pipeline.py`
- `backend/modules/explainer.py` (specifically lines relating to confidence evaluation and passing query to confidence computation)

You MUST NOT edit test files or `backend/rag/`.

## Detailed Implementation Directives (Milestone M2: Pre-Synthesis Relevance & Confidence Gating)
Refer to Track 2 (Section 2.1 & 2.2) of `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\handoff.md`:

1. **Multi-Factor Confidence Function in `backend/web_search/confidence.py`**:
   - Update `compute_rag_confidence`:
     ```python
     def compute_rag_confidence(
         rag_result: Any,
         query: str | None = None,
     ) -> float:
     ```
   - Maintain backward compatibility if `query` is `None` or omitted.
   - Enforce statutory entity alignment:
     - Extract statutory anchors from `query` (e.g. `148a`, `148`, `149`, `151`, `206aa`, `114aaa`, `234h`, `reassessment`, etc.).
     - If query contains statutory anchors, verify if the top retrieved chunk text, title, section, or tags contain support for those anchors.
     - If the top retrieved chunk completely lacks support for the statutory anchors (e.g., Section 119(2)(b) condonation or generic PAN FAQ retrieved for a Section 148A reassessment query), apply a severe penalty capping confidence strictly below `0.35` (e.g., `0.15`–`0.25`).
   - Enforce lexical overlap factor:
     - Compute content term overlap between query and chunk, avoiding high confidence for accidental single-word collisions.

2. **Integration in `backend/pipeline.py` & `backend/modules/explainer.py`**:
   - In `backend/pipeline.py` (around lines 605, 962, 1076), ensure `compute_rag_confidence(rag_result, query=user_query)` passes the query.
   - When confidence is below `WEB_SEARCH_CONFIDENCE_THRESHOLD` (0.35):
     - Pipeline will trigger live CRAG search on official allowlisted domains.
     - If live search also lacks evidence, output honest refusal with `confidence="low"`.
     - Prevent off-topic chunks from receiving a `HIGH` confidence badge.
   - In `backend/modules/explainer.py` (around lines 364–366):
     - Ensure confidence badge calculation incorporates the gated score or entity alignment, never emitting `"high"` when statutory alignment fails.

3. **Verification**:
   - Run: `py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v`
     Must turn this test from FAILED to PASSED!
   - Run: `py -m pytest tests/test_web_search.py tests/test_pipeline.py -v`
     Verify zero regressions across existing web search and pipeline tests.
   - Document verification commands and output in `handoff.md`.

Write your handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m2\handoff.md`.


## 2026-11-09T13:07:35Z
[Message] timestamp=2026-11-09T13:07:35Z sender=39a4200a-88ea-4d70-9ed4-ca0bc59538f8 priority=MESSAGE_PRIORITY_HIGH content=You are worker_cases_m2, an implementation worker agent (teamwork_worker).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m2
You MUST read:
1. c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
2. c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
3. c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m2\DISPATCH.md
4. c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\handoff.md (specifically Track 2)

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Rule: Zero Predefined Responses: NEVER use or re-introduce predefined, hardcoded, or pre-canned responses.

File ownership:
- backend/web_search/confidence.py
- backend/pipeline.py
- backend/modules/explainer.py (confidence badge calculation & query passing)
Do not edit test files or backend/rag/.

Implement Milestone M2 (Pre-Synthesis Relevance & Confidence Gating):
1. Upgrade `compute_rag_confidence(rag_result, query=None)` in `backend/web_search/confidence.py` with statutory entity alignment and term overlap.
2. If query mentions statutory sections (148A, 149, 206AA, 234H, etc.) and top hit lacks support, penalize confidence strictly below 0.35.
3. Pass `query` to `compute_rag_confidence` in `backend/pipeline.py` and `backend/modules/explainer.py`.
4. Ensure off-topic hits do not receive HIGH confidence badges.
5. Run tests:
   py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v
   py -m pytest tests/test_web_search.py -v
6. Write your complete handoff report to c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m2\handoff.md.
When complete, send a message to caller with your handoff path and summary.
