# Milestone 3 Iteration 2 Empirical Challenge Report

**Agent**: `challenger_m3_iter2_2`  
**Parent Agent**: `dbf15a36-ef58-4a18-a9f2-171e93acf6cc`  
**Timestamp**: 2026-11-04T20:30:00Z  
**Type**: Hard Handoff  
**Verdict**: **`REQUEST_CHANGES`**

---

## 1. Observation

### 1.1 Critical Vulnerability: Broken Word Boundary in `is_139_query` Regex
In `backend/rag/retriever.py`, line 307:
```python
is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))
```
1. In Python's `re` module, `\b` asserts a word boundary, which occurs only between an alphanumeric character (`\w` = `[a-zA-Z0-9_]`) and a non-alphanumeric character (`\W`), or vice versa.
2. Because `139(9)` ends with the closing parenthesis `)`, which is already a `\W` character, the trailing `\b` requires the subsequent character to be `\w`. If followed by whitespace, punctuation, or end of string (all `\W`), `\b` evaluates to `False`.
   - Direct verification:
     ```python
     bool(re.search(r"\b(?:139\(9\))\b", "139(9) ")) == False
     bool(re.search(r"\b(?:139\(9\))\b", "139(9)abc")) == True  # Inverted boundary!
     ```
3. Whenever a query contains `139(9)` without the verbatim phrases `"defective return"`, `"defective notice"`, or `"defect memo"`, `is_139_query` evaluates to `False`.
   - Verification across queries:
     ```python
     q1 = "Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback"
     # bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", q1.lower())) -> False

     q2 = "Should I file 139(9) response or give AIS feedback for duplicate mutual fund transaction?"
     # bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", q2.lower())) -> False

     q3 = "139(9) vs AIS feedback"
     # bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", q3.lower())) -> False

     q4 = "How do I respond to 139(9) on e-proceedings portal?"
     # bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", q4.lower())) -> False
     ```

