# Handoff Report: Independent Quality & Adversarial Review of Milestone M2

**Agent**: `reviewer_cases_m2_2`  
**Role**: Teamwork Reviewer & Adversarial Critic (`teamwork_reviewer`)  
**Working Directory**: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m2_2`  
**Date**: 2026-11-09T13:46:00Z  
**Recipient**: `39a4200a-88ea-4d70-9ed4-ca0bc59538f8`  
**Verdict**: **`REQUEST_CHANGES`**

---

## 1. Observation

1. **Targeted Milestone M2 Verification Suite Passes**:
   - Running `py -m pytest tests/test_case1_case2_gating_regression.py -k "relevance_confidence_gating or decomposition_with_confidence_gating" -v` executed with code 0:
     ```text
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic PASSED [ 50%]
     tests/test_case1_case2_gating_regression.py::TestTier3CrossFeatureCombinations::test_tier3_decomposition_with_confidence_gating PASSED [100%]
     2 passed, 17 deselected in 43.58s
     ```
   - Running `py -m pytest tests/test_web_search.py -v` executed with code 0:
     ```text
     30 passed, 1 warning in 37.63s
     ```
   - Running `py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py -v` executed with code 0:
     ```text
     22 passed, 1 warning in 4.08s
     ```
   - Running `py -m pytest tests/test_adversarial_m2_confidence_gating_stress.py -v` executed with code 0:
     ```text
     21 passed, 2 warnings in 28.55s
     ```

2. **Severe Regression in Pipeline Grounding Gate (`backend/pipeline.py`)**:
   In `backend/pipeline.py` lines 664–681:
   ```python
   if rag_result is not None and rag_result.hits:
       top_hit = rag_result.hits[0]
       from backend.web_search.confidence import compute_rag_confidence
       rag_confidence = compute_rag_confidence(rag_result, query=safe_text)
       # Strict Grounding Gate: If top chunk is below confidence threshold or lacks relevance alignment, refuse to guess
       if top_hit.score < MIN_RRF_CONFIDENCE_THRESHOLD or rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD:
           log_unresolved_query(
               safe_text,
               reason="low_retrieval_confidence",
               domain=supported_category(search_text) if 'supported_category' in globals() else None,
               top_score=top_hit.score,
               conversation_id=parsed_request.conversation_id,
           )
           return _finalize_answer(
               not_found_answer(safe_text, masked_items=masked_items),
               request=parsed_request,
               safe_question=masked_question.text or safe_text,
               target_lang=target_lang,
               rl_arm=bandit_action.name,
           )
   ```
   And in `run_stream` line 1060:
   ```python
   if top_hit.score >= MIN_RRF_CONFIDENCE_THRESHOLD and rag_confidence >= WEB_SEARCH_CONFIDENCE_THRESHOLD:
   ```

3. **Threshold Definition in `backend/config.py`**:
   In `backend/config.py` line 33:
   ```python
   WEB_SEARCH_CONFIDENCE_THRESHOLD = float(os.getenv("WEB_SEARCH_CONFIDENCE_THRESHOLD", "0.75"))
   ```
   `WEB_SEARCH_CONFIDENCE_THRESHOLD` is explicitly configured to `0.75`.

4. **Regressions Observed in Existing Test Suite (`tests/test_api.py`)**:
   Running `py -m pytest tests/test_domain_router.py tests/test_api.py -v` resulted in:
   ```text
   FAILED tests/test_api.py::test_pipeline_returns_answer_for_supported_question
   FAILED tests/test_api.py::test_live_rag_is_feature_flagged_and_returns_cited_candidate_evidence
   FAILED tests/test_api.py::test_ask_endpoint_supported_question_uses_real_backend_boundary
   FAILED tests/test_api.py::test_ask_endpoint_non_english_request_warns_without_fake_translation
   FAILED tests/test_api.py::test_ask_endpoint_defaults_to_question_input_type
   FAILED tests/test_api.py::test_ask_endpoint_supports_multi_turn_conversational_context
   FAILED tests/test_api.py::test_aadhaar_source_url_is_not_beta - AttributeError: 'NoneType' object has no attribute 'lower'
   7 failed, 109 passed in 120.90s
   ```
   Verbatim failure reason across all 7 tests:
   ```text
   AssertionError: assert 'pan' in 'no verified guide found'
   where 'no verified guide found' = Answer.title
   ```

5. **Empirical Reproduction of Premature Refusal**:
   Executing:
   `py -c "from backend.pipeline import run; from backend.schemas import AskRequest; ans = run(AskRequest(question='What should I check in a loan agreement?', language='en')); print('Title:', ans.title, 'Conf:', ans.confidence)"`
   Yields:
   ```text
   Title: No verified guide found Conf: low
   ```
   For `"How do I get PAN card?"`:
   `res.hits[0].score = 0.0197`, `compute_rag_confidence` returns `0.493` ("medium"). Because $0.493 < 0.75$, it is blocked at line 667 and emits `not_found_answer`.

---

## 2. Logic Chain

1. From **Observation 1.3**, `WEB_SEARCH_CONFIDENCE_THRESHOLD = 0.75`. This threshold was designed to trigger live web search (CRAG) when RAG retrieval confidence is below 0.75, allowing the system to seek better official web sources.
2. From **Observation 1.2**, in `backend/pipeline.py` line 667 and line 1060, `rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD` was erroneously inserted into the strict grounding refusal gate.
3. According to `PROJECT.md` (Features 5 & 6, Interface Contracts) and `explainer.py:366`:
   - Confidence $\ge 0.75$ is `"high"`.
   - Confidence in $[0.35, 0.75)$ is `"medium"`.
   - Confidence $< 0.35$ is `"low"` (statutory mismatch or term overlap failure).
   - The contract explicitly states: *"trigger live CRAG when retrieved chunks lack semantic alignment (< 0.35) or emit honest refusal if ungrounded"*.
4. From **Observations 1.4 and 1.5**, because line 667 requires `rag_confidence >= 0.75` for synthesis, ALL valid civic queries whose RRF scores place them in the `"medium"` confidence band ($0.35 \le \text{confidence} < 0.75$) are treated as ungrounded and immediately rejected with `not_found_answer` ("No verified guide found").
5. This breaks backward compatibility for standard supported queries across the entire civic platform (including loan agreement review, PAN card application, and Aadhaar card queries), producing 7 test failures in `tests/test_api.py`.
6. Therefore, the implementation in `backend/pipeline.py` violates the interface contract and introduces a severe system-wide regression.

---

## 3. Review Findings & Adversarial Assessment

### Finding 1: [Critical / Major Defect] Conflation of CRAG Web Search Threshold (0.75) with Strict Grounding Refusal Gate (0.35)
- **Location**: `backend/pipeline.py:667` (in `run()`) and `backend/pipeline.py:1060` (in `run_stream()`)
- **Problem**:
  Line 667 checks `if top_hit.score < MIN_RRF_CONFIDENCE_THRESHOLD or rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD:` where `WEB_SEARCH_CONFIDENCE_THRESHOLD = 0.75`.
  Line 1060 checks `if top_hit.score >= MIN_RRF_CONFIDENCE_THRESHOLD and rag_confidence >= WEB_SEARCH_CONFIDENCE_THRESHOLD:`.
  This rejects legitimate "medium" confidence queries ($[0.35, 0.75)$) with an honest refusal (`not_found_answer`), breaking standard RAG synthesis across the application.
- **Required Fix**:
  Use `0.35` (the low confidence / statutory mismatch cutoff) or introduce a dedicated constant `MIN_GROUNDING_CONFIDENCE_THRESHOLD = 0.35`:
  - In `backend/pipeline.py:667`:
    `if top_hit.score < MIN_RRF_CONFIDENCE_THRESHOLD or rag_confidence < 0.35:`
  - In `backend/pipeline.py:1060`:
    `if top_hit.score >= MIN_RRF_CONFIDENCE_THRESHOLD and rag_confidence >= 0.35:`

### Finding 2: [Minor / Code Quality] Greedy Normalization of Provision Anchors 139 and 119
- **Location**: `backend/web_search/confidence.py:57–60`
- **Problem**:
  ```python
  if cleaned.startswith("139(9)") or cleaned.startswith("139"):
      return "139(9)"
  if cleaned.startswith("119(2)(b)") or cleaned.startswith("119"):
      return "119(2)(b)"
  ```
  Any query referencing Section 139(1) (filing deadlines) or Section 119(2)(a) will be normalized to "139(9)" or "119(2)(b)".
- **Suggestion**:
  Normalize only exact subsection prefixes (e.g. `139(9)`), and keep base section `139` distinct from specific subsections.

### Integrity Verification
- **Hardcoded test outputs**: NONE. Anchor extraction and term overlap are generic algorithms.
- **Facades / Dummy code**: NONE. Logic executes genuine multi-factor calculations.
- **Shortcuts / Rule violations**: `Zero Predefined Responses` rule verified; `test_tier2_adversarial_zero_predefined_responses_compliance` passes.

---

## 4. Caveats

- Milestone M3 requirements (`classify_query_modality`, `steps == []` checklist elimination, and query decomposition) were excluded from this M2 evaluation per project roadmap boundaries.
- Live web search tests in `test_web_search.py` pass; however, web search was disabled during local API testing, exposing the strict grounding gate regression.

---

## 5. Conclusion

Milestone M2 cannot be approved in its current state due to the critical regression in `backend/pipeline.py` lines 667 and 1060:
- **Verdict**: **`REQUEST_CHANGES`**
- **Action Required**: Worker must update `backend/pipeline.py` lines 667 and 1060 to use `0.35` (the low confidence threshold) instead of `WEB_SEARCH_CONFIDENCE_THRESHOLD` (0.75), and verify that `py -m pytest tests/test_api.py -v` passes.

---

## 6. Verification Method

1. **Verify Regression**:
   ```bash
   py -m pytest tests/test_api.py -k "test_pipeline_returns_answer_for_supported_question or test_ask_endpoint_supported_question_uses_real_backend_boundary" -v
   ```
   *Expected Current Output*: FAILED (emits "No verified guide found" because confidence 0.493 < 0.75).

2. **Verify M2 Confidence Scoring & Gating**:
   ```bash
   py -m pytest tests/test_case1_case2_gating_regression.py -k "relevance_confidence_gating or decomposition_with_confidence_gating" -v
   py -m pytest tests/test_web_search.py -v
   py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py -v
   py -m pytest tests/test_adversarial_m2_confidence_gating_stress.py -v
   ```

3. **Invalidation Condition**:
   Once lines 667 and 1060 in `backend/pipeline.py` are changed from `WEB_SEARCH_CONFIDENCE_THRESHOLD` (0.75) to `0.35`, all 7 failing tests in `tests/test_api.py` will pass without compromising off-topic gating.
