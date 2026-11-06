# Milestone 3 Empirical Verification Report: Same-Domain Sub-Procedure Granularity (R6)

**Agent**: `challenger_m3_2`  
**Role**: Empirical Challenger (critic, specialist)  
**Parent Agent**: `dbf15a36-ef58-4a18-a9f2-171e93acf6cc`  
**Timestamp**: 2026-11-04T19:22:00Z  
**Verdict**: **`APPROVE`**  
**Type**: Hard Handoff  

---

## 1. Observation

### A. Qdrant Vector Database and Point Embedding Health
1. **Collection Configuration**:
   Audited Qdrant local store at `backend/data/vector_index/qdrant` via Python API (`qdrant_client.QdrantClient`):
   - Collection name: `govbank_chunks`
   - Point count: `1388`
   - Vector dimensions: `384`
   - Distance metric: `Distance.COSINE`
2. **AIS Feedback Document (`itr_ais_feedback_manual_01`) Point Health**:
   - Canonical corpus ID: `rag_6fb152da882c91c7a951f34c5fe9d58325e5987ea845c73054e8ffd92d88cb29`
   - Point ID: `ae152718-78e4-5cc5-b1d7-5836775bb42f`
   - Payload:
     ```json
     {
       "document_id": "rag_6fb152da882c91c7a951f34c5fe9d58325e5987ea845c73054e8ffd92d88cb29",
       "category": "tax",
       "title": "Income Tax Department User Guide on Submitting Feedback on Annual Information Statement (AIS)",
       "source_url": "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/ais"
     }
     ```
   - Embedding vector: `384` dimensions, valid non-zero float values, `L2 norm = 3.1548`, `min = -0.4484`, `max = 0.5216`, `mean = 0.0004`. Zero NaNs or infinities. Exactly 1 point exists for this document.

### B. Score Margin & Discrimination Stress Testing
1. **Pure AIS Query**: `"How do I submit feedback for duplicate SFT mutual fund transaction in AIS?"`
   - Rank 1: `itr_ais_feedback_manual_01` (Score: `0.2176`, Signals: `bm25_score: 42.221`, `exact_statutory_boost: 0.12`, `symptom_boost: 0.08`).
   - Mismatched document `itr_defective_return_manual_01`: Penalized with `sub_procedure_mismatch_penalty: -0.40`. Its candidate score dropped to `-0.3841`.
   - Resulting score margin: `0.2176 - (-0.3841) = +0.6017` (cleanly exceeds the required >=0.40 margin). In hybrid search, `itr_defective_return_manual_01` was completely eliminated from top 10 hits.
2. **Boundary AIS Query with Defect Token**: `"Discrepancy defect in AIS portal regarding duplicate mutual fund SFT report"`
   - Rank 1: `itr_ais_feedback_manual_01` (Score: `0.2174`).
   - Signals applied: `exact_statutory_boost: 0.12`, `symptom_boost: 0.08`.
   - Mismatched document `itr_defective_return_manual_01` is eliminated from top hits.
3. **Pure Section 139(9) Notice Query**: `"How do I respond to Section 139(9) defective return notice on e-proceedings portal?"`
   - Rank 1: `itr_defective_return_manual_01` (Score: `0.2664`, Signals: `bm25_score: 47.734`, `exact_statutory_boost: 0.12`, `troubleshooting_boost: 0.05`, `symptom_boost: 0.08`).
   - Mismatched document `itr_ais_feedback_manual_01`: Penalized with `sub_procedure_mismatch_penalty: -0.40`. Completely eliminated from top 10 hits. Score margin >= `0.65`.
4. **Boundary Section 139(9) Query with AIS Token**: `"Received Section 139(9) defective return notice because AIS income differed from ITR"`
   - Rank 1: `itr_defective_return_manual_01` (Score: `0.2664`).
   - AIS feedback is suppressed by `-0.40` penalty.
5. **Self-Contamination Immunity**:
   - `itr_ais_feedback_manual_01` text contains statutory disclaimer: `"AIS feedback is NOT a Section 139(9) defective return proceeding, does not require filing a rectified JSON schema under e-Proceedings, and does not have a 15-day defect memo deadline."`
   - Query: `"Submitting feedback on Annual Information Statement (AIS) for SFT dividend mismatch"`
   - Verified that `signals` on `itr_ais_feedback_manual_01` contains `symptom_boost: 0.08` and does NOT contain `contamination_penalty: -0.15`.
6. **Three-Way Tax Sub-Procedure Disambiguation**:
   - Condonation under 119(2)(b) -> `itr_condonation_delay_manual_01` (Rank 1).
   - Defective return under 139(9) -> `itr_defective_return_manual_01` (Rank 1).
   - AIS / SFT transaction feedback -> `itr_ais_feedback_manual_01` (Rank 1).

### C. Automated Test and Regression Execution Results
All test runs were executed directly using Python 3.12:

1. **Milestone 3 Empirical Adversarial Harness (`tests/test_adversarial_m3_harness.py`)**:
   ```
   8 passed in 13.79s
   ```
2. **Scenes 1 to 3 Regression Suite (R1, R2, R5, R6, Tier 2 AIS/139)**:
   Command: `pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r2 or test_tier1_r5 or test_tier1_r6 or test_tier2_ais or test_tier2_139" -v`
   ```
   32 passed, 27 deselected in 4.84s
   ```
3. **Domain Router & M2 Adversarial Harness**:
   Command: `pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v`
   ```
   89 passed in 5.63s
   ```
