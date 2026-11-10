# Handoff Report: Milestone M2 Iteration 2 Challenger Verification

**Verdict**: **APPROVE**  
**Role**: challenger / critic / specialist (`challenger_cases_m2_iter2_rep`)  
**Date**: 2026-11-09  

---

## 1. Observation

### 1.1 Test Suite Verification Commands and Results
Direct empirical execution was performed across all mandated suites using Python 3.11:

1. **API Endpoints Regression Suite**:
   - Command: `py -m pytest tests/test_api.py -v`
   - Result: `57 passed, 2 warnings in 42.49s`
   - Output snippet:
     ```
     tests/test_api.py::test_ask_endpoint_supported_question_uses_real_backend_boundary PASSED [ 35%]
     tests/test_api.py::test_ask_endpoint_supports_multi_turn_conversational_context PASSED [ 56%]
     tests/test_api.py::test_scenario1_income_tax_bank_validation_prevents_defective_return_hallucination PASSED [ 98%]
     tests/test_api.py::test_scenario2_aadhaar_pvc_no_srn_provides_exact_tat_and_escalation PASSED [100%]
     ======================= 57 passed, 2 warnings in 42.49s =======================
     ```
   - All 7 previously failing tests in `test_api.py` now pass completely with 0 regressions.

2. **Milestone M2 Gating Regression**:
   - Command: `py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v`
   - Result: `1 passed, 18 deselected in 1.81s`
   - Output snippet:
     ```
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic PASSED [100%]
     ================= 1 passed, 18 deselected, 1 warning in 1.81s =================
     ```

3. **Challenger & Adversarial Gating Suites**:
   - Command: `py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py tests/test_adversarial_m2_confidence_gating_stress.py -v`
   - Result: `43 passed, 2 warnings in 9.40s`
   - Output snippet:
     ```
     tests/test_empirical_challenger_m2_confidence_gating.py (20 passed)
     tests/test_adversarial_m2_confidence_gating_stress.py (23 passed)
     ======================= 43 passed, 2 warnings in 9.40s ========================
     ```

4. **Adversarial Boundary Stress Suite**:
   - Command: `py -m pytest tests/test_challenger_cases_m2_iter2_stress.py -v`
   - Result: `20 passed, 1 warning in 32.33s`
   - Output snippet:
     ```
     tests/test_challenger_cases_m2_iter2_stress.py::TestConfidenceBoundaryPipelineRun::test_run_strictly_refuses_when_confidence_below_0_35[0.0] PASSED [  5%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestConfidenceBoundaryPipelineRun::test_run_proceeds_to_synthesis_when_confidence_at_least_0_35[0.35] PASSED [ 30%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestConfidenceBoundaryPipelineRunStream::test_run_stream_refuses_when_confidence_below_0_35 PASSED [ 65%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestConfidenceBoundaryPipelineRunStream::test_run_stream_proceeds_when_confidence_at_least_0_35 PASSED [ 70%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestOffTopicStatutoryRefusalGating::test_section_148a_query_with_119_2_b_chunk_strictly_refuses PASSED [ 75%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestOffTopicStatutoryRefusalGating::test_section_206aa_query_with_dl_chunk_strictly_refuses PASSED [ 80%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestLowRrfThresholdGate::test_low_rrf_score_refuses_even_if_confidence_high PASSED [ 90%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestMultiTurnContextAwareConfidence::test_anaphoric_followup_incorporates_context_topic_into_confidence PASSED [ 95%]
     tests/test_challenger_cases_m2_iter2_stress.py::TestLoanGuidelinesCitationTitleConformity::test_mudra_loan_citation_title_enhancement PASSED [100%]
     ======================= 20 passed, 1 warning in 32.33s ========================
     ```

5. **Web Search & Allowlist Regression Suite**:
   - Command: `py -m pytest tests/test_web_search.py -v`
   - Result: `30 passed, 1 warning in 24.26s`

### 1.2 Mathematical Boundary Assertions
Direct evaluation of `compute_rag_confidence` against off-topic statutory chunks and on-topic matching queries:

