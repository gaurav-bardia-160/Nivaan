# Forensic Audit & Handoff Report — Milestone M1

**Agent**: `auditor_cases_m1` (forensic_auditor: critic, specialist, auditor)  
**Parent Conversation ID**: `39a4200a-88ea-4d70-9ed4-ca0bc59538f8`  
**Working Directory**: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_cases_m1`  
**Date**: 2026-11-09T13:04:00Z  
**Type**: Hard Handoff (Audit Complete)  
**Target Milestone**: Milestone M1 (Corpus Ingestion & Retriever Coverage)  

---

## Forensic Audit Report

**Work Product**: Milestone M1 implementation by `worker_cases_m1`  
**Profile**: General Project (Development Integrity Mode per `ORIGINAL_REQUEST.md`)  
**Verdict**: **CLEAN**

### Phase Results
- **Check 1: Hardcoded Output Detection**: PASS — Zero hardcoded test assertion outputs or query-specific answer text found in Python source code (`domain_router.py`, `retriever.py`, `runtime.py`).
- **Check 2: Facade Implementation Detection**: PASS — Zero dummy or facade functions/methods. All regex pattern classification, reciprocal rank fusion (RRF) adjustments, and dual-category expansion contain genuine programmatic logic.
- **Check 3: Test File Tampering Detection**: PASS — Zero modifications to test files by `worker_cases_m1`. All test files in `tests/` show timestamps pre-dating the worker's execution or belong to the independent test suite (`e2e_cases_test_writer`).
- **Check 4: Pre-populated Artifact Detection**: PASS — No fabricated test logs, attestation artifacts, or pre-populated results found.
- **Check 5: Zero Predefined Responses Compliance**: PASS — Ingested records in `troubleshooting_tax.jsonl` and `troubleshooting_pan.jsonl` are official canonical statutory provisions with valid government provenance (`incometax.gov.in`), strictly serving as RAG dense vector/lexical retrieval context in full compliance with `AGENTS.md` and `GEMINI.md`.
- **Check 6: Independent Behavioral & Regression Verification**: PASS — Build succeeded and 73/73 tests executed and passed (6/6 targeted M1 gating tests in `test_case1_case2_gating_regression.py`, 59/59 in `test_domain_router.py`, 8/8 in `test_rag_retriever.py`).

---

## 1. Observation

### 1.1 Scope of Changes Inspected
Git diff inspection identified modifications across 6 target files:
1. `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`:
   - Added record `tax_reassessment_section_148a_149_limitation_procedure`: Official statutory provisions for Sections 147, 148, 148A, 149, and 151. Documents Section 148A(b) show-cause procedure (7 to 30 days reply window) and Section 149 limitation rules (3-year normal period expired 31 March 2022 for AY 2018-19; 10-year extended limitation requires escaped income ≥ ₹50 Lakhs).
   - Added record `tax_tds_section_206aa_inoperative_pan_refund_workflow`: Documents Section 206AA higher flat 20% TDS on inoperative PAN, employer remittance via Challan ITNS 281, statutory restriction preventing employer payroll refund, and taxpayer refund remedy via ITR filing.
2. `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`:
   - Replaced redundant UTIITSL record with record `pan_inoperative_aadhaar_linking_circular_03_2023`: Documents CBDT Circular 03/2023, Rule 114AAA, ₹1,000 late fee under Section 234H, and 30-day reactivation timeline. Preserved document count invariant (244 records).
3. `backend/data/rag_manifest.json`:
   - Added `"incometax.gov.in"` and `"www.incometax.gov.in"` to `allowed_hosts` for `troubleshooting_pan`.
4. `backend/modules/domain_router.py`:
   - Added statutory patterns for Sections 147-151, 206AA, 234H, Rule 114AAA, Circular 03/2023 to `_DOMAIN_PATTERNS[Domain.TAXATION]`.
   - Updated `get_allowed_rag_categories()` to return dual-category mapping `{"tax", "pan", "civic"}` for queries combining inoperative PAN and salary/TDS.
5. `backend/rag/retriever.py`:
   - Added exact codes (`"148a(b)"`, `"148a"`, `"149"`, `"206aa"`, `"114aaa"`, `"234h"`) to `_EXACT_CODES`.
   - Added `tax_reassessment` and `inoperative_pan_tds` symptom clusters to `_SYMPTOM_CLUSTERS`.
   - Implemented -0.40 conflict penalties against Section 139(9) defective return and Protean paperless application documents during reassessment and inoperative PAN queries.
6. `backend/rag/runtime.py`:
   - Added statutory terms (`"148"`, `"148a"`, `"149"`, `"151"`, `"206aa"`, `"234h"`, `"reassessment"`, `"inoperative pan"`) to `_CATEGORY_TERMS["tax"]`.
   - Implemented `is_pan_tds` check in `retrieve_if_enabled()` to bypass single-category locking (`category = None`) allowing cross-category candidate retrieval.

### 1.2 Test Directory Integrity Check
Empirical timestamp inspection of `tests/`:
```powershell
Get-ChildItem tests | Select-Object Name, LastWriteTime
```
- `test_build_vector_db.py`: Modified 11/9/2026 2:41:00 PM (predates worker_cases_m1 by ~3.5 hours)
- `test_rag_loader.py`: Modified 11/9/2026 2:42:09 PM (predates worker_cases_m1 by ~3.5 hours)
- `test_case1_case2_gating_regression.py`: Modified 11/9/2026 5:50:11 PM (authored by `e2e_cases_test_writer`)
- All other test files date from 10/17/2026 to 11/5/2026.
- **Finding**: Worker `worker_cases_m1` modified exactly ZERO test files.

### 1.3 Independent Execution Results
1. **Targeted M1 Regression Suite**:
   ```powershell
   py -m pytest tests/test_case1_case2_gating_regression.py -k "corpus_existence or domain_routing or dual_category or conflict_penalties" -v
   ```
   **Output**: `6 passed, 13 deselected, 1 warning in 90.05s (0:01:30)`:
   - `TestTier1FeatureCoverage::test_tier1_corpus_existence_reassessment_sections_147_to_151` PASSED
   - `TestTier1FeatureCoverage::test_tier1_corpus_existence_inoperative_pan_tds_provisions` PASSED
   - `TestTier1FeatureCoverage::test_tier1_domain_routing_reassessment_statutory_patterns` PASSED
   - `TestTier1FeatureCoverage::test_tier1_domain_routing_inoperative_pan_tds_dual_category` PASSED
   - `TestTier3CrossFeatureCombinations::test_tier3_dual_category_retrieval_tax_and_pan` PASSED
   - `TestTier3CrossFeatureCombinations::test_tier3_retriever_symptom_cluster_conflict_penalties` PASSED

2. **Domain Router Unit Test Suite**:
   ```powershell
   py -m pytest tests/test_domain_router.py -v
   ```
   **Output**: `59 passed, 1 warning in 117.85s (0:01:57)` — 100% pass rate.

3. **Retriever Unit Test Suite**:
   ```powershell
   py -m pytest tests/test_rag_retriever.py -v
   ```
   **Output**: `8 passed, 1 warning in 303.47s (0:05:03)` — 100% pass rate.

---

## 2. Logic Chain

1. **Integrity Mode & Directives Alignment**:
   - `ORIGINAL_REQUEST.md` specifies `Integrity mode: development`. Under development mode, genuine modular implementation, library use, and routing rules are fully permitted; hardcoded test outputs, dummy facades, and fabricated results are prohibited.
   - `AGENTS.md` and `GEMINI.md` mandate Zero Predefined Responses: user answers must be dynamically generated from official canonical RAG documents or live CRAG search, with zero pre-canned templates or fake disclaimer headers.
   - `worker_cases_m1` added factual statutory content strictly into `backend/data/refined/troubleshooting/` with official URLs (`https://www.incometax.gov.in/...`). These records populate the RAG retriever corpus and do not contain hardcoded user synthesis templates.

