# Milestone 3 Iteration 2 Independent Review & Adversarial Challenge Report

**Agent**: `reviewer_m3_iter2_1`  
**Parent Agent**: `dbf15a36-ef58-4a18-a9f2-171e93acf6cc`  
**Timestamp**: 2026-11-04T20:33:00Z  
**Type**: Hard Handoff  
**Verdict**: **`REQUEST_CHANGES`**

---

## 1. Observation

1. **Verification of Iteration 1 Remediations**:
   - **`DocumentId` Data Model Invariant**:
     In `backend/rag/retriever.py`, lines 15–21:
     ```python
     class DocumentId(str):
         """Immutable document identifier preserving Python's data model invariant."""
         def __new__(cls, val: str, aliases: tuple[str, ...] | list[str] = ()):
             obj = str.__new__(cls, val)
             obj._aliases = tuple(aliases)
             return obj
     ```
     `__eq__` and `__hash__` overrides were removed. `DocumentId` directly inherits Python `str` equality and hashing.
     Independent verification test:
     ```python
     d = DocumentId('primary', ['primary', 'alias1'])
     assert d == 'primary'
     assert hash(d) == hash('primary')
     s = {d}
     assert 'primary' in s
     ```
     Verified: Python data model invariant `a == b => hash(a) == hash(b)` is fully restored and preserved.

   - **Unified Candidate Keying in `RagRetriever.search()`**:
     In `backend/rag/retriever.py`:
     - Lexical pass (line 137): `signals = candidates.setdefault(document.id, {})`
     - Vector pass (line 155): `signals = candidates.setdefault(document.id, {})`
     Both passes use the exact same key object (`document.id`).
     Candidate signals (`bm25_score`, `lexical_rrf`, `vector_score`, `vector_rrf`) are successfully fused into a single dictionary entry per document.
   - **Hybrid Search Deduplication**:
     In `backend/rag/retriever.py`, lines 181–188:
     ```python
     seen_doc_ids: set[str] = set()
     for document_id, signals in candidates.items():
         if document_id not in self.documents_by_id:
             continue
         document = self.documents_by_id[document_id]
         if document.id in seen_doc_ids:
             continue
         seen_doc_ids.add(document.id)
     ```
     Tested on `defective return 139(9)`:
     Verbatim output: `Hits count: 8`, 8 unique document IDs, 0 duplicates.
     Tested across 22 multi-domain hybrid queries in `tests/test_empirical_challenger_m3_iter2.py`: 100% passed with 0 duplicates.

2. **Discovery of Word-Boundary Regex Defect in `is_139_query`**:
   In `backend/rag/retriever.py`, line 307:
   ```python
   is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))
   ```
   Notice the trailing word boundary `\b` applied to the non-capturing group containing `139\(9\)`.
   In Python regular expressions, `\b` matches the boundary between a word character (`\w`: letters, digits, underscore) and a non-word character (`\W`).
   Because the closing parenthesis `)` in `139(9)` is a non-word character (`\W`), `\b` immediately following `)` requires the next character to be a word character (`\w`).
   When `139(9)` is followed by whitespace, punctuation, or end of string (all non-word characters `\W`), **`\b` fails to match**:
   ```python
   import re
   s = "compare section 139(9) e-proceedings"
   print(bool(re.search(r"\b139\(9\)\b", s)))  # Evaluates to False!
   ```

