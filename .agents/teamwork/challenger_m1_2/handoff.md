# Milestone 1 Adversarial Verification Report: EPFO Corpus & Vector DB Integrity (R1)

## Verdict: APPROVE

---

## 1. Observation

### 1.1 Vector Database Inspection
1. **Direct Qdrant Collection Geometry & Configuration**:
   Executed via direct Qdrant client connection against `backend/data/vector_index/qdrant`:
   ```python
   client = QdrantClient(path=r'C:\Users\gaura\Documents\nivaan\backend\data\vector_index\qdrant')
   info = client.get_collection('govbank_chunks')
   ```
   - **Points count**: `1387`
   - **Vector dimension**: `384`
   - **Distance metric**: `Distance.COSINE`
   - **Collection name**: `govbank_chunks`

2. **Index Metadata & Corpus Checksum Parity**:
   Inspected `backend/data/vector_index/qdrant/meta.json` and `govbank_index.json`:
   - `corpus_sha256`: `5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6`
   - Matches exactly with `load_corpus().report.corpus_sha256`: `5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6`
   - Expected documents: `1387`
   - Re-verified via `python -m backend.offline.ensure_vector_db --check-only`:
     ```json
     {
       "path": "C:\\Users\\gaura\\Documents\\nivaan\\backend\\data\\vector_index\\qdrant",
       "collection": "govbank_chunks",
       "expected_documents": 1387,
       "corpus_sha256": "5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6",
       "ready": true,
       "points": 1387,
       "dimensions": 384,
       "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
       "reason": "ready"
     }
     ```

### 1.2 EPFO Corpus Content & Allowlist Inspection
1. **Target Document**: `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl` (Line 10, ID: `epfo_claim_passbook_cheque_standards_01`):
   - **Source URL**: `https://www.epfindia.gov.in/site_docs/PDFs/Circulars/Y2024-2025/WSU_IssueOfBKG_49885_16.pdf`
   - **Title**: `EPFO Passbook and Cheque Leaf Validation Standards for Form 19 and 31 Claims`
   - **Section**: `Terminal Settlement Rejections and Visual Passbook/Cheque Validation Criteria`
   - **Status**: `automated_verified`
   - **Quality Score**: `1.0`
   - **Source Confidence**: `official`
   - **Retrieval Tags**: `["troubleshooting", "escalation", "sop", "epf_claim_rejected", "epf_cheque_rejected", "name_not_printed_cheque", "epf_passbook_stamp", "form_19_rejection", "form_31_rejection", "epf_bank_kyc"]`
   - Verified: Non-matching Inspector Compliance Manual URL and tag `"manual"` have been cleanly removed. No PMVBRY boilerplate exists.
2. **Manifest Allowlist**: `backend/data/rag_manifest.json` under `troubleshooting_civic`:
   - `allowed_hosts` includes both `epfindia.gov.in` and `www.epfindia.gov.in`.

### 1.3 Empirical Hybrid Retrieval & Ranking Stress Tests
Tested with `FastEmbedProvider` (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) and Qdrant local vector store combined with BM25 Reciprocal Rank Fusion:

