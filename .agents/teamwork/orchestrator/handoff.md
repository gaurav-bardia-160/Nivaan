# Orchestrator Soft Handoff — Case 1 & Case 2 Pipeline Remediation

**Author**: `orchestrator` (Top-Level Project Orchestrator, Generation 1)  
**Date**: 2026-11-09T13:52:00Z  
**Type**: Soft Handoff (Self-Succession at 16 Spawns)  
**Recipient**: Successor Orchestrator (Generation 2)  
**Parent Conversation ID**: `63247ec2-b8b8-40d2-a5ba-cd61604e4af3`

---

## 1. Milestone State

| # | Name | Scope | Dependencies | Status | Notes |
|---|------|-------|-------------|--------|-------|
| E2E | Independent E2E Testing Suite | Requirements Tiers 1-4 in `tests/test_case1_case2_gating_regression.py` | none | **DONE** | 19 tests authored; baseline `14 failed, 5 passed` in `TEST_READY.md`. |
| M1 | Corpus Ingestion & Retriever Coverage | Features 1, 2, 3, 4 | none | **DONE** | Passed Gate Iteration 1 with 5/5 APPROVE/CLEAN verdicts. 73 unit tests pass with zero regressions. |
| M2 | Pre-Synthesis Relevance & Confidence Gating | Features 5, 6 | M1 | **IN_PROGRESS** (Iteration 1: Gate FAIL on reviewer REQUEST_CHANGES; ready for Iteration 2 remediation) | Implemented by `worker_cases_m2`. `reviewer_cases_m2_2` caught regression in `pipeline.py:667, 1060` (used 0.75 instead of 0.35, breaking `test_api.py`). |
| M3 | Response Shape & Multi-Part Query Decomposition | Features 7, 8 | M1, M2 | **PLANNED** | Spec defined in `survey_arch_gating_3/handoff.md`. Needs `classify_query_modality`, checklist elimination (`steps = []`), and `decompose_query`. |
| M4 | Full Regression Verification & Coverage Hardening | Feature 9 | M1, M2, M3, E2E | **PLANNED** | Pass 100% of `tests/test_case1_case2_gating_regression.py` (19/19) and full repository test suite. |

---

## 2. Active Subagents
- All 16 subagents from Generation 1 have fully completed and are retired.
- No subagents are currently running.

---

## 3. Pending Decisions & Immediate Next Steps for Successor

### Immediate Step 1: Milestone M2 Iteration 2 Remediation
1. Spawn `worker_cases_m2_iter2` (`teamwork_worker`) with:
   - Scope: `backend/pipeline.py` lines 667 and 1060.
   - Issue identified by `reviewer_cases_m2_2`:
     Line 667 checks `if top_hit.score < MIN_RRF_CONFIDENCE_THRESHOLD or rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD:` where `WEB_SEARCH_CONFIDENCE_THRESHOLD = 0.75`.
     Line 1060 checks `if top_hit.score >= MIN_RRF_CONFIDENCE_THRESHOLD and rag_confidence >= WEB_SEARCH_CONFIDENCE_THRESHOLD:`.
     This erroneously rejects legitimate medium-confidence queries ($[0.35, 0.75)$) with an ungrounded refusal ("No verified guide found"), causing 7 failures in `tests/test_api.py`.
   - Fix: Change `WEB_SEARCH_CONFIDENCE_THRESHOLD` to `0.35` (or define `MIN_GROUNDING_CONFIDENCE_THRESHOLD = 0.35`) in `backend/pipeline.py` lines 667 and 1060.
   - Verification command for worker: `py -m pytest tests/test_api.py tests/test_case1_case2_gating_regression.py -k "relevance_confidence_gating" -v` (must pass 100%).
2. Run M2 Iteration 2 Gate (Reviewers, Challengers, Auditor). Once gate passes, update `GATE_STATUS.md` and `PROJECT.md` to mark M2 as **DONE**.

### Step 2: Milestone M3 Implementation (Response Shape & Multi-Part Query Decomposition)
1. Spawn `worker_cases_m3` (`teamwork_worker`) for Features 7 & 8:
   - Exclusively owns: `backend/modules/explainer.py`, `backend/modules/llm.py`, `backend/rag/retriever.py` (or `backend/rag/decomposition.py`), `backend/web_search/synthesizer.py`.
   - Implement `classify_query_modality(query: str) -> QueryModality`:
     - Distinguish `PROCEDURAL` from `ANALYTICAL`, `CALCULATION`, `LEGAL_INTERPRETATION`.
   - In `backend/modules/explainer.py:352-361`:
     - Eliminate the 3-step checklist (`Review [Doc 1]`, `Review [Doc 2]`, `Verify Official Portal`) for non-procedural queries: set `steps = []`.
     - In summary, provide substantive analytical explanations.
   - In `backend/modules/llm.py:802-806`:
     - Do not re-inject dynamic steps for non-procedural queries when `steps` is empty.
   - In `backend/rag/retriever.py`:
     - Implement `decompose_query(query: str) -> list[str]` to isolate sub-questions for compound queries (e.g. Case 1: limitation vs reply window; Case 2: reactivation timeline vs ITR refund).
   - In `backend/web_search/synthesizer.py:391-396`:
     - Remove the step count penalty from confidence evaluation for analytical queries.
   - Verification: `py -m pytest tests/test_case1_case2_gating_regression.py -k "query_modality or checklist_elimination or query_decomposition or offline_pytest or multipart_synthesis" -v`.
2. Run M3 Gate (Reviewers, Challengers, Auditor).

### Step 3: Milestone M4 Full Verification & User Report
1. Run full test suite: `py -m pytest tests/test_case1_case2_gating_regression.py -v` (all 19 tests must pass).
2. Run regression checks: `py -m pytest tests/test_scenes_1_to_3_regression.py tests/test_api.py -v`.
3. Report verified outcome to parent (`63247ec2-b8b8-40d2-a5ba-cd61604e4af3`) via `send_message`.

---

## 4. Key Artifacts
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`: Authoritative user request.
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`: Roadmap, 10 features, milestones, interface contracts.
- `c:\Users\gaura\Documents\nivaan\TEST_READY.md`: E2E test suite baseline and mapping.
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\GATE_STATUS.md`: Authoritative gate verdicts.
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\orchestrator\progress.md`: Execution checklist.
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3\handoff.md`: Technical architectural specifications for gating, scaffolding, and decomposition.
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m2_2\handoff.md`: Exact diagnosis of the M2 pipeline regression to be fixed by `worker_cases_m2_iter2`.