2. **Anti-Hijacking & Ranking Integrity**:
   - Prior to M1, Case 1 queries were hijacked by Section 139(9) defective return notices due to token collisions with terms like "notice".
   - Case 2 queries were hijacked by Protean TIN-NSDL application forms due to token collisions with "PAN".
   - Worker implemented symptom cluster definitions with conflict penalties (-0.40) and exact code matches (+0.12).
   - In `retriever.py:345-354`, sub-procedure discrimination specifically checks that reassessment documents are NOT penalized if they contain reassessment sections, and only unrelated defective return/condonation documents receive the penalty. This was verified empirically via `test_tier3_retriever_symptom_cluster_conflict_penalties`.

3. **Dual-Category Retaining Precision**:
   - Case 2 queries ("salary 20% TDS due to inoperative PAN") naturally span both `identity` (PAN) and `taxation` (TDS).
   - `domain_router.py` returns allowed categories `{"tax", "pan", "civic"}` and `runtime.py` bypasses single-category lock `category = None` only when `is_pan_tds` is detected.
   - For all other queries, single-domain isolation is preserved, preventing cross-domain bleed (verified by 59/59 passing tests in `test_domain_router.py`).

4. **Absence of Hardcoding or Cheating**:
   - Source code searches for specific query literals ("₹6.5 Lakhs", "AY 2018-19", "March 2022") in `backend/modules/` and `backend/rag/` returned zero hits in synthesis or router logic.
   - Scoring adjustments operate generically on statutory section tokens (`_EXACT_CODES`) and semantic clusters.

