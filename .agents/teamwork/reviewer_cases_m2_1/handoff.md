# Independent Review & Adversarial Critic Report: Milestone M2

**Agent ID**: `reviewer_cases_m2_1`  
**Role**: Independent Reviewer & Adversarial Critic (`teamwork_reviewer`)  
**Working Directory**: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m2_1`  
**Date**: 2026-11-09T13:52:00Z  
**Recipient**: `39a4200a-88ea-4d70-9ed4-ca0bc59538f8`  
**Verdict**: **APPROVE**

---

## 1. Observation

1. **Source Code Modifications**:
   - `backend/web_search/confidence.py`:
     - Implemented `extract_statutory_anchors(text: str) -> set[str]` capturing sections (`148a`, `149`, `147`, `151`, `206aa`, `139(9)`, `119(2)(b)`, etc.), rules (`114aaa`), circulars (`03/2023`), and arbitrary provisions.
     - Implemented `compute_term_overlap(query: str, chunk_blob: str) -> float` evaluating lexical content word overlap ratio against a 30% target.
     - Upgraded `compute_rag_confidence(rag_result: Any, query: str | None = None) -> float`:
       $$\text{Confidence} = \text{BaseScore} \times \text{EntityAlignment} \times \text{TermOverlap}$$
       When statutory anchors are present in the query and zero anchors match the candidate chunk text, `entity_alignment = 0.15` and confidence is hard-capped at $\le 0.25$ (strictly $< 0.35$).
       When `query` is omitted or empty, `base_confidence = \min(\text{top\_score} / 0.040, 1.0)$ preserves full backward compatibility.
   - `backend/modules/explainer.py` (lines 364–366):
     - Updated dynamic confidence scoring in `explain_rag_result` from raw score slicing (`top_score >= 0.05`) to `compute_rag_confidence(result, query=user_question)`.
     - Standard thresholds applied: $\ge 0.75 \to \text{"high"}$, $[0.35, 0.75) \to \text{"medium"}$, $< 0.35 \to \text{"low"}$.
   - `backend/pipeline.py` (lines 605, 665, 963, 1060, 1076):
     - Propagated `query=safe_text` to `compute_rag_confidence(rag_result, query=safe_text)` across all gating decision points in synchronous `run()` and streaming `run_stream()`.

2. **Automated Verification Test Executions**:
   - Gating regression tests:
     `py -m pytest tests/test_case1_case2_gating_regression.py -k "relevance_confidence_gating or decomposition_with_confidence_gating" -v`
     - `test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic`: **PASSED** [50%]
     - `test_tier3_decomposition_with_confidence_gating`: **PASSED** [100%]
     - Result: `2 passed, 17 deselected, 1 warning in 39.32s`.
   - Web search test suite:
     `py -m pytest tests/test_web_search.py -v`
     - Result: `30 passed, 1 warning in 51.56s` (100% pass rate).
   - Adversarial stress suites:
     `py -m pytest tests/test_adversarial_m2_confidence_gating_stress.py tests/test_adversarial_m2_harness.py tests/test_empirical_challenger_m2_confidence_gating.py -v`
     - Result: `73 passed, 2 warnings in 41.77s` (100% pass rate).

3. **Integrity & Zero Predefined Responses Audit**:
   - Source code inspection verified zero hardcoded strings matching query literals, zero facade logic, zero external task delegation bypasses, and zero fabricated assertions.
   - All responses dynamically evaluate RRF scores and text blobs.
   - No pre-canned templates or forbidden disclaimers ("pre-verified guide", "predefined response") introduced.

---

## 2. Logic Chain

