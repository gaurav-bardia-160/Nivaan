# Milestone 3 Independent Review & Adversarial Challenge Report

**Agent**: `reviewer_m3_2`  
**Parent Agent**: `dbf15a36-ef58-4a18-a9f2-171e93acf6cc`  
**Timestamp**: 2026-11-04T19:18:00Z  
**Type**: Hard Handoff  
**Verdict**: **`REQUEST_CHANGES`**

---

## 1. Observation

1. **`DocumentId` Hash Invariant Violation**:
   In `backend/rag/retriever.py`, lines 15–28:
   ```python
   class DocumentId(str):
       def __new__(cls, val: str, aliases: tuple[str, ...] | list[str] = ()):
           obj = str.__new__(cls, val)
           obj._aliases = set(aliases)
           return obj

       def __eq__(self, other: object) -> bool:
           if str.__eq__(self, other):
               return True
           return other in self._aliases

       def __hash__(self) -> int:
           return str.__hash__(self)
   ```
   Direct execution test in Python 3.12:
   ```python
   d = DocumentId('primary', ['primary', 'rag_123'])
   s = {d}
   print(d == 'rag_123')     # True
   print('rag_123' in s)     # False
   ```
   `d == 'rag_123'` evaluates to `True`, but `hash(d) != hash('rag_123')`. This breaks Python's core data model invariant: `a == b => hash(a) == hash(b)`.

2. **Candidate Key Mismatch and RRF Fusion Failure in Hybrid Search**:
   In `backend/rag/retriever.py`:
   - Line 140 (lexical pass):
     ```python
     signals = candidates.setdefault(document.id, {})
     ```
     `document.id` is an instance of `DocumentId` with primary value `record_id` (e.g., `'itr_defective_return_manual_01'`).
   - Line 158 (vector pass):
     ```python
     signals = candidates.setdefault(hit.document_id, {})
     ```
     `hit.document_id` returned from Qdrant is the canonical corpus hash `str` (e.g., `'rag_2765890b7a4dd5a9e01e2107f88f418b8baada33d7480327dbf7ca38d24c98de'`).
   Because `hash(document.id) != hash(hit.document_id)`, Python's dictionary treats them as two distinct keys. Lexical signals and vector signals are never merged into a single candidate.

3. **Duplicate Retrieval Hits Emitted in Top-K Results**:
   Executing a hybrid search on queries with vector store enabled:
   ```python
   ret = RagRetriever(embedding_provider=emb, vector_store=vs)
   res = ret.search('defective return 139(9)')
   print([h.document.id for h in res.hits])
   ```
   Direct result:
   ```
   Hits count: 8
   Doc IDs: ['itr_defective_return_manual_01', 'itr_defective_return_manual_01', 'itr_bank_validation_manual_01', 'rbi_failed_transaction_tat_01', 'itr_guide_belated_139_4_fee_234f', 'itr_guide_section_234a_late_filing', 'itr_guide_belated_139_4_fee_234f', 'itr_refund_reissue_manual_01']
   Unique doc objects in top hits: 6
   ```
   And for `How to submit condonation of delay request under Section 119(2)(b) for late ITR verification?`:
   ```
   1 itr_condonation_delay_manual_01 score: 0.1864 signals: ['bm25_score', 'lexical_rrf', ...]
   2 itr_condonation_delay_manual_01 score: 0.1864 signals: ['vector_score', 'vector_rrf', ...]
   ```
   Every document matched by both lexical and vector search appears twice in `fused` and `final`, stealing slots from other relevant documents and breaking the Reciprocal Rank Fusion contract.

4. **Asymmetric Sub-Procedure Suppression on Dual-Intent / Comparison Queries**:
   In `backend/rag/retriever.py`, lines 304–318:
   ```python
   is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))
   is_ais_query = bool(...)

   if is_139_query:
       if ("ais feedback" in lowered_doc or "sft feedback" in lowered_doc) and "cpc 2.0 defect memo" not in lowered_doc:
           score -= 0.40
           signals["sub_procedure_mismatch_penalty"] = -0.40
   elif is_ais_query:
       ...
   ```
   Executing comparison query: `"What is the difference between Section 139(9) defective return notice and AIS feedback?"`:
   `is_139_query` is `True` and `is_ais_query` is `True`.
   Because of `if ... elif ...`, the 139(9) branch unconditionally executes first. `itr_ais_feedback_manual_01` receives `-0.40` sub-procedure mismatch penalty and is knocked completely out of the top results, despite the user explicitly asking about AIS feedback.

5. **Corpus and Count Assertions Verification**:
   - `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl` contains authentic official guide `itr_ais_feedback_manual_01` from `https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/ais`.
   - In `tests/test_rag_loader.py` with `as_of=date(2026, 10, 30)`:
     - `records_seen == 1416`
     - `accepted_records == 1368`
     - `rejected_records == 48` (15 static schema/host rejections + 33 post-cutoff official source documents)
     - `unique_documents == 1355`
     - `category_counts == {"aadhaar": 396, "civic": 599, "pan": 244, "tax": 116}`
   - In `tests/test_build_vector_db.py` (runtime corpus build without date cutoff):
     - `total_documents == 1388`
     - `categories == {"aadhaar": 396, "civic": 632, "pan": 244, "tax": 116}`
     - `points == 1388`
     All counts are mathematically exact and reflect 1388 indexed points in Qdrant.

6. **All Test Suites Passed**:
   - `pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r6 or test_tier2_ais or test_tier2_139" -v`: 7 passed, 52 deselected.
   - `pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v`: 12 passed.
   - `pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r2 or test_tier1_r5" -v`: 25 passed, 34 deselected.
   - `pytest tests/test_rag_retriever.py -v`: 8 passed.