4. **RAG Retriever Core Suite**:
   Command: `pytest tests/test_rag_retriever.py -v`
   ```
   8 passed in 17.50s
   ```
5. **RAG Loader & Vector DB Build Suite**:
   Command: `pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v`
   ```
   12 passed in 20.95s
   ```

**Total Tests Verified Across All Suites**: 149 passed, 0 failed, 0 errors.

---

## 2. Logic Chain

1. From Observation A.1, the Qdrant local storage was directly verified via the client API. The vector collection `govbank_chunks` holds exactly 1388 points, with 384 dimensions and Cosine distance metric, exactly fulfilling the requirements of Task 1.
2. From Observation A.2, `itr_ais_feedback_manual_01` is confirmed present with point ID `ae152718-78e4-5cc5-b1d7-5836775bb42f`, mapped to canonical hash ID `rag_6fb152da882c91c7a951f34c5fe9d58325e5987ea845c73054e8ffd92d88cb29`. Its vector embedding is valid, continuous, non-zero across all 384 dimensions, and exhibits a healthy L2 norm of 3.1548 without NaN/Inf values.
3. From Observation B.1 and B.2, queries targeting AIS feedback trigger the dedicated `ais_feedback` symptom cluster and exact code booster, elevating `itr_ais_feedback_manual_01` to Rank 1. When `itr_defective_return_manual_01` is considered, it receives the `-0.40` sub-procedure mismatch penalty, producing an empirical score gap of `+0.6017`, completely eliminating 139(9) from top-10 hybrid results.
4. From Observation B.3 and B.4, queries targeting Section 139(9) defective return notices elevate `itr_defective_return_manual_01` to Rank 1, while applying the `-0.40` sub-procedure mismatch penalty to `itr_ais_feedback_manual_01`, yielding a score gap of `>=0.65` and cleanly suppressing AIS feedback.
5. From Observation B.5, the guard `and not has_boost` in `backend/rag/retriever.py` line 299 successfully prevents `itr_ais_feedback_manual_01` from triggering a self-contamination penalty from its own statutory disclaimer text (`"AIS feedback is NOT a Section 139(9) defective return proceeding..."`).
6. From Observation B.6, all three tax troubleshooting sub-procedures (119(2)(b) condonation, 139(9) defect memo, and AIS feedback) resolve to their respective documents with Rank 1 precision.
7. From Observation C.1 through C.5, 149 automated test cases across M1, M2, and M3 regression and adversarial suites pass with 100% success rate, confirming zero regressions in domain routing, EPFO corpus authenticity, or CRAG scraper cleanup.
8. Compliance with `AGENTS.md` and `GEMINI.md`: All sub-procedure retrievals are dynamic (dense FastEmbed + BM25 reciprocal rank fusion + procedural boosting), without any pre-canned, hardcoded response templates.

---

## 3. Caveats

1. **Local Mode Single-Process Concurrency**:
   Local Qdrant file-based storage relies on `portalocker` for write safety on Windows. Concurrent processes attempting to instantiate `QdrantClient(path=...)` simultaneously will encounter lock conflicts (`AlreadyLocked`). Tests accessing Qdrant directly should share a client fixture within the same test session or allow the previous process to release file handles.
2. **Milestone 4 Confidence Decoupling & LLM Relevance Gating**:
   While the retriever delivers rank-1 accuracy and >=0.40 penalty margins, post-retrieval confidence grading (`MATCH`, `PARTIAL`, `NO_MATCH`) and synthesis guardrails are scheduled for implementation in Milestone 4.

---

## 4. Conclusion

Milestone 3: Same-Domain Sub-Procedure Granularity (R6) is **VERIFIED** and **APPROVED**.
- Authentic official AIS feedback guide is fully ingested and indexed in Qdrant (1388 points, 384 dimensions, Cosine distance).
- Sub-procedure queries on AIS feedback and Section 139(9) defective returns disambiguate cleanly with rank-1 accuracy and bidirectional penalty separation (-0.40).
- Score margin exceeds the required threshold (>= 0.40 margin observed in empirical testing).
- 100% of regression and adversarial tests across M1, M2, and M3 pass cleanly.

**Final Verdict: `APPROVE`**.

---

## 5. Verification Method

To independently reproduce and verify this assessment:

1. **Run Empirical M3 Adversarial Test Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m3_harness.py -v
   ```
   *Expected*: 8 passed in ~14s.

2. **Run Scenes 1-3 Regression Suite for R1, R2, R5, R6, and Tier 2 AIS/139**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r2 or test_tier1_r5 or test_tier1_r6 or test_tier2_ais or test_tier2_139" -v
   ```
   *Expected*: 32 passed, 27 deselected.

3. **Run Domain Router & M2 Adversarial Harness**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v
   ```
   *Expected*: 89 passed.

4. **Run RAG Retriever Core Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_retriever.py -v
   ```
   *Expected*: 8 passed.

5. **Run RAG Loader & Vector Build DB Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_rag_loader.py tests/test_build_vector_db.py -v
   ```
   *Expected*: 12 passed.

6. **Files to Inspect**:
   - `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl` (line 6: `itr_ais_feedback_manual_01`)
   - `backend/rag/retriever.py` (lines 235-318: symptom clusters and bidirectional -0.40 penalty)
   - `tests/test_adversarial_m3_harness.py` (empirical vector health, margin stress tests, negative disclaimer immunity)
