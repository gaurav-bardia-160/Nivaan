# Handoff Report: Milestone M2 Empirical Adversarial Verification

**Agent ID**: `challenger_cases_m2_1`  
**Role**: Empirical Adversarial Verifier (`teamwork_challenger`)  
**Working Directory**: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_cases_m2_1`  
**Date**: 2026-11-09T13:35:00Z  
**Recipient**: `39a4200a-88ea-4d70-9ed4-ca0bc59538f8`  
**Verdict**: **APPROVE**

---

## 1. Observation

1. **Test Suite Verification**:
   - Running the M2 targeted regression command:
     ```powershell
     py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v
     ```
     Yielded verbatim:
     ```text
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic PASSED [100%]
     ================= 1 passed, 18 deselected, 1 warning in 3.64s =================
     ```
   - Running the cross-feature decomposition gating test:
     ```powershell
     py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating or test_tier3_decomposition_with_confidence_gating" -v
     ```
     Yielded verbatim:
     ```text
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic PASSED [ 50%]
     tests/test_case1_case2_gating_regression.py::TestTier3CrossFeatureCombinations::test_tier3_decomposition_with_confidence_gating PASSED [100%]
     ================ 2 passed, 17 deselected, 1 warning in 44.06s =================
     ```
   - Running the entire web search regression test suite:
     ```powershell
     py -m pytest tests/test_web_search.py -v
     ```
     Yielded verbatim:
     ```text
     ================== 30 passed, 1 warning in 64.01s (0:01:04) ===================
     ```

2. **Empirical Adversarial Stress Harness (`tests/test_empirical_challenger_m2_confidence_gating.py`)**:
   An independent 22-test adversarial harness was written and executed:
   ```powershell
   py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py -v
   ```
   Yielded verbatim:
   ```text
   ======================== 22 passed, 1 warning in 2.25s ========================
   ```
   Specific test suites and observed empirical results:
   - **Reassessment Queries (Section 148A, Section 149) paired with off-topic chunks**:
     - Paired with Section 119(2)(b) condonation: `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
     - Paired with Section 139(9) defective return: `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
     - Paired with PAN FAQ (Form 49A corrections): `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
     - Paired with Bank Account pre-validation: `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
   - **Inoperative PAN / TDS Queries (Section 206AA, Section 234H, Circular 03/2023) paired with off-topic chunks**:
     - Paired with EPFO passbook / UAN activation: `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
     - Paired with Protean paperless application rejection (biometric 330): `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
     - Paired with Passport Tatkaal checklist: `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
     - Paired with Sarathi DL renewal: `confidence = 0.150` (< 0.35, cap $\le 0.25$), explainer `confidence = "low"`.
   - **Extreme RRF Score Saturation Attacks**:
     - Raw scores tested: `0.040, 0.080, 0.150, 0.500, 1.000, 10.000`.
     - In all cases with statutory mismatch, final confidence was strictly capped at $\le 0.25$ and explainer mapped to `"low"`.
   - **Positive Controls (On-Topic Matching Chunks)**:
     - Case 1 query + matching Section 148A/149 statutory chunk: `confidence = 1.000` ($\ge 0.75$), explainer `confidence = "high"`.
     - Case 2 query + matching Circular 03/2023 / Section 206AA chunk: `confidence = 1.000` ($\ge 0.75$), explainer `confidence = "high"`.
   - **Boundary Conditions & Backward Compatibility**:
     - `rag_result=None` $\to 0.0$.
     - `hits=()` $\to 0.0$.
     - `score <= 0.0` $\to 0.0$.
     - `query=None` or `query="   "` $\to$ returns unconditioned base score $\min(\text{top\_score} / 0.040, 1.0)$, preserving backward compatibility for legacy callers.

3. **Code Inspection**:
   - `backend/web_search/confidence.py`:
     - Lines 231–246: Extracts statutory anchors (`148a`, `149`, `147`, `151`, `206aa`, `114aaa`, `234h`, `139(9)`, `119(2)(b)`).
     - Lines 242–244: When query contains statutory anchors and candidate chunk contains none, applies `entity_alignment = 0.15`.
     - Lines 253–255: Hard ceiling enforcement:
       ```python
       if statutory_anchors and not matched_anchors:
           confidence = min(confidence, 0.25)
       ```
     - Line 220: Backward compatibility when query is None or empty:
       ```python
       if query is None or not str(query).strip():
           return base_confidence
       ```
   - `backend/modules/explainer.py`:
     - Lines 364–366:
       ```python
       from backend.web_search.confidence import compute_rag_confidence
       score_conf = compute_rag_confidence(result, query=user_question)
       calc_conf = "high" if score_conf >= 0.75 else ("medium" if score_conf >= 0.35 else "low")
       ```
       Since `score_conf <= 0.25 < 0.35`, `calc_conf` evaluates strictly to `"low"`.
   - `backend/pipeline.py`:
     - Lines 605, 665, 964, 1059, 1079: `compute_rag_confidence` is invoked with `query=safe_text`.
     - Lines 667 & 1060: Strict grounding gate blocks synthesis when `rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD` (0.35), triggering web search fallback or issuing honest refusal.