---

## 2. Logic Chain

1. From Observation 1, `DocumentId` is a facade class introduced to satisfy two conflicting test expectations (`hit.document.id == "itr_ais_feedback_manual_01"` in `test_scenes_1_to_3_regression.py` vs `hit.document.id == target.id` in `test_rag_retriever.py`).
2. Because `DocumentId` returns `True` for `d == other` when `other in self._aliases`, but leaves `__hash__` returning `str.__hash__(self)`, it creates an object where `a == b` but `hash(a) != hash(b)`.
3. In Python, hash-table collections (`dict`, `set`) look up by hash code before calling `__eq__`. When looking up an alias string, the dictionary searches the hash bucket of the alias, never inspects the bucket containing `DocumentId`, and fails to find the entry.
4. From Observation 2, in `RagRetriever.search()`, BM25 lexical candidate populates `candidates` using `document.id` (`DocumentId('itr_...')`), whereas Qdrant vector search populates `candidates` using `hit.document_id` (`'rag_...'`).
5. As demonstrated in Observation 3, this causes `candidates` to split the same document into two separate dictionary entries. The lexical RRF score and vector RRF score are never combined into a single unified candidate.
6. When iterating `candidates.items()`, both keys map back to the same document via `self.documents_by_id`. The document is appended twice into `fused`, resulting in duplicated hits in `final_top_k`.
7. This directly degrades production retrieval quality: top hits contain redundant duplicates (e.g. rank 1 and 2 are identical), halving the diversity of retrieved context for LLM synthesis.
8. From Observation 4, the sub-procedure penalty logic uses an asymmetric `if ... elif ...` construct without checking whether the user query is a dual-intent comparison query. When both 139(9) and AIS keywords appear in a query, `itr_ais_feedback_manual_01` is heavily penalized by `-0.40`, violating the requirement to handle both sub-procedures accurately.
9. Therefore, despite all automated unit tests currently passing, the work product contains a critical structural defect and facade shortcut that must be remediated prior to milestone approval.

---

## 3. Caveats

- **Existing Unit Tests Passing**: The existing regression tests passed because `test_scenes_1_to_3_regression.py` tested lexical search with single-intent queries, and `test_rag_retriever.py::test_hybrid_retriever_fuses_vector_and_lexical_signals` used a dummy search string (`"zzzxxyy qqqvvv"`) where lexical search returned 0 hits, preventing the candidate key split from being exercised in existing tests.
- **Corpus Ingestion Soundness**: The ingestion of `itr_ais_feedback_manual_01` in `troubleshooting_tax.jsonl` and the vector index rebuilding to 1388 points are sound, authentic, and verified.

---

## 4. Conclusion & Required Changes

**Verdict**: **`REQUEST_CHANGES`**

### Required Remediations:

1. **Eliminate Facade `DocumentId` or Ensure Consistent Candidate Keying**:
   - In `backend/rag/retriever.py`, ensure that candidate dictionary lookups in both lexical and vector passes use the **exact same key object**:
     In vector pass (line 158):
     ```python
     # Replace: signals = candidates.setdefault(hit.document_id, {})
     # With:
     signals = candidates.setdefault(document.id, {})
     ```
   - Reconcile `DocumentId` to maintain hash-table consistency, or standardize `RagDocument.id` across the corpus and update test assertions to check either `hit.document.id` or `hit.document.sources[0].record_id` cleanly without facade equality hacks.

2. **Deduplicate `fused` in Hybrid Retrieval**:
   - Ensure `fused` cannot contain duplicate documents, either by keying `candidates` by a single canonical key or by deduplicating hits before sorting into `final`.

3. **Fix Dual-Intent Sub-Procedure Query Penalization**:
   - In `backend/rag/retriever.py`, update sub-procedure discrimination so mutual penalties only apply when the query is single-intent:
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

---

## 5. Verification Method

To verify the defects and validate the required changes:

1. **Verify Hash Invariant Failure**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import DocumentId; d = DocumentId('primary', ['primary', 'rag_123']); s = {d}; assert 'rag_123' in s, 'Hash invariant violated'"
   ```
   *Current state*: Fails with `AssertionError: Hash invariant violated`.

2. **Verify Hybrid Retrieval Duplicate Hits**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import RagRetriever; from backend.rag.embeddings import FastEmbedProvider; from backend.rag.vector_store import QdrantLocalVectorStore; from backend.rag.runtime import DEFAULT_VECTOR_PATH; emb = FastEmbedProvider(); vs = QdrantLocalVectorStore(DEFAULT_VECTOR_PATH); ret = RagRetriever(embedding_provider=emb, vector_store=vs); res = ret.search('defective return 139(9)'); hits = [h.document.id for h in res.hits]; vs.close(); assert len(hits) == len(set(hits)), f'Duplicate hits found: {hits}'"
   ```
   *Current state*: Fails with `AssertionError: Duplicate hits found: ['itr_defective_return_manual_01', 'itr_defective_return_manual_01', ...]`

3. **Verify Dual-Intent Comparison Query**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import RagRetriever; ret = RagRetriever(); res = ret.search('What is the difference between Section 139(9) defective return notice and AIS feedback?', category='tax'); hit_ids = [h.document.id for h in res.hits[:3]]; assert 'itr_ais_feedback_manual_01' in hit_ids and 'itr_defective_return_manual_01' in hit_ids, f'Both documents must be in top 3, got: {hit_ids}'"
   ```
   *Current state*: Fails because `itr_ais_feedback_manual_01` is penalized by `-0.40` and excluded.