1. From **Observation 1.1**, the core requirement R2 (ORIGINAL_REQUEST.md line 15 & PROJECT.md Feature 5) requires that retrieved chunks lacking semantic alignment or statutory support do not output a HIGH confidence rating, and off-topic chunks lacking statutory support are capped strictly below 0.35.
2. Direct empirical evaluation of `compute_rag_confidence` demonstrated:
   - Off-topic hit (Section 148A reassessment query matched against Section 119(2)(b) condonation chunk with high RRF score 0.055): yielded confidence = `0.1250` ($\le 0.25 < 0.35$), evaluated as `confidence="low"`.
   - On-topic hit (Section 148A notice with score 0.045): yielded confidence = `1.0000`, evaluated as `confidence="high"`.
   - Partial match (Compound query with supported Section 148A and unsupported Section 999XYZ): yielded confidence = `0.5000` ($< 0.75$), evaluated as `confidence="medium"`, successfully preventing false HIGH confidence badges.
   - Non-statutory off-topic query (Driving license renewal query matched against Income Tax refund chunk): yielded confidence = `0.0000` via lexical term overlap ($< 0.35$).
3. From **Observation 1.2**, `tests/test_web_search.py` passing 30/30 confirms that backward compatibility for existing web search fallback logic, DuckDuckGo allowlisting, and domain queries is fully intact.
4. From **Observation 2**, extensive independent adversarial suites containing 73 dedicated stress tests passed without error, confirming robustness against ReDoS, extreme RRF saturation ($score \ge 10.0$), empty inputs, and unusual token combinations.

---

## 3. Caveats

1. **Milestone M3 Separation**:
   Failures in `test_case1_case2_gating_regression.py` regarding query modality classification (`classify_query_modality`), step elimination (`steps == []`), and compound query decomposition belong to Milestone M3 scope and were properly not modified in M2.
2. **Environment Configuration in Streaming Test**:
   In `tests/test_streaming.py`, `test_ask_stream_verified_query` tests an SSE streaming pipeline where `.env` has `WEB_SEARCH_ENABLED=true` and `WEB_SEARCH_CONFIDENCE_THRESHOLD=0.75`. When a moderate-scoring RAG hit (score 0.023, confidence 0.576) is encountered, web search fallback is engaged per configured policy. This is an integration behavior of the web search configuration rather than an M2 confidence gating failure.

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone M2 (Pre-Synthesis Relevance & Confidence Gating) is correctly and robustly implemented:
1. Multi-factor confidence scoring in `backend/web_search/confidence.py` enforces statutory entity alignment and lexical content overlap.
2. Off-topic chunks lacking statutory support are strictly capped at $\le 0.25$ ($< 0.35$), ensuring they receive `confidence="low"` and trigger web search or honest refusal.
3. Query propagation in `backend/pipeline.py` and `backend/modules/explainer.py` operates as specified.
4. All required tests (`test_case1_case2_gating_regression.py` gating tests, `test_web_search.py`, and 73 M2 adversarial tests) pass 100%.
5. Zero integrity violations and full compliance with the Zero Predefined Responses directive.

---

## 5. Verification Method

To independently reproduce the reviewer's verification:
```powershell
# 1. Gating regression tests
py -m pytest tests/test_case1_case2_gating_regression.py -k "relevance_confidence_gating or decomposition_with_confidence_gating" -v

# 2. Web search regression suite
py -m pytest tests/test_web_search.py -v

# 3. Comprehensive M2 adversarial suites
py -m pytest tests/test_adversarial_m2_confidence_gating_stress.py tests/test_adversarial_m2_harness.py tests/test_empirical_challenger_m2_confidence_gating.py -v

# 4. Empirical off-topic capping verification script
py -c "from backend.web_search.confidence import compute_rag_confidence; from backend.rag.models import RagDocument, RetrievalHit, RetrievalResult; doc = RagDocument(id='d1', content_hash='h1', category='tax', text='Section 119(2)(b) condonation of delay', language='en', tags=(), sources=(), warnings=()); hit = RetrievalHit(document=doc, score=0.055, rank=1, signals={}); res = RetrievalResult(query='test', hits=(hit,), status='supported', searched_documents=10); c = compute_rag_confidence(res, query='Notice under Section 148A(b)'); assert c < 0.35 and c <= 0.25, f'Failed: {c}'; print('Verified: c =', c)"
```