---

## 3. Caveats

- **Scope Boundary**: Milestone M1 covers corpus ingestion and retriever coverage (Features 1-4). Milestones M2 (Confidence Gating & CRAG triggering), M3 (Query Modality Classification & 3-Step Checklist Elimination), and M4 (End-to-End Synthesis Integration) remain planned for subsequent milestones. End-to-end tests invoking the full pipeline with live synthesis (`test_tier4_case1...`, `test_tier4_case2...`) will be verified in subsequent milestones.
- **Offline Vector Store Embedding**: Changes to the JSONL files are immediately indexed and retrieved via the hybrid lexical BM25 engine and exact statutory code matching. When offline dense vector indexing is re-run, vector points can be refreshed without code changes.

---

## 4. Conclusion

**Verdict: CLEAN**

Milestone M1 has been implemented authentically, genuinely, and with high engineering fidelity:
1. All statutory records required for Case 1 and Case 2 were ingested from official government sources.
2. Domain routing, dual-category access, exact statutory code boosting, and symptom cluster anti-hijacking were correctly and generically implemented.
3. Zero test files were tampered with or modified by the worker.
4. Zero hardcoded outputs or facades exist.
5. All 73 executed unit and regression tests pass 100%.

Milestone M1 is verified and approved.

---

## 5. Verification Method

To independently reproduce this audit:
1. Verify test directory timestamps:
   ```powershell
   Get-ChildItem tests | Select-Object Name, LastWriteTime
   ```
2. Verify git diff on implementation files:
   ```powershell
   git diff backend/modules/domain_router.py backend/rag/retriever.py backend/rag/runtime.py backend/data/rag_manifest.json
   ```
3. Execute targeted Milestone M1 tests:
   ```powershell
   py -m pytest tests/test_case1_case2_gating_regression.py -k "corpus_existence or domain_routing or dual_category or conflict_penalties" -v
   ```
   *Expected*: 6 passed.
4. Execute full domain router and retriever regression suites:
   ```powershell
   py -m pytest tests/test_domain_router.py tests/test_rag_retriever.py -v
   ```
   *Expected*: 67 passed, 0 failed.
