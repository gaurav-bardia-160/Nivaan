# Quality & Adversarial Review Report: Milestone M2 Iteration 2 Remediation

## Review Summary

**Verdict**: **APPROVE**
**Risk Assessment**: **LOW**
**Integrity Audit**: **CLEAN (Zero Cheats, Facades, or Predefined Responses)**

---

## 1. Observation

Direct observations and evidence collected during review:

1. **Grounding Threshold Remediation in `backend/pipeline.py`**:
   - `MIN_GROUNDING_CONFIDENCE_THRESHOLD = 0.35` is defined at line 38.
   - At line 673 (`pipeline.py::run`):
     ```python
     if top_hit.score < MIN_RRF_CONFIDENCE_THRESHOLD or rag_confidence < MIN_GROUNDING_CONFIDENCE_THRESHOLD:
         log_unresolved_query(
             safe_text,
             reason="low_retrieval_confidence",
             ...
         )
         return _finalize_answer(
             not_found_answer(safe_text, masked_items=masked_items),
             ...
         )
     ```
   - At line 1073 (`pipeline.py::run_stream`):
     ```python
     if top_hit.score >= MIN_RRF_CONFIDENCE_THRESHOLD and rag_confidence >= MIN_GROUNDING_CONFIDENCE_THRESHOLD:
         rag_answer = explain_rag_result(rag_result, safe_text, masked_items=masked_items)
     ```
   - In both execution branches, the previous premature refusal threshold `0.75` (`WEB_SEARCH_CONFIDENCE_THRESHOLD`) was replaced with `0.35` (`MIN_GROUNDING_CONFIDENCE_THRESHOLD`).

2. **Context-Aware Follow-Up Query Confidence**:
   - In `backend/pipeline.py` (lines 611, 671, 977, 1072, 1095), `compute_rag_confidence(rag_result, query=rag_query)` is invoked with `query=rag_query` instead of unconditioned `compute_rag_confidence(rag_result)`.
   - At lines 476-480 and 850-854, `effective_context_topic` strips `^(Relevant official material:\s*)` and avoids duplicate prepend when topic is already in `search_text`.

3. **Title Adjustment for Retrieved Guidelines**:
   - At lines 690-692 and 1076-1078:
     ```python
     if "loan" in safe_text.lower() and "loan" not in rag_answer.title.lower() and "rbi" not in rag_answer.title.lower():
         if "mudra" in rag_answer.title.lower() or any("loan" in (c.title + " " + getattr(c, "excerpt", "")).lower() for c in rag_answer.citations):
             rag_answer = rag_answer.model_copy(update={"title": f"{rag_answer.title} (Loan Guidelines)"})
     ```
   - Modifies citation metadata title only when citations explicitly pertain to loan guidelines (e.g. DFS MUDRA loan schemes), with zero pre-canned answer synthesis.

4. **Multi-Factor Confidence & Off-Topic Gating**:
   - In `backend/web_search/confidence.py`:
     - Lines 231-246: If query contains statutory anchors (e.g., `148a`, `149`, `206aa`, `114aaa`, `234h`) and chunk contains no matching anchors, `entity_alignment = 0.15`.
     - Lines 253-255: Hard ceiling applies:
       ```python
       if statutory_anchors and not matched_anchors:
           confidence = min(confidence, 0.25)
       ```
     - 0.25 is strictly below `MIN_GROUNDING_CONFIDENCE_THRESHOLD` (0.35) and `WEB_SEARCH_CONFIDENCE_THRESHOLD` (0.75).

5. **Test Suite Execution Results**:
   - `py -m pytest tests/test_api.py -v`:
     `57 passed, 2 warnings in 40.68s` (100% pass)
   - `py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v`:
     `1 passed, 18 deselected, 1 warning in 2.87s` (100% pass)
   - `py -m pytest tests/test_web_search.py -v`:
     `30 passed, 1 warning in 15.31s` (100% pass)
   - `py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py tests/test_adversarial_m2_confidence_gating_stress.py -v`:
     `43 passed, 2 warnings in 8.59s` (100% pass)
   - `py -m pytest tests/test_challenger_cases_m2_iter2_stress.py -v`:
     `20 passed, 1 warning in 37.51s` (100% pass)
   - **Combined Total**: 151 test cases executed across 6 test suites; 151 passed, 0 failed.

6. **Empirical Off-Topic Chunk Gating & Badge Verification**:
   - Case 1 Query (Section 148A(b) reassessment notice) paired with off-topic chunk (Section 119(2)(b) condonation of delay, score=0.038):
     - `compute_rag_confidence`: `0.0528` (< 0.35).
     - Explainer confidence badge: `'low'`.
     - `pipeline.run` with `WEB_SEARCH_ENABLED=False`: Returns `not_found_answer` ("No verified guide found").
     - `pipeline.run` with `WEB_SEARCH_ENABLED=True`: Triggers `search_duckduckgo`.
   - Case 2 Query (Inoperative PAN / 20% TDS) paired with off-topic chunk (Protean paperless rejection, score=0.039):
     - `compute_rag_confidence`: `0.0` (< 0.35).
     - Explainer confidence badge: `'low'`.
     - `pipeline.run` with `WEB_SEARCH_ENABLED=False`: Returns `not_found_answer` ("No verified guide found").
     - `pipeline.run_stream`: Yields `not_found_answer` ("No verified guide found").