---

## 2. Logic Chain

1. From **Observation 1.1** and **Observation 1.2**, the core requirement R2 specifies that candidate chunks lacking statutory semantic alignment with the query must never output a HIGH confidence rating and must evaluate to confidence $< 0.35$.
2. From **Observation 3.1**, `compute_rag_confidence` enforces a two-tier defense:
   - First, `entity_alignment = 0.15` scales down the multi-factor product $\text{BaseScore} \times \text{EntityAlignment} \times \text{TermOverlap}$.
   - Second, a hard ceiling `confidence = min(confidence, 0.25)` guarantees that even if raw RRF score or lexical term overlap saturate to 1.0, the returned confidence cannot exceed $0.25$.
3. From **Observation 1.2** (Extreme RRF Score Saturation), testing extreme raw scores up to $10.0$ confirmed that no arithmetic overflow or score inflation can breach the $0.25$ cap under statutory mismatch.
4. From **Observation 3.2**, `backend/modules/explainer.py` maps any `score_conf < 0.35` to `"low"`. Because off-topic candidate chunks evaluate to $\le 0.25$, they unconditionally receive `confidence="low"`.
5. From **Observation 1.2** (Positive Controls), genuine statutory matches on Sections 148A/149 or Circular 03/2023 / Section 206AA score $1.000$ and receive `confidence="high"`, proving that gating does not cause false negatives for on-topic retrieval.
6. From **Observation 1.1** (Web Search Suite), all 30 tests in `test_web_search.py` pass without regressions, confirming backward compatibility when `query` is omitted.
7. Therefore, Milestone M2 fully satisfies Requirement R2 and Case 1 / Case 2 confidence gating criteria.

---

## 3. Caveats

1. **Milestone M3 Dependencies**:
   Full end-to-end tests for Case 1 and Case 2 (`test_tier4_case1_verbatim_reassessment_section_148a_end_to_end` and `test_tier4_case2_verbatim_inoperative_pan_tds_refund_end_to_end`) test response shape (`steps == []`) and multi-part query decomposition, which belong to Milestone M3 (`worker_cases_m3`). Those aspects were intentionally not modified in M2.
2. **Corpus Dependency**:
   On-topic high confidence scoring relies on official statutory records ingested in Milestone M1 (`troubleshooting_tax.jsonl` and `troubleshooting_pan.jsonl`). As verified in M1, those provisions are present.

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone M2 (Pre-Synthesis Relevance & Confidence Gating) is thoroughly verified and robust against adversarial bypass:
1. Reassessment and inoperative PAN queries paired with off-topic candidate chunks (119(2)(b), 139(9), PAN FAQs, bank validation, EPFO, Protean, Passport, DL) are strictly gated below 0.35 (capped at $\le 0.25$).
2. Explainer maps all off-topic hits to `confidence="low"`; no off-topic hit can receive `"high"` or `"medium"`.
3. Artificial RRF score saturation attacks up to score=10.0 cannot breach the 0.25 cap.
4. Positive controls verify that legitimate statutory hits receive `confidence="high"` ($\ge 0.75$).
5. All 22 tests in `tests/test_empirical_challenger_m2_confidence_gating.py`, all regression tests in `test_case1_case2_gating_regression.py` for M2, and all 30 tests in `tests/test_web_search.py` pass with zero failures.

---

## 5. Verification Method

To independently reproduce the empirical verification:
```powershell
# 1. Run empirical challenger stress test suite (22 tests):
py -m pytest tests/test_empirical_challenger_m2_confidence_gating.py -v
# Output: 22 passed, 1 warning in ~2.3s

# 2. Run M2 regression gating tests:
py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating or test_tier3_decomposition_with_confidence_gating" -v
# Output: 2 passed in ~44s

# 3. Run full web search regression suite:
py -m pytest tests/test_web_search.py -v
# Output: 30 passed in ~64s
```

Files to inspect:
- `backend/web_search/confidence.py`: lines 231–257 (statutory anchor alignment, 0.15 penalty, 0.25 ceiling).
- `backend/modules/explainer.py`: lines 364–366 (threshold mapping: $\ge 0.75 \to \text{"high"}$, $\ge 0.35 \to \text{"medium"}$, $< 0.35 \to \text{"low"}$).
- `tests/test_empirical_challenger_m2_confidence_gating.py`: comprehensive 22-test adversarial harness.

Invalidation Conditions:
- Any test in `test_empirical_challenger_m2_confidence_gating.py` fails.
- An off-topic candidate chunk returns `compute_rag_confidence(res, query=...) >= 0.35`.
- An off-topic chunk receives `confidence="high"` in `explain_rag_result`.