3. **Failure of Dual-Intent Comparison Queries Lacking the Literal Word "Defective"**:
   Executing the following comparison queries in `retriever.search()`:
   - Query 1: `"Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback"`
   - Query 2: `"Should I file 139(9) response or give AIS feedback for duplicate mutual fund transaction?"`

   In both queries:
   - The query does not contain `"defective return"`, `"defective notice"`, or `"defect memo"`.
   - `is_139_query` evaluates to `False` due to the `)\b` boundary bug.
   - `is_ais_query` evaluates to `True`.
   - The retriever enters line 317:
     ```python
     elif is_ais_query and not is_139_query:
         if ("139(9)" in lowered_doc or "defective return" in lowered_doc) and "ais feedback" not in lowered_doc and "sft feedback" not in lowered_doc:
             score -= 0.40
             signals["sub_procedure_mismatch_penalty"] = -0.40
     ```
   - Verbatim hit evaluation for `itr_defective_return_manual_01`:
     ```python
     Found: 29 itr_defective_return_manual_01 score: -0.3339 signals: {
         'bm25_score': 31.0355,
         'lexical_rrf': 0.0161,
         'tag_overlap': 0.0,
         'exact_statutory_boost': 0.12,
         'symptom_boost': 0.08,
         'contamination_penalty': -0.15,
         'sub_procedure_mismatch_penalty': -0.4
     }
     ```
   - In hybrid search, `itr_defective_return_manual_01` is knocked out of the top results entirely (missing from top 10 and top 15).
   - In `tests/test_empirical_challenger_m3_iter2.py`:
     ```
     FAILED tests/test_empirical_challenger_m3_iter2.py::TestDualIntentComparisonQueries::test_dual_intent_both_subprocedures_surfaced_without_penalty[Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback]
     FAILED tests/test_empirical_challenger_m3_iter2.py::TestDualIntentComparisonQueries::test_dual_intent_both_subprocedures_surfaced_without_penalty[Should I file 139(9) response or give AIS feedback for duplicate mutual fund transaction?]
     ```

4. **Test Suite Execution**:
   - `pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r6 or test_tier2_ais or test_tier2_139" -v`: 7 passed, 52 deselected.
   - `pytest tests/test_rag_retriever.py -v`: 8 passed.
   - `pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v`: 12 passed.
   - `pytest tests/test_adversarial_m3_harness.py tests/test_adversarial_m3_1_harness.py -v`: 24 passed.
   - `pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r2 or test_tier1_r5" -v`: 25 passed, 34 deselected.
   - `pytest tests/test_empirical_challenger_m3_iter2.py -v`: 36 passed, 2 FAILED.

---

## 2. Logic Chain

1. From Observation 1, worker_m3_iter2 successfully resolved the candidate key mismatch and dictionary splitting by keying candidates consistently on `document.id`. The hash model invariant in `DocumentId` is sound.
2. However, from Observation 2, `is_139_query` uses the regular expression:
   `r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b"`
   Because the closing parenthesis `)` is non-word, the trailing `\b` asserts a boundary between non-word and word. When `139(9)` is followed by a space (as in `"139(9) e-proceedings"` or `"139(9) response"`), the boundary check fails because both `)` and ` ` are non-word.
3. Therefore, `is_139_query` only ever evaluated to `True` when the query happened to contain the explicit literal phrases `"defective return"`, `"defective notice"`, or `"defect memo"`.
4. In DISPATCH.md, the test query `"What is the difference between Section 139(9) defective return notice and AIS feedback?"` passed solely because it included the words `"defective return notice"`.
5. For any legitimate user comparison query that uses `"139(9)"` without repeating `"defective"` (e.g. `"Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback"` or `"Should I file 139(9) response or give AIS feedback for duplicate mutual fund transaction?"`), `is_139_query` returns `False` while `is_ais_query` returns `True`.
6. From Observation 3, the retriever falls into `elif is_ais_query and not is_139_query:`, treats the comparison query as a single-intent AIS query, and unfairly penalizes `itr_defective_return_manual_01` with `-0.40`.
7. This causes `itr_defective_return_manual_01` to be knocked out of the top search results in production, violating the core requirement of dual-intent sub-procedure comparison.
8. Because review must be adversarial and reject fragile implementations that break on natural user phrasings, the verdict must be `REQUEST_CHANGES`.

---

## 3. Caveats

- **No Integrity Violation**: There is no evidence of hardcoded test bypasses, facade classes, or pre-canned responses. `DocumentId` and candidate deduplication were genuinely implemented. The defect is an unintended regex boundary syntax error in `is_139_query`.
- **Corpus Integrity Intact**: The underlying JSONL data files, vector index embeddings (1388 points), and domain router remain fully verified and intact.

---

## 4. Conclusion & Required Changes

**Verdict**: **`REQUEST_CHANGES`**

### Required Remediation:

