# Milestone 3 Empirical Challenger Verification Report: Same-Domain Sub-Procedure Granularity (R6)

**Agent**: `challenger_m3_1`  
**Parent Agent**: `dbf15a36-ef58-4a18-a9f2-171e93acf6cc`  
**Timestamp**: 2026-11-04T19:24:00Z  
**Type**: Hard Handoff  
**Verdict**: `APPROVE`  

---

## 1. Observation

1. **Automated Test Suite Execution (Python 3.12)**:
   - **M3 (R6) Regression Tests**:
     Command:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r6 or test_tier2_ais or test_tier2_139" -v`
     Result: `7 passed, 52 deselected in 4.90s`
     All 7 targeted tests (`test_tier1_r6_ais_feedback_document_exists`, `test_tier1_r6_ais_feedback_content_accuracy`, `test_tier1_r6_retriever_exact_code_booster`, `test_tier1_r6_symptom_cluster_ais_vs_139`, `test_tier1_r6_sub_procedure_bidirectional_discrimination`, `test_tier2_ais_query_with_defect_keyword`, `test_tier2_139_query_with_ais_keyword`) passed.
   - **Corpus Loader & Vector Store Tests**:
     Command:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v`
     Result: `12 passed in 18.04s`
     Reconciled corpus counts (1368 accepted records, 1388 indexed points in Qdrant `govbank_chunks`, 116 tax documents) validated.
   - **Non-Regression on R1, R2, R5**:
     Command:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r2 or test_tier1_r5" -v`
     Result: `25 passed, 34 deselected in 5.37s`
     EPFO authenticity (R1), MCA/LPG/NSP hard domain routing and short-circuit (R2), and Trafilatura table-free scraping (R5) remain regression-free.
   - **Core RAG Retriever Suite**:
     Command:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_retriever.py -v`
     Result: `8 passed in 30.36s`

2. **Empirical Adversarial Boundary Queries (Direct Retrieval Inspection)**:
   - **Query A (Discrepancy defect in AIS)**:
     `"Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report"`
     - Rank 1: `itr_ais_feedback_manual_01`, Score: `0.2174`
     - Signals: `bm25_score: 33.87, lexical_rrf: 0.0164, exact_statutory_boost: 0.12, symptom_boost: 0.08`
     - Rank 2: `itr_individual_filing_workflow_01` (0.0969); `itr_defective_return_manual_01` is completely absent from top 3.
   - **Query B (Defective notice due to AIS mismatch)**:
     `"Received Section 139(9) defective return notice because AIS income differed from ITR"`
     - Rank 1: `itr_defective_return_manual_01`, Score: `0.2664`
     - Signals: `bm25_score: 49.16, exact_statutory_boost: 0.12, troubleshooting_boost: 0.05, symptom_boost: 0.08`
     - Rank 2: `itr_ais_feedback_manual_01`, Score: `-0.1330`
     - Signals on AIS: `sub_procedure_mismatch_penalty: -0.40`, depressed below 0 by clean margin of `0.3994`.
   - **Query C (Duplicate interest in AIS)**:
     `"How to correct duplicate interest in Annual Information Statement?"`
     - Rank 1: `itr_ais_feedback_manual_01`, Score: `0.2164`
     - Signals: `bm25_score: 28.07, exact_statutory_boost: 0.12, symptom_boost: 0.08`
     - Section 139(9) defective return is completely absent from top 20 candidates (0 lexical/vector bleeding).
   - **Query D (15-day defect memo response)**:
     `"How to respond to e-proceedings 15-day defect memo for defective return?"`
     - Rank 1: `itr_defective_return_manual_01`, Score: `0.1464`
     - Signals: `bm25_score: 43.89, troubleshooting_boost: 0.05, symptom_boost: 0.08`
     - AIS feedback is completely absent from top 20 candidates (0 bleeding).
   - **Query E (Ambiguous dividend transaction)**:
     `"My AIS has wrong dividend transaction what should I do"`
     - Rank 1: `itr_ais_feedback_manual_01`, Score: `0.0181`
     - Production top_k=3 (`retrieve_if_enabled`): `itr_defective_return_manual_01` is absent.
     - In expanded candidate search: `itr_defective_return_manual_01` matched token 'ais' in its body text, but was penalized with `sub_procedure_mismatch_penalty: -0.40` driving its score down to `-0.3841`.

3. **Dedicated Adversarial Challenge Suite (`tests/test_adversarial_m3_1_harness.py`)**:
   Executed 16 automated stress tests covering:
   - Queries A through E boundary assertions.
   - Unspecified category routing (automatic classification to `Domain.TAXATION`).
   - Hinglish phrasings (`"AIS me duplicate transaction kaise hataye"`, `"139(9) defective return notice ka reply e-proceedings me kaise kare"`).
   - End-to-end pipeline citation isolation (`run_pipeline` cleanly isolates AIS citations from 139(9) citations).
   - Self-contamination immunity: AIS manual contains `"AIS feedback is NOT a Section 139(9) defective return proceeding..."` and `has_boost` guard in `retriever.py:299` ensures no false self-penalty occurs.
   - Document integrity: verified `itr_ais_feedback_manual_01` in `troubleshooting_tax.jsonl` contains official portal URLs and authentic feedback categories.
   Command:
   `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m3_1_harness.py -v`
   Result: `16 passed in 15.06s`.

---

## 2. Logic Chain

1. From Observation 1, authentic record `itr_ais_feedback_manual_01` exists in `troubleshooting_tax.jsonl` and the vector index contains 1388 synchronized embeddings, verified by automated unit tests passing 100%.
2. From Observation 2 (Queries A, C, E), queries regarding AIS errors, duplicate transactions, or discrepancies activate `is_ais_query` and the `ais_feedback` symptom cluster. In each case, `itr_ais_feedback_manual_01` ranks #1 with exact statutory boost (+0.12) and symptom boost (+0.08).
3. From Observation 2 (Query B, D), queries regarding Section 139(9), defective return notices, or 15-day defect memos activate `is_139_query` and the `defective_return` symptom cluster. In each case, `itr_defective_return_manual_01` ranks #1.
4. When both procedure tokens appear in the same query (Observation 2, Query B):
   - `itr_defective_return_manual_01` achieves score `0.2664`.
   - `itr_ais_feedback_manual_01` receives `sub_procedure_mismatch_penalty: -0.40`, dragging its score down to `-0.1330`.
   - The resulting separation margin of `0.3994` decisively prevents false ranking.
5. In Query E, although `itr_defective_return_manual_01` mentions `AIS` in its body text, the sub-procedure discriminator detects `is_ais_query` and applies `-0.40`, lowering the defective return score to `-0.3841` and eliminating it from production `top_k=3` retrieval.
6. From Observation 3, running `run_pipeline()` proves that the RAG pipeline end-to-end yields `"high"` confidence answers with strict citation isolation (0 cross-procedure citation leakage).
7. Non-regression tests confirm that prior milestones (M1 EPFO corpus, M1 Trafilatura scraper, M2 Uncovered domain routing) remain intact.

---

## 3. Caveats

- In queries where fewer than `top_k` documents are indexed for a domain, heavily penalized negative-score candidates (e.g. score `-0.3841`) remain in the raw returned tuple if no positive-score filter (`score > 0`) is applied on the raw retriever output. However, in production `retrieve_if_enabled()` (top_k=3) and downstream relevance gating, these negative-score hits are discarded.
- No production source files were modified during this verification; all adversarial assertions were executed in standalone test files.

---

## 4. Conclusion

Milestone 3 (R6 Same-Domain Sub-Procedure Granularity) satisfies all empirical acceptance criteria:
- Authentic AIS feedback manual is ingested and indexed into Qdrant.
- Exact code boosters (+0.12) and symptom clusters (+0.08) accurately reward matching procedures.
- Bidirectional mismatch penalty (-0.40) decisively separates Section 139(9) defective returns from AIS feedback.
- Boundary Queries A, B, C, D, and E achieve 100% Rank-1 precision with zero cross-contamination in primary citations.
- 100% of regression and adversarial test suites pass.

**Verdict**: `APPROVE`.

---

## 5. Verification Method

To independently verify this evaluation, execute the following commands in powershell:

1. **Run R6 Regression Tests**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r6 or test_tier2_ais or test_tier2_139" -v
   ```
   *Expected*: `7 passed, 52 deselected`.

2. **Run Corpus Loader and Vector DB Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v
   ```
   *Expected*: `12 passed`.

3. **Run M1/M2/M5 Non-Regression Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r2 or test_tier1_r5" -v
   ```
   *Expected*: `25 passed, 34 deselected`.

4. **Run Empirical Adversarial Challenge Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m3_1_harness.py -v
   ```
   *Expected*: `16 passed`.