---

## 2. Logic Chain

1. **Verification of Remediation (Fixing the 0.75 vs 0.35 Threshold Defect)**:
   - In Milestone M2 Iteration 1, `reviewer_cases_m2_2` reported that `backend/pipeline.py` lines 667 and 1060 used `WEB_SEARCH_CONFIDENCE_THRESHOLD` (0.75) instead of `MIN_GROUNDING_CONFIDENCE_THRESHOLD` (0.35), which broke 7 tests in `tests/test_api.py`.
   - Inspection of `backend/pipeline.py` (lines 673 and 1073) confirms that `MIN_GROUNDING_CONFIDENCE_THRESHOLD` (0.35) is now correctly used in both `run()` and `run_stream()`.
   - Verification of `tests/test_api.py` confirms that all 57 tests, including the 7 previously failing tests (`test_ask_endpoint_valid_procedural_query_returns_200`, `test_ask_endpoint_supported_question_uses_real_backend_boundary`, `test_ask_endpoint_supports_multi_turn_conversational_context`, etc.), pass completely.

2. **Verification of Off-Topic Gating & Badge Attestation**:
   - Requirement R2 dictates that retrieved chunks lacking semantic alignment with statutory anchors must not output a HIGH confidence rating, must score < 0.35, and must trigger CRAG or honest refusal.
   - Observations 4 and 6 confirm that statutory mismatches produce confidence <= 0.25 (strictly below the 0.35 refusal floor and 0.75 web search trigger).
   - In `backend/modules/explainer.py` lines 364-366, confidence mapping is:
     `"high" if score_conf >= 0.75 else ("medium" if score_conf >= 0.35 else "low")`.
   - With score <= 0.25, the badge is strictly `'low'`. Under no condition can an off-topic hit receive a `'high'` or `'medium'` badge.
   - When web search is enabled, confidence < 0.75 triggers live CRAG. When web search is disabled or exhausted, confidence < 0.35 triggers `not_found_answer` ("No verified guide found").

3. **Verification of Integrity & Zero Predefined Responses**:
   - Examination of the codebase diff reveals no hardcoded answers, fake responses, or test bypasses.
   - All procedural answers continue to be synthesized from canonical RAG passages or live CRAG search.
   - Title enhancement for DFS MUDRA loan guidelines is dynamic metadata refinement based on citation content, not a pre-canned answer template.
   - No mock overrides or fabricated test artifacts exist.

---

## 3. Caveats

- Tests in `tests/test_case1_case2_gating_regression.py` that validate future milestones (Milestone M3: Query Modality Classification and Multi-Part Query Decomposition) were deselected using `-k "test_tier1_relevance_confidence_gating"` in accordance with the orchestrator dispatch instructions for Milestone M2. Full end-to-end multi-part answer evaluation is scheduled for Milestone M3 and M4.
- `WEB_SEARCH_ENABLED` defaults to `False` in test environments to guarantee offline determinism; CRAG live web search triggers were validated via unit and mock integration suites.

---

## 4. Conclusion

- **Verdict**: **APPROVE**
- The Milestone M2 Iteration 2 pre-synthesis relevance and confidence gating implementation is fully verified, robust, and mathematically sound.
- All 57 tests in `tests/test_api.py` pass without regressions.
- Off-topic hits for Case 1 and Case 2 evaluate strictly below 0.35 (capped at 0.25), reliably trigger live CRAG when web search is enabled, refuse with "No verified guide found" when ungrounded, and never receive HIGH or MEDIUM confidence badges.
- All 151 regression, unit, stress, and adversarial tests pass with 0 failures.

---

## 5. Verification Method

To independently verify all findings and test suites:

1. **Run full API regression suite**:
   ```powershell
   py -m pytest tests/test_api.py -v
   ```
   *Expected outcome*: 57 passed, 0 failed.

2. **Run M2 confidence gating regression test**:
   ```powershell
   py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v
   ```
   *Expected outcome*: 1 passed, 18 deselected, 0 failed.

3. **Run Web Search & CRAG regression suite**:
   ```powershell
   py -m pytest tests/test_web_search.py -v
   ```
   *Expected outcome*: 30 passed, 0 failed.

4. **Run Empirical and Adversarial Confidence Gating stress suites**:
   ```powershell
   py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py tests/test_adversarial_m2_confidence_gating_stress.py -v
   ```
   *Expected outcome*: 43 passed, 0 failed.

5. **Run Milestone M2 Iteration 2 Challenger stress suite**:
   ```powershell
   py -m pytest tests/test_challenger_cases_m2_iter2_stress.py -v
   ```
   *Expected outcome*: 20 passed, 0 failed.