### 1.2 Catastrophic Suppression on Dual-Intent Comparison Queries
In `backend/rag/retriever.py`, lines 313-320:
```python
if is_139_query and not is_ais_query:
    if ("ais feedback" in lowered_doc or "sft feedback" in lowered_doc) and "cpc 2.0 defect memo" not in lowered_doc:
        score -= 0.40
        signals["sub_procedure_mismatch_penalty"] = -0.40
elif is_ais_query and not is_139_query:
    if ("139(9)" in lowered_doc or "defective return" in lowered_doc) and "ais feedback" not in lowered_doc and "sft feedback" not in lowered_doc:
        score -= 0.40
        signals["sub_procedure_mismatch_penalty"] = -0.40
```
Because `is_139_query` is falsely `False` while `is_ais_query` is `True` on comparison queries:
1. `elif is_ais_query and not is_139_query:` evaluates to `True`.
2. `itr_defective_return_manual_01` is classified as an unwanted single-intent AIS mismatch.
3. `itr_defective_return_manual_01` receives `sub_procedure_mismatch_penalty = -0.40`.
4. Verbatim output on executing `'139(9) vs AIS feedback'`:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import RagRetriever; r = RagRetriever(); res = r.search('139(9) vs AIS feedback', category='tax', top_k=50); d = next((h for h in res.hits if h.document.id == 'itr_defective_return_manual_01'), None); print('139 hit score:', d.score, 'signals:', d.signals)"
   ```
   Output:
   ```
   139 hit score: -0.3338709677419355 signals: {'bm25_score': 20.657819778084047, 'lexical_rrf': 0.016129032258064516, 'tag_overlap': 0.0, 'exact_statutory_boost': 0.12, 'symptom_boost': 0.08, 'contamination_penalty': -0.15, 'sub_procedure_mismatch_penalty': -0.4}
   ```
   `itr_defective_return_manual_01` drops from Rank 2 (healthy positive score ~+0.12) to score **`-0.3338`**, dropping out of top 10/20 results entirely.

### 1.3 Asymmetric Failure on Single-Intent 139(9) Queries
On pure 139(9) queries that don't say `"defective return"`, e.g., `"How do I respond to 139(9) on e-proceedings portal?"`:
- `is_139_query` is `False`.
- `itr_ais_feedback_manual_01` receives **no penalty** and surfaces at Rank 2 with score `0.2161`, virtually tied with Rank 1 `itr_defective_return_manual_01` (`0.2163`).

### 1.4 Passing Areas Verified Empirically
1. **Candidate Deduplication in Hybrid Search**:
   Tested 21+ stress queries spanning all categories in hybrid mode (with Qdrant and FastEmbed active):
   - Result: 0 duplicate hits found across all queries. RRF properly fuses vector and BM25 signals.
2. **`DocumentId` Data Model Invariant**:
   - `DocumentId("x") == "x"` and `hash(DocumentId("x")) == hash("x")`.
   - Set and dictionary key interchangeability verified.
3. **Boundary Queries A through E in Hybrid Search**:
   - Boundary Query A: AIS Rank 1 (score 0.22, 139 not in top 3). PASS.
   - Boundary Query B: 139 Rank 1 (score 0.35, AIS receives -0.40). PASS (because "defective return" matched).
   - Boundary Query C: AIS Rank 1. PASS.
   - Boundary Query D: 139 Rank 1. PASS.
   - Boundary Query E: AIS Rank 1. PASS.
4. **Qdrant File Lock Contention in Automated Suites**:
   Running `pytest tests/test_adversarial_m3_1_harness.py tests/test_adversarial_m3_harness.py` together triggers `RuntimeError: Storage folder ... is already accessed by another instance of Qdrant client` because `backend/rag/runtime.py`'s `_get_retriever` caches the local vector store client holding `portalocker` exclusive locks. When run separately, both suites pass (16 passed in harness 1, 8 passed in harness 2).

---

## 2. Logic Chain

1. From Observation 1.1, the regex pattern in line 307 places `\b` immediately after `139\(9\)`.
2. In regular expressions, `\b` matches a zero-width transition between `\w` and `\W`. Because `)` is already `\W`, followed by space or punctuation (also `\W`), no word boundary exists. Therefore, `re.search` fails unconditionally for `139(9)` when followed by normal query delimiters.
3. Because the regex fails, `is_139_query` evaluates to `False` for any query that mentions `139(9)` unless the user also redundantly includes `"defective return"`, `"defective notice"`, or `"defect memo"`.
4. From Observation 1.2, in dual-intent comparison queries such as `"139(9) vs AIS feedback"`, `is_ais_query` evaluates to `True`, while `is_139_query` falsely evaluates to `False`.
5. This misroutes execution into the `elif is_ais_query and not is_139_query:` branch, which applies `-0.40` `sub_procedure_mismatch_penalty` to `itr_defective_return_manual_01`.
6. This penalty causes `itr_defective_return_manual_01`'s score to drop below zero (-0.3338), eliminating it from the top retrieval hits and violating the core Milestone 3 requirement: dual-intent comparison queries must present both sub-procedures simultaneously without false mismatch penalties.

---

## 3. Caveats

- **No Corpus / Data Modification**: Corpus JSONL and Qdrant points are healthy and unaffected.
- **Worker Remediation Scope**: The candidate deduplication and `DocumentId` hash invariant changes implemented by worker_m3_iter2 are sound and verified. Only the regex boundary and detection logic in `is_139_query` require remediation.

---

## 4. Conclusion

Milestone 3 Iteration 2 **FAILS** adversarial review.
Verdict: **`REQUEST_CHANGES`**.

The worker must remediate `backend/rag/retriever.py:307`:
1. Fix the word boundary assertion for `139(9)` using lookaheads/lookbehinds `(?<!\w)139\(9\)(?!\w)` instead of `\b139\(9\)\b`, or structure the regex safely:
   ```python
   is_139_query = bool(
       re.search(r"(?:\b139\(9\)(?!\w)|\b(?:defective\s+return|defective\s+notice|defect\s+memo)\b)", lowered_q)
       or ("139" in lowered_q and any(w in lowered_q for w in ("9", "defect", "defective", "proceedings", "memo")))
   )
   ```
2. Ensure queries such as `"139(9) vs AIS feedback"`, `"Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback"`, and `"Should I file 139(9) response or give AIS feedback for duplicate mutual fund transaction?"` resolve with `is_139_query == True` and `is_ais_query == True`, producing ranks 1 and 2 for both sub-procedures without mismatch penalties.

---

## 5. Verification Method

To independently reproduce this failure:

1. **Reproduce Regex Boundary Failure on 139(9)**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "import re; pat = r'\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b'; print('Matches 139(9):', bool(re.search(pat, '139(9) vs AIS feedback'.lower())))"
   ```
   *Expected*: `False` (Demonstrating regex failure).

2. **Reproduce Dual-Intent Penalty on 139(9) vs AIS Comparison**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import RagRetriever; r = RagRetriever(); res = r.search('139(9) vs AIS feedback', category='tax', top_k=20); d = next((h for h in res.hits if h.document.id == 'itr_defective_return_manual_01'), None); print('139 hit score:', d.score if d else 'Not in hits', 'penalty:', d.signals.get('sub_procedure_mismatch_penalty') if d else None); assert d is not None and 'sub_procedure_mismatch_penalty' not in d.signals, 'FAIL: 139 penalized or missing'"
   ```
   *Result*: `AssertionError: FAIL: 139 penalized or missing` with `penalty: -0.4`.

3. **Run Challenger Stress Harness**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_empirical_challenger_m3_iter2.py -v
   ```
   *Result*: 2 failed (`test_dual_intent_both_subprocedures_surfaced_without_penalty` on comparison queries), 36 passed.

4. **Invalidation Condition**:
   - `is_139_query` returns `True` for `'139(9) vs AIS feedback'`.
   - Both `itr_ais_feedback_manual_01` and `itr_defective_return_manual_01` appear in top hits with positive scores (> 0.05) and zero `sub_procedure_mismatch_penalty`.