| Query Type | Candidate Chunk Evaluated | Raw Score | Confidence | Constraint Verification | Result |
|---|---|---|---|---|---|
| **Case 1 (148A Reassessment)** | Section 119(2)(b) Delay Condonation | 0.0800 | **0.0370** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 1 (148A Reassessment)** | Section 139(9) Defective Return | 0.0800 | **0.0741** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 1 (148A Reassessment)** | PAN Card FAQ (Reprint Form 49A) | 0.0800 | **0.0185** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 1 (148A Reassessment)** | Bank Account Pre-validation | 0.0800 | **0.0370** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 2 (206AA Inoperative PAN)**| EPFO Passbook / UAN Activation | 0.0800 | **0.0192** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 2 (206AA Inoperative PAN)**| Protean Biometric Failure (330) | 0.0800 | **0.0192** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 2 (206AA Inoperative PAN)**| Passport Tatkaal Checklist | 0.0800 | **0.0000** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 2 (206AA Inoperative PAN)**| Parivahan DL Renewal / Slots | 0.0800 | **0.0000** | `<= 0.25` and `< 0.35` | **PASS** |
| **Case 1 On-Topic** | Sections 148A + 149 Reassessment | 0.0380 | **0.9500** | `>= 0.35` | **PASS** |
| **Case 2 On-Topic** | Circular 03/2023 + Sec 206AA | 0.0380 | **0.9500** | `>= 0.35` | **PASS** |
| **Contextual Multi-Turn** | PAN Form 49A ("What documents...")| 0.0380 | **0.9500** | `>= 0.35` | **PASS** |

### 1.3 Target Code Review (`backend/pipeline.py`)
Lines 672-687 and lines 1070-1080:
```python
# In pipeline.run():
if top_hit.score < MIN_RRF_CONFIDENCE_THRESHOLD or rag_confidence < MIN_GROUNDING_CONFIDENCE_THRESHOLD:
    log_unresolved_query(...)
    return _finalize_answer(not_found_answer(...))

# In pipeline.run_stream():
if top_hit.score >= MIN_RRF_CONFIDENCE_THRESHOLD and rag_confidence >= MIN_GROUNDING_CONFIDENCE_THRESHOLD:
    rag_answer = explain_rag_result(...)
```
- `MIN_GROUNDING_CONFIDENCE_THRESHOLD = 0.35` is defined at the module level.
- Multi-turn queries pass `query=rag_query` (with cleaned contextual topic) into `compute_rag_confidence(rag_result, query=rag_query)`.

---

## 2. Logic Chain

1. **Rejection of Spurious Refusal for Medium-Confidence Procedural Queries**:
   - In Milestone M2 Iteration 1, the gate mistakenly required `rag_confidence >= WEB_SEARCH_CONFIDENCE_THRESHOLD (0.75)` to avoid refusal.
   - Legitimate procedural queries routinely score in `[0.35, 0.75)` (medium confidence), causing false `not_found_answer` rejections on standard civic inquiries (e.g. multi-turn follow-ups, document extraction).
   - Calibrating the refusal threshold to `MIN_GROUNDING_CONFIDENCE_THRESHOLD = 0.35` directly aligns the grounding gate with the RAG confidence scale (`low < 0.35 <= medium < 0.75 <= high`), successfully fixing all 7 regressions in `tests/test_api.py`.

2. **Strictness of Off-Topic Gating**:
   - In `backend/web_search/confidence.py` (lines 254-255), if statutory anchors are present in the query and unmatched in the retrieved chunk, confidence is subject to a hard mathematical ceiling:
     ```python
     if statutory_anchors and not matched_anchors:
         confidence = min(confidence, 0.25)
     ```
   - Even under adversarial RRF score saturation (scores up to 10.0), `confidence` remains `<= 0.25`, strictly below `MIN_GROUNDING_CONFIDENCE_THRESHOLD = 0.35`.
   - Consequently, any retrieval hit lacking statutory alignment is deterministically rejected by `pipeline.run()` and `pipeline.run_stream()`, triggering `not_found_answer` and preventing ungrounded hallucination or FALSE HIGH confidence badges.

