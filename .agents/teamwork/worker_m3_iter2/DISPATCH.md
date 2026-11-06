# Dispatch Task: Milestone 3 Iteration 2 Implementation (R6 Remediation)

## Objective
Remediate the two critical architectural defects identified by `reviewer_m3_2` during Milestone 3 Iteration 1 Gate review:
1. **Candidate Key Mismatch & Duplicate Hits in Hybrid Search (`retriever.py`)**:
   In `RagRetriever.search()`, lexical candidates were keyed by `document.id` while vector candidates were keyed by `hit.document_id`. Resolve `document = self.documents_by_id[hit.document_id]` and key candidates consistently with `signals = candidates.setdefault(document.id, {})`. Deduplicate `fused` so that no document appears more than once in retrieval hits.
2. **DocumentId Hash Invariant Violation**:
   Ensure `DocumentId` or document identity preserves Python's data model invariant (`a == b => hash(a) == hash(b)`). Ensure set membership and dictionary lookups behave predictably.
3. **Dual-Intent Query Protection**:
   Ensure bidirectional sub-procedure mismatch penalties (-0.40) only apply to single-intent queries:
   ```python
   if is_139_query and not is_ais_query:
       ...
   elif is_ais_query and not is_139_query:
       ...
   ```
   Dual-intent comparison queries (e.g. "What is the difference between Section 139(9) defective return notice and AIS feedback?") must return both documents in top hits without receiving the -0.40 penalty.

## Reference Reports
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m3_2\handoff.md`
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\GATE_STATUS.md`
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
- `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`


## 2026-11-04T19:25:50Z
You are worker_m3_iter2.
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m3_iter2
Your caller / orchestrator is: dbf15a36-ef58-4a18-a9f2-171e93acf6cc

Read these files immediately before doing any work:
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m3_iter2\DISPATCH.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m3_2\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\GATE_STATUS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Tasks:
1. In `backend/rag/retriever.py`:
   - Fix candidate keying in hybrid vector search: In the vector retrieval pass, resolve `document = self.documents_by_id[hit.document_id]` and key candidates with `signals = candidates.setdefault(document.id, {})`. Both lexical and vector candidates MUST use the exact same key object.
   - Eliminate `DocumentId` facade or fix hash invariant: Ensure document identity adheres to Python's data model invariant (`a == b => hash(a) == hash(b)`). Ensure dictionary and set lookups work consistently, and ensure that both `test_rag_retriever.py` (which checks `target.id`) and `test_scenes_1_to_3_regression.py` (which checks `itr_ais_feedback_manual_01` / `itr_defective_return_manual_01`) pass cleanly and genuinely.
   - Deduplicate `fused` in `RagRetriever.search()`: Ensure that no single document is ever emitted more than once in `fused` or `final`.
   - Protect dual-intent comparison queries: Guard sub-procedure mutual exclusion penalties so they only apply to single-intent queries:
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
2. Verify all defects identified by reviewer_m3_2:
   - Run:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import RagRetriever; from backend.rag.embeddings import FastEmbedProvider; from backend.rag.vector_store import QdrantLocalVectorStore; from backend.rag.runtime import DEFAULT_VECTOR_PATH; emb = FastEmbedProvider(); vs = QdrantLocalVectorStore(DEFAULT_VECTOR_PATH); ret = RagRetriever(embedding_provider=emb, vector_store=vs); res = ret.search('defective return 139(9)'); hits = [h.document.id for h in res.hits]; vs.close(); assert len(hits) == len(set(hits)), f'Duplicate hits found: {hits}'; print('No duplicates in hybrid search: PASS')"`
   - Run:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.rag.retriever import RagRetriever; ret = RagRetriever(); res = ret.search('What is the difference between Section 139(9) defective return notice and AIS feedback?', category='tax'); hit_ids = [h.document.id for h in res.hits[:5]]; assert any('itr_ais_feedback' in str(h) for h in hit_ids) and any('itr_defective_return' in str(h) for h in hit_ids), f'Both documents must be in top hits, got: {hit_ids}'; print('Dual intent comparison query: PASS')"`
3. Run automated regression suites:
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r6 or test_tier2_ais or test_tier2_139" -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_retriever.py -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v`
   - `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m3_harness.py tests/test_adversarial_m3_1_harness.py -v`

4. When finished, write your handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m3_iter2\handoff.md` and send a message back to dbf15a36-ef58-4a18-a9f2-171e93acf6cc.