| # | Test Query | Top Hit ID | Score | Rank 1 Target Document | Expected Document In Top Hits |
|---|------------|------------|-------|------------------------|-------------------------------|
| 1 | `pre-printed name missing on cheque Form 19 rejection` | `epfo_claim_passbook_cheque_standards_01` | `0.2028` | EPFO Passbook and Cheque Leaf Validation Standards | YES (Rank 1) |
| 2 | `EPFO Form 19 rejection cancelled cheque stamp` | `epfo_claim_passbook_cheque_standards_01` | `0.2028` | EPFO Passbook and Cheque Leaf Validation Standards | YES (Rank 1) |
| 3 | `Why was my EPF claim rejected due to cancelled cheque leaf?` | `epfo_claim_passbook_cheque_standards_01` | `0.0828` | EPFO Passbook and Cheque Leaf Validation Standards | YES (Rank 1) |
| 4 | `cancelled cheque leaf without pre-printed name EPF claim rejected` | `epfo_claim_passbook_cheque_standards_01` | `0.0828` | EPFO Passbook and Cheque Leaf Validation Standards | YES (Rank 1) |
| 5 | `passbook not attested bank manager stamp EPFO Form 31` | `epfo_claim_passbook_cheque_standards_01` | `0.0828` | EPFO Passbook and Cheque Leaf Validation Standards | YES (Rank 1) |
| 6 | `epfo cancelled cheque me naam nahi hai claim reject ho gaya` (Hinglish) | `epfo_claim_passbook_cheque_standards_01` | `0.0792` | EPFO Passbook and Cheque Leaf Validation Standards | YES (Rank 1) |
| 7 | `establishment closed company shut down employer untraceable Joint Declaration` | `epfo_closed_establishment_attestation_01` | `0.1984` | EPFO Attestation Framework for Closed Establishments | YES (Rank 1) |
| 8 | `bank manager attestation closed establishment RPFC physical joint declaration` | `epfo_closed_establishment_attestation_01` | `0.1950` | EPFO Attestation Framework for Closed Establishments | YES (Rank 1) |
| 9 | `EPFO Joint Declaration minor major modifications name date of birth correction Annexure-I` | `epfo_joint_declaration_minor_major_sop_01` | `0.1982` | EPFO Joint Declaration SOP (JD/2022/1) | YES (Rank 1) |

### 1.4 Cross-Domain Bleed Resistance Stress Tests
Challenged retrieval with corporate, petroleum, and scholarship queries:
- Query: `SPICe+ Part A Rule 8A corporate name reservation guidelines`
  * Top 3 hits: `UTIITSL Annexure B` (score 0.0297), `UTIITSL Annexure C` (score 0.0296), `tinpan FAQ` (score 0.0280).
  * `epfo_claim_passbook_cheque_standards_01` retrieved? **NO** (0 occurrences).
- Query: `MCA SPICe+ company incorporation name approval criteria`
  * Top 3 hits: `tinpan PAN Form 93-94` (score 0.0301), `tinpan FAQ` (score 0.0298), `UTIITSL Changes FAQ` (score 0.0273).
  * `epfo_claim_passbook_cheque_standards_01` retrieved? **NO** (0 occurrences).
- Query: `Ministry of Corporate Affairs name reservation objection Rule 8`
  * `epfo_claim_passbook_cheque_standards_01` retrieved? **NO** (0 occurrences).
- Query: `petroleum LPG subsidy direct benefit transfer DBTL ujjwala`
  * `epfo_claim_passbook_cheque_standards_01` retrieved? **NO** (0 occurrences).
- Query: `NSP national scholarship portal verification institute nodal officer`
  * `epfo_claim_passbook_cheque_standards_01` retrieved? **NO** (0 occurrences).

### 1.5 Automated Test Suite Execution Results
1. **Dedicated Adversarial Suite** (`tests/test_adversarial_m1_2_epfo_vector.py`):
   - Command: `pytest tests/test_adversarial_m1_2_epfo_vector.py -v`
   - Result: `19 passed in 13.40s` (0 failures, 0 warnings).
2. **Tier 1 R1 Regression Suite** (`tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1"`):
   - Result: `5 passed, 54 deselected in 1.30s`.
3. **Canonical Loader and DB Build Tests** (`tests/test_rag_loader.py tests/test_build_vector_db.py`):
   - Result: `12 passed in 25.81s`.
4. **Vector Readiness Tests** (`tests/test_vector_readiness.py`):
   - Result: `5 passed in 1.67s`.

---

## 2. Logic Chain

