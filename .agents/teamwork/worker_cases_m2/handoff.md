# Handoff Report: Milestone M2 — Pre-Synthesis Relevance & Confidence Gating

**Agent ID**: `worker_cases_m2`  
**Role**: Implementation Worker (`teamwork_worker`)  
**Working Directory**: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_cases_m2`  
**Date**: 2026-11-09T13:26:00Z  
**Recipient**: `39a4200a-88ea-4d70-9ed4-ca0bc59538f8`

---

## 1. Observation

1. **Baseline Failure**:
   Running `py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v` produced verbatim:
   ```text
   TypeError: compute_rag_confidence() got an unexpected keyword argument 'query'
   FAILED tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic
   ```
   Inspection of `backend/web_search/confidence.py` (lines 23–53) showed:
   ```python
   def compute_rag_confidence(rag_result) -> float:
       ...
       normalized = min(top_score / _RRF_HIGH_CONFIDENCE_FLOOR, 1.0)
       return normalized
   ```
   The function did not accept a `query` parameter and computed confidence purely from the raw RRF top score without any entity alignment or term overlap checks.

2. **Off-Topic False High Confidence in Explainer**:
   In `backend/modules/explainer.py` (lines 364–366):
   ```python
   top_score = result.hits[0].score
   calc_conf = "high" if top_score >= 0.05 else ("medium" if top_score >= 0.02 else "low")
   ```
   If an off-topic document (such as Section 119(2)(b) condonation of delay or Section 139(9) defective return) was retrieved for a Section 148A reassessment query with an RRF score $\ge 0.05$, `explain_rag_result` unconditionally marked `confidence="high"`.

3. **Missing Query Propagation in Pipeline**:
   In `backend/pipeline.py` (lines 605, 962, and 1076):
   - Line 605: `rag_confidence = compute_rag_confidence(rag_result)`
   - Line 962: `rag_confidence = compute_rag_confidence(rag_result)`
   - Line 1076: `score_conf = compute_rag_confidence(rag_result)`
   None of these invocations passed the user query (`safe_text`), leaving the web search gating and metadata confidence badges unconditioned on semantic relevance.

---

## 2. Logic Chain

1. From **Observation 1.1**, the test suite and architectural contract require `compute_rag_confidence` to accept `query: str | None = None` and evaluate statutory entity alignment and lexical term overlap.
2. In `backend/web_search/confidence.py`, a multi-factor confidence formulation was implemented:
   $$\text{Confidence} = \text{BaseScore} \times \text{EntityAlignment} \times \text{TermOverlap}$$
   - **BaseScore**: $\min(\text{top\_score} / 0.040, 1.0)$ preserves backward compatibility when `query` is omitted or `None`.
   - **EntityAlignment**: Statutory anchor extraction (`extract_statutory_anchors`) identifies provisions (`148a`, `149`, `147`, `151`, `206aa`, `114aaa`, `234h`, `139(9)`, `119(2)(b)`). If statutory anchors are present in the query:
     - If the candidate chunk lacks support for the anchors, a severe penalty ($\text{EntityAlignment} = 0.15$) is applied, and confidence is capped strictly below 0.35 ($\min(\text{confidence}, 0.25)$).
     - If statutory anchors are partially supported (e.g., compound query with supported Section 148A and unsupported Section 999XYZ), $\text{EntityAlignment} = |E_{\text{matched}}| / |E_{\text{query}}| = 0.50$, preventing false HIGH confidence badges.
   - **TermOverlap**: Lexical content word containment (`compute_term_overlap`) computes the fraction of non-stopword content words present in the candidate chunk against a $30\%$ threshold, preventing single-word accidental token collisions from generating high confidence.
3. From **Observation 1.2**, in `backend/modules/explainer.py:364`, `calc_conf` was updated to call `compute_rag_confidence(result, query=user_question)` with standard thresholds:
   $$\text{confidence} = \begin{cases} \text{"high"} & \text{if } \text{score\_conf} \ge 0.75 \\ \text{"medium"} & \text{if } 0.35 \le \text{score\_conf} < 0.75 \\ \text{"low"} & \text{if } \text{score\_conf} < 0.35 \end{cases}$$
   Consequently, off-topic hits failing statutory alignment evaluate to $\text{score\_conf} < 0.35$ and receive `confidence="low"`, never `"high"`.
4. From **Observation 1.3**, in `backend/pipeline.py`:
   - Search gate (line 605) and streaming gate (line 964) pass `query=safe_text` to `compute_rag_confidence(rag_result, query=safe_text)`.
   - Strict grounding gate (lines 665 and 1058) checks `rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD`: if off-topic chunks lack support, pipeline triggers live web search, or issues an honest refusal (`not_found_answer`) with `confidence="low"`.
   - Dynamic confidence badge (line 1076) passes `query=safe_text`.

---

## 3. Caveats

1. **Milestone M3 Scope**:
   Test failures in `test_case1_case2_gating_regression.py` related to `classify_query_modality`, checklist elimination (`steps == []`), and sub-question decomposition belong to Milestone M3 (`worker_cases_m3`). Those were intentionally not touched to adhere strictly to file ownership and milestone boundaries.
2. **Corpus Dependency**:
   Gating relies on statutory chunks ingested in Milestone M1 (`troubleshooting_tax.jsonl` and `troubleshooting_pan.jsonl`). As verified, M1 corpus provisions (Sections 147–151, 206AA, 114AAA, 234H) are present, allowing on-topic queries to match correctly with HIGH confidence.

---

## 4. Conclusion

Milestone M2 (Pre-Synthesis Relevance & Confidence Gating) is complete and verified:
1. `backend/web_search/confidence.py` provides multi-factor gating: statutory entity alignment, lexical term overlap, and backward-compatible base score normalization.
2. Off-topic hits lacking statutory support are strictly penalized below 0.35 (capped at $\le 0.25$), preventing false HIGH confidence badges.
3. `backend/pipeline.py` and `backend/modules/explainer.py` pass `query` to `compute_rag_confidence`.
4. `test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic` turned from FAILED to PASSED.
5. `test_tier3_decomposition_with_confidence_gating` PASSED.
6. `tests/test_web_search.py` passed 100% (30/30) with zero regressions.

---

## 5. Verification Method

To independently verify the implementation:
```bash
# 1. Run M2 targeted relevance and confidence gating unit test:
py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier1_relevance_confidence_gating" -v
# Output: PASSED [100%] in ~2.1s

# 2. Run compound query decomposition gating test:
py -m pytest tests/test_case1_case2_gating_regression.py -k "test_tier3_decomposition_with_confidence_gating" -v
# Output: PASSED [100%]

# 3. Run full web search regression suite:
py -m pytest tests/test_web_search.py -v
# Output: 30 passed, 1 warning in ~32s

# 4. Run domain router regression suite:
py -m pytest tests/test_domain_router.py -v
# Output: 59 passed in ~24s
```

Files to inspect:
- `backend/web_search/confidence.py`: functions `compute_rag_confidence`, `extract_statutory_anchors`, `compute_term_overlap`, `_is_anchor_in_chunk`.
- `backend/pipeline.py`: lines 605, 665, 963, 1058, 1076.
- `backend/modules/explainer.py`: lines 364–366.

Invalidation Conditions:
- If `compute_rag_confidence(mock_result, query=CASE1_QUERY)` with an off-topic hit returns $\ge 0.35$, M2 gating is broken.
- If `test_web_search.py` fails any test, backward compatibility is compromised.