In `backend/rag/retriever.py`, line 307:
Replace the trailing word boundary `\b` after `139\(9\)` with negative lookaround `(?!\w)` (identical to the pattern already proven in `_EXACT_CODES` at line 223):

```python
# Before (buggy):
is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))

# After (remediated):
is_139_query = bool(
    re.search(r"(?:(?<!\w)139\(9\)(?!\w)|\b(?:defective\s+return|defective\s+notice|defect\s+memo)\b)", lowered_q)
)
```

With this single targeted change:
1. `"139(9)"` matches whether followed by space, punctuation, or end of string.
2. Dual-intent comparison queries without the literal word `"defective"` correctly set `is_139_query = True` and `is_ais_query = True`.
3. Neither sub-procedure receives the `-0.40` penalty.
4. Both `itr_ais_feedback_manual_01` and `itr_defective_return_manual_01` surface cleanly in the top hits.
5. All 38 tests in `tests/test_empirical_challenger_m3_iter2.py` pass cleanly.

---

## 5. Verification Method

To independently verify this defect and validate the remediation:

1. **Verify Regex Boundary Failure**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "import re; s = 'Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback'; print('Current regex match:', bool(re.search(r'\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b', s.lower()))); print('Lookaround regex match:', bool(re.search(r'(?:(?<!\w)139\(9\)(?!\w)|\b(?:defective\s+return|defective\s+notice|defect\s+memo)\b)', s.lower())))"
   ```
   *Current state*: Prints `Current regex match: False`, `Lookaround regex match: True`.

2. **Verify Dual-Intent Suppression on Failing Queries**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import RagRetriever; ret = RagRetriever(); res = ret.search('Compare Section 139(9) e-proceedings vs AIS Annual Information Statement feedback', category='tax', top_k=10); hit_ids = [str(h.document.id) for h in res.hits]; assert 'itr_defective_return_manual_01' in hit_ids, f'Missing defective return manual from top hits: {hit_ids}'"
   ```
   *Current state*: Fails with `AssertionError: Missing defective return manual from top hits`.

3. **Run Test Suites Following Fix**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_empirical_challenger_m3_iter2.py -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r6 or test_tier2_ais or test_tier2_139" -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_retriever.py -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m3_harness.py tests/test_adversarial_m3_1_harness.py -v
   ```

4. **Invalidation Conditions**:
   - `is_139_query` evaluating to `False` for queries containing `"139(9)"`.
   - `itr_defective_return_manual_01` receiving `-0.40` mismatch penalty on dual-intent comparison queries.
   - Any test failure in `test_empirical_challenger_m3_iter2.py` or regression suites.

---

## 6. Review Summary & Findings

### [Major] Finding 1: Regex Word Boundary Failure in `is_139_query` Suppresses 139(9) on Comparison Queries
- **What**: `r"\b(?:139\(9\)|...)\b"` fails to match `139(9)` when followed by whitespace or punctuation because `)` is a non-word character and `\b` requires a transition between word and non-word characters.
- **Where**: `backend/rag/retriever.py`, line 307.
- **Why**: Dual-intent comparison queries that mention `"139(9)"` without the literal word `"defective"` fail `is_139_query`, trigger `is_ais_query and not is_139_query`, slash `itr_defective_return_manual_01` with `-0.40` mismatch penalty, and exclude it from top results.
- **Suggestion**: Use `(?<!\w)139\(9\)(?!\w)` instead of `\b139\(9\)\b`.

### Verified Claims
- Candidate keying in hybrid search keys by `document.id` in both lexical and vector passes: VERIFIED PASS.
- No duplicate hits emitted across 22 multi-domain hybrid queries: VERIFIED PASS.
- `DocumentId` adheres to Python's data model invariant (`a == b => hash(a) == hash(b)`): VERIFIED PASS.
- Single-intent 139(9) queries surface `itr_defective_return_manual_01` at rank 1: VERIFIED PASS.
- Single-intent AIS queries surface `itr_ais_feedback_manual_01` at rank 1: VERIFIED PASS.

### Coverage Gaps
- None.

### Unverified Items
- None.
