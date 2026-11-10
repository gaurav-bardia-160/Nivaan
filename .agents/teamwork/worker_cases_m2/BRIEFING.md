# BRIEFING — 2026-11-09T13:25:00Z

## Mission
Implement Milestone M2: Pre-Synthesis Relevance & Confidence Gating in Nivaan by upgrading compute_rag_confidence with statutory entity alignment and lexical term overlap, preventing off-topic hits from scoring HIGH confidence, and connecting gating to pipeline.py and explainer.py.

## 🔒 My Identity
- Archetype: teamwork_worker
- Roles: implementer, qa, specialist
- Working directory: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m2
- Original parent: 39a4200a-88ea-4d70-9ed4-ca0bc59538f8
- Milestone: M2 (Pre-Synthesis Relevance & Confidence Gating)

## 🔒 Key Constraints
- File ownership: ONLY modify backend/web_search/confidence.py, backend/pipeline.py, and backend/modules/explainer.py (confidence evaluation & query passing).
- DO NOT edit test files or backend/rag/.
- Integrity Mandate: No hardcoding test results, no dummy implementations. Real state and genuine logic only.
- Rule: Zero Predefined Responses: Never introduce predefined or hardcoded responses.
- Pass query to compute_rag_confidence(rag_result, query). Penalize confidence strictly below 0.35 when statutory anchors in query lack support in retrieved chunk.

## Current Parent
- Conversation ID: 39a4200a-88ea-4d70-9ed4-ca0bc59538f8
- Updated: 2026-11-09T13:25:00Z

## Task Summary
- **What to build**: Multi-factor confidence gating in `compute_rag_confidence` with statutory entity alignment and lexical overlap; pass `query` in `backend/pipeline.py` and `backend/modules/explainer.py`; prevent false HIGH confidence badges on off-topic hits and trigger CRAG/honest refusal.
- **Success criteria**:
  1. `compute_rag_confidence(rag_result, query)` penalizes off-topic statutory queries < 0.35.
  2. `pipeline.py` and `explainer.py` pass query to `compute_rag_confidence`.
  3. `py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v` passes.
  4. `py -m pytest tests/test_web_search.py -v` passes without regressions.
- **Interface contracts**: `PROJECT.md` § Interface Contracts: Confidence Gating ↔ Pipeline & Explainer
- **Code layout**: `backend/web_search/confidence.py`, `backend/pipeline.py`, `backend/modules/explainer.py`

## Key Decisions Made
- `compute_rag_confidence` upgraded to multi-factor model: BaseScore * EntityAlignment * TermOverlap.
- If statutory anchors exist in query (sections, rules, circulars) and none match in candidate chunk, apply severe entity alignment penalty (0.15) and enforce hard ceiling < 0.35 (min(score, 0.25)).
- If `query` is omitted or None, return base RRF score for 100% backward compatibility with legacy tests.
- In `backend/pipeline.py`: passed `safe_text` as query to `compute_rag_confidence` across search gate (line 605), streaming gate (line 964), candidate grounding gate (lines 665 & 1058), and metadata dynamic confidence calculation (line 1076).
- In `backend/modules/explainer.py`: updated line 364 to compute dynamic confidence using `compute_rag_confidence(result, query=user_question)` with thresholds `>= 0.75` for HIGH, `>= 0.35` for MEDIUM, and `< 0.35` for LOW.

## Artifact Index
- `handoff.md` — Final handoff report upon completion
- `progress.md` — Progress tracker and heartbeat

## Change Tracker
- **Files modified**:
  - `backend/web_search/confidence.py`: multi-factor relevance and confidence gating with statutory anchor extraction and lexical overlap
  - `backend/pipeline.py`: passed query to `compute_rag_confidence` across RAG and web search gates
  - `backend/modules/explainer.py`: dynamic confidence badge calculation conditioned on query statutory alignment
- **Build status**: All targeted unit & regression tests PASS (100%)
- **Pending issues**: None

## Quality Status
- **Build/test result**:
  - `test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic`: PASSED
  - `test_tier3_decomposition_with_confidence_gating`: PASSED
  - `tests/test_web_search.py`: 30/30 PASSED
  - `tests/test_domain_router.py`: 59/59 PASSED
- **Lint status**: Clean
- **Tests added/modified**: Covered by existing test specifications in tests/test_case1_case2_gating_regression.py

## Loaded Skills
- None