1. **Corpus Remediation (Observation 1.2)**:
   - Worker M1 substituted the non-matching `Manual_for_Inspector_cum_Facilitator.pdf` URL with authentic circular `WSU_IssueOfBKG_49885_16.pdf` on `www.epfindia.gov.in`.
   - Inspection of `backend/data/rag_manifest.json` confirms `www.epfindia.gov.in` is in `allowed_hosts`.
   - Inspection of the record text proves it provides visual standards for cancelled cheques (pre-printed name mandatory) and passbooks (manager stamp and signature).
   - Therefore, Requirement R1 is cleanly satisfied at the corpus layer.

2. **Vector Store Integrity (Observation 1.1)**:
   - Direct inspection via `QdrantClient` confirms `points_count: 1387`, `vector_size: 384`, `distance: Cosine`.
   - The corpus SHA256 checksum in `meta.json` (`5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6`) exactly matches the computed checksum from `load_corpus()`.
   - `ensure_vector_db --check-only` returns `ready: true`.
   - Therefore, the vector database is completely built, sound, and fully synchronized with the 1387-document corpus.

3. **Hybrid Retrieval and Bleed Resistance (Observations 1.3 & 1.4)**:
   - Queries directly mentioning cancelled cheque or passbook rejection scenarios cleanly retrieve `epfo_claim_passbook_cheque_standards_01` as Rank 1 across all tested variants (formal English, conversational query, and Hinglish).
   - Because the worker removed `"manual"` from tags and added `"epf_claim_rejected"` and `"epf_bank_kyc"`, generic corporate queries (SPICe+, Rule 8A, MCA name approval) do not match lexical tokens or dense vector neighborhoods for this document.
   - Bleed stress tests confirmed 0 appearances of `epfo_claim_passbook_cheque_standards_01` across corporate, LPG subsidy, and scholarship queries.

4. **Zero Predefined Response Directives (`AGENTS.md` / `GEMINI.md`)**:
   - All retrieved answers and hits are generated purely through dynamic hybrid retrieval (vector similarity + BM25 RRF fusion) over the canonical corpus JSONL chunks. No hardcoded or pre-canned answers were introduced.

---

## 3. Caveats

1. **File Locking in Local Qdrant**:
   - `qdrant-client` local file-storage enforces single-process locking via `portalocker`. If multiple processes attempt to initialize `QdrantClient` simultaneously against the same folder, subsequent processes will receive a `RuntimeError: Storage folder is already accessed by another instance`.
   - `backend/rag/runtime.py` safely catches this error and falls back to deterministic lexical retrieval (`lexical_candidate_corpus`), ensuring the application never crashes.
   - For tests and verification commands, ensuring proper cleanup (`client.close()` or module fixtures) ensures vector mode runs without lock contention.
2. **Domain Routing Short-Circuit (R2)**:
   - While corporate queries do not retrieve EPFO cheque records, general fallback queries for uncovered domains will be fully short-circuited in Milestone 2 (`Domain.UNCOVERED` in `domain_router.py`).

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone 1 R1 (EPFO Corpus Remediation and Vector Database Integrity) meets all specifications and passes all adversarial stress tests:
- `troubleshooting_civic.jsonl` contains authentic official circular URL and precise retrieval tags.
- Qdrant embedded collection `govbank_chunks` is completely built and synchronized with 1387 vectors of dimension 384 and Cosine distance metric.
- Retrieval ranking is robust: EPFO cancelled cheque rejection queries achieve Rank 1 resolution.
- Corporate name reservation queries exhibit 0 retrieval bleed into EPFO records.
- 100% of automated tests (41 tests across 5 test suites) pass cleanly.

---

## 5. Verification Method

To independently verify this empirical evaluation, run the following commands in powershell:

```powershell
# 1. Verify Qdrant Vector Store readiness and point count
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db --check-only

# 2. Run the dedicated 19-test adversarial test harness
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_adversarial_m1_2_epfo_vector.py -v

# 3. Run Tier 1 R1 regression tests
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_scenes_1_to_3_regression.py -k "test_tier1_r1" -v

# 4. Invalidation Conditions
# - If points count in govbank_chunks != 1387
# - If corpus_sha256 != 5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6
# - If tests/test_adversarial_m1_2_epfo_vector.py fails any test
```