3. **Multi-Turn Context Resolution**:
   - Follow-up queries with anaphora (e.g., `"What documents do I need for that?"`) incorporate `effective_context_topic` into `rag_query`.
   - By passing `rag_query` to `compute_rag_confidence(rag_result, query=rag_query)`, lexical overlap is evaluated against the resolved context rather than isolated pronouns, achieving `0.9500 >= 0.35` and avoiding false rejections.
   - If no valid context exists, the query continues to score `< 0.35` and is properly gated.

4. **Zero Predefined Responses Compliance**:
   - Code inspection of `backend/pipeline.py` confirms no hardcoded response text, canned steps, or mock disclaimers were introduced.
   - Responses are dynamically retrieved from Qdrant vector store and synthesized via grounded LLM synthesis.

---

## 3. Caveats

- **Scope Boundary**: Milestones M3 (modality classification, query decomposition) and M4 (corpus ingestion for reassessment and inoperative PAN) are scheduled for subsequent iterations; tests specifically asserting M3/M4 functionality in `tests/test_case1_case2_gating_regression.py` were deselected using `-k "test_tier1_relevance_confidence_gating"` per dispatch instructions.
- **Environment**: All tests executed on Windows x64 with Python 3.11.0; no platform-specific anomalies were detected.

---

## 4. Conclusion

**Verdict: APPROVE**

- The Milestone M2 Iteration 2 pre-synthesis relevance and confidence gating implementation is empirically verified, mathematically sound, and architecturally robust.
- The 0.35 threshold cleanly separates off-topic statutory chunks (which score `<= 0.25`, well below 0.35) from supported procedural inquiries (which score `>= 0.35`).
- 100% of required test suites pass with 0 failures:
  - `tests/test_api.py`: **57 / 57 passed** (100%)
  - `tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating"`: **1 / 1 passed** (100%)
  - `tests/test_empirical_challenger_m2_confidence_gating.py` + `tests/test_adversarial_m2_confidence_gating_stress.py`: **43 / 43 passed** (100%)
  - `tests/test_challenger_cases_m2_iter2_stress.py`: **20 / 20 passed** (100%)
  - `tests/test_web_search.py`: **30 / 30 passed** (100%)
- Total passing tests verified in this run: **151 passed, 0 failed**.

---

## 5. Verification Method

To independently reproduce and verify this assessment:

1. **Run full API regression**:
   ```powershell
   py -m pytest tests/test_api.py -v
   ```
   *Expected*: 57 passed, 0 failed.

2. **Run confidence gating regression**:
   ```powershell
   py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v
   ```
   *Expected*: 1 passed, 18 deselected.

3. **Run challenger empirical & adversarial stress harnesses**:
   ```powershell
   py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py tests/test_adversarial_m2_confidence_gating_stress.py tests/test_challenger_cases_m2_iter2_stress.py -v
   ```
   *Expected*: 63 passed, 0 failed.

4. **Run boundary condition mathematical assertion script**:
   ```powershell
   py -c "from backend.rag.models import RagDocument, RetrievalHit, RetrievalResult, SourceReference; from backend.web_search.confidence import compute_rag_confidence; doc = RagDocument(id='d1', content_hash='h', category='tax', text='Section 119(2)(b) delay', language='en', tags=('tax',), sources=(), warnings=()); hit = RetrievalHit(document=doc, score=0.08, rank=1, signals={}); res = RetrievalResult(query='Section 148A', hits=(hit,), status='s', searched_documents=10); conf = compute_rag_confidence(res, query='Section 148A notice for AY 2018-19'); assert conf <= 0.25 and conf < 0.35, f'Failed: {conf}'; print('Boundary assertion confirmed: score=', conf)"
   ```
   *Expected*: `Boundary assertion confirmed: score= 0.037037...`

5. **Invalidation Conditions**:
   - Any test failure in `test_api.py` or the gating stress suites.
   - Any off-topic statutory chunk scoring `>= 0.35` under `compute_rag_confidence`.
   - Any introduction of hardcoded or pre-canned procedural answers.
