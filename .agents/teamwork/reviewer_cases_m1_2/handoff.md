# Handoff Report — Milestone M1 Independent Review & Adversarial Audit

**Agent**: `reviewer_cases_m1_2` (teamwork_reviewer, critic)  
**Parent Conversation ID**: `39a4200a-88ea-4d70-9ed4-ca0bc59538f8`  
**Working Directory**: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_cases_m1_2`  
**Date**: 2026-11-09T13:06:00Z  
**Type**: Hard Handoff (Milestone M1 Review Complete)

---

## Review Summary

**Verdict**: **APPROVE**  
**Integrity Status**: CLEAN — Zero integrity violations detected (no hardcoded outputs, no facade implementations, no shortcuts, no pre-canned answer templates).  
**Regression Status**: CLEAN — 6/6 selected M1 gating regression tests passed; 67/67 unit tests passed with 0 failures.

---

## 1. Observation

### 1.1 Ingested Statutory Records
1. **`backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`**:
   - Record `tax_reassessment_section_148a_149_limitation_procedure`:
     * Line 2: Contains statutory coverage of Sections 147, 148, 148A, 149, and 151.
     * Specifies Section 148A(b) show-cause procedure requiring a reply window of not less than 7 days and up to 30 days.
     * Specifies Section 149(1)(a) normal 3-year limitation period (ended 31 March 2022 for AY 2018-19).
     * Specifies Section 149(1)(b) extended 10-year limitation period strictly requiring escaped income in the form of an asset to equal or exceed ₹50 Lakhs (₹50,00,000); explicitly notes an allegation of ₹6.5 Lakhs is below ₹50 Lakhs and thus barred by limitation.
     * Cites official portal source: `https://www.incometax.gov.in/iec/foportal/help/statutory-forms/reassessment-notice-sop`.
   - Record `tax_tds_section_206aa_inoperative_pan_refund_workflow`:
     * Line 3: Covers Section 206AA mandatory higher 20% TDS deduction on inoperative PAN.
     * Confirms employer statutory obligation under Section 200 via Challan ITNS 281 and establishes that the employer cannot adjust or refund deposited TDS via payroll.
     * Specifies employee recourse: pay ₹1,000 fee under Section 234H, link Aadhaar, await 30-day reactivation under Rule 114AAA, verify TDS in Form 26AS/AIS, and file an ITR to claim refund.
     * Cites official portal source: `https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/tds-refund-inoperative-pan`.

2. **`backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`**:
   - Replaced duplicate UTIITSL entry with record `pan_inoperative_aadhaar_linking_circular_03_2023` while preserving `pan_protean_application_troubleshooting_01`.
   - Line 2: Covers CBDT Circular 03/2023 and Rule 114AAA for reactivating inoperative PAN.
   - Details ₹1,000 late fee under Section 234H (e-Pay Tax, Challan ITNS 280, Major Head 0021, Minor Head 500).
   - Details 30-day reactivation timeline following linking submission.
   - Preserves total PAN dataset count at 244 records, preventing regressions in `test_rag_retriever.py:52`.
   - Cites official portal source: `https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-03/Circular_No_03_2023.pdf`.

3. **`backend/data/rag_manifest.json`**:
   - Lines 576, 581: Added `"incometax.gov.in"` and `"www.incometax.gov.in"` to `allowed_hosts` in `troubleshooting_pan`, satisfying corpus provenance validation in `load_corpus()`.

### 1.2 Routing, Retrieval & Runtime Architecture
1. **`backend/modules/domain_router.py`**:
   - Lines 105-106: Added regex patterns for Sections 147, 148, 148A, 149, 151, 148A(b), 148A(d), 206AA, 234H, Rule 114AAA, Circular 03/2023, "reassessment", "escaped income", "time-barred", "limitation period".
   - Lines 203-211: In `get_allowed_rag_categories`, implemented dual-category cross-retrieval returning `{"tax", "pan", "civic"}` for queries involving inoperative PAN and salary/TDS/refund in `Domain.TAXATION` or `Domain.IDENTITY`.
   - Line 196: Uncovered domain check (`domain in (Domain.UNCOVERED, "uncovered") -> return set()`) is strictly evaluated before query-based dual category resolution, preventing domain leakage into uncovered areas.

2. **`backend/rag/retriever.py`**:
   - Lines 118-124: Passes `clean_query` to `get_allowed_rag_categories` and enables `{"tax", "pan", "civic"}` cross-category searching for `is_pan_tds_query`.
   - Line 221: Added exact codes `"148a(b)"`, `"148a"`, `"148"`, `"149"`, `"147"`, `"151"`, `"206aa"`, `"114aaa"`, `"234h"` to `_EXACT_CODES`.
   - Lines 247-258: Added symptom clusters `tax_reassessment` (boosting reassessment terms, penalizing 139(9), 119(2)(b), defective returns, bank validation) and `inoperative_pan_tds` (boosting Circular 03/2023, 114AAA, 206AA, 234H, penalizing Protean/tin-nsdl application rejections).
   - Line 322: Conflict penalty configured to -0.40 for `tax_reassessment` and `inoperative_pan_tds`.
   - Lines 342-354: Implemented explicit sub-procedure mismatch penalties (-0.40) to prevent Section 139(9) defective return SOPs from hijacking Section 148A queries, and Protean application rejections from hijacking inoperative PAN queries.

3. **`backend/rag/runtime.py`**:
   - Lines 29-30: Added statutory terms (`148`, `148a`, `147`, `149`, `151`, `reassessment`, `escaped income`, `206aa`, `234h`, `inoperative pan`) to `_CATEGORY_TERMS["tax"]`.
   - Lines 163-181: In `retrieve_if_enabled()`, bypassed hardcoded single-category assignment (`category = None`) when `is_pan_tds` is true, enabling the retriever to search across both tax and PAN categories.

### 1.3 Independent Verification Test Execution
1. **Command 1**: `py -m pytest tests/test_case1_case2_gating_regression.py -k "corpus_existence or domain_routing or dual_category or conflict_penalties" -v`
   - Result: `6 passed, 13 deselected, 1 warning in 110.88s`
   - Output log:
     ```
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_corpus_existence_reassessment_sections_147_to_151 PASSED [ 16%]
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_corpus_existence_inoperative_pan_tds_provisions PASSED [ 33%]
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_domain_routing_reassessment_statutory_patterns PASSED [ 50%]
     tests/test_case1_case2_gating_regression.py::TestTier1FeatureCoverage::test_tier1_domain_routing_inoperative_pan_tds_dual_category PASSED [ 66%]
     tests/test_case1_case2_gating_regression.py::TestTier3CrossFeatureCombinations::test_tier3_dual_category_retrieval_tax_and_pan PASSED [ 83%]
     tests/test_case1_case2_gating_regression.py::TestTier3CrossFeatureCombinations::test_tier3_retriever_symptom_cluster_conflict_penalties PASSED [100%]
     ```

2. **Command 2**: `py -m pytest tests/test_domain_router.py tests/test_rag_retriever.py -v`
   - Result: `67 passed, 1 warning in 419.33s`
   - Zero test failures across all domain routing, uncovered domain refusals, and retriever unit tests.

---

## 2. Logic Chain

1. **Case 1 Grounding and Anti-Hijacking**:
   - *Observation 1.1* confirms official statutory provisions for Section 148A(b) (reply window minimum 7 to 30 days) and Section 149 (normal 3-year limitation vs ₹50 Lakhs extended 10-year threshold) are present in `troubleshooting_tax.jsonl`.
   - *Observation 1.2* confirms exact statutory codes (`148a(b)`, `149`, `148`) and the `tax_reassessment` symptom cluster apply a +0.08 boost to reassessment records and a -0.40 conflict penalty to off-topic Section 139(9) defective return records.
   - *Observation 1.3* confirms `test_tier3_retriever_symptom_cluster_conflict_penalties` passed, proving Section 139(9) defective returns no longer hijack rank 1 for Case 1 queries.

2. **Case 2 Dual-Category Retrieval Grounding**:
   - *Observation 1.1* confirms `troubleshooting_pan.jsonl` contains CBDT Circular 03/2023 (Rule 114AAA, ₹1,000 fee under 234H, 30-day reactivation timeline) and `troubleshooting_tax.jsonl` contains Section 206AA (employer 20% TDS deposit, employer cannot refund via payroll, refund claimed via ITR).
   - *Observation 1.2* confirms `domain_router.py` and `runtime.py` enable dual-category access `{"tax", "pan", "civic"}` for PAN-TDS queries without locking the retriever to a single category.
   - *Observation 1.3* confirms `test_tier3_dual_category_retrieval_tax_and_pan` passed, proving both the PAN reactivation record and the TDS refund SOP are retrieved together in the top hits.

3. **Integrity and Non-Contamination Verification**:
   - *Observation 1.2* demonstrates that `domain in (Domain.UNCOVERED, "uncovered")` is evaluated first in `get_allowed_rag_categories`, strictly returning `set()` and preventing any cross-category leakage into uncovered domains.
   - *Observation 1.3* confirms all 67 domain router and retriever unit tests pass, verifying that tokenizer preservation, multilingual address expansion, and local Qdrant persistence remain completely intact.
   - Direct inspection confirms that no test assertions or canned answers are embedded in source code, and no disclaimers referencing "pre-verified guides" exist.

---

## 3. Adversarial Challenges & Stress-Testing

### Challenge 1: Uncovered Domain Leakage Risk via Query Parameter
- **Assumption Challenged**: Does passing `query=clean_query` to `get_allowed_rag_categories` allow an uncovered query mentioning "PAN" or "206AA" to bypass uncovered refusal?
- **Stress-Test**: Tested pattern ordering in `backend/modules/domain_router.py`. Line 196 strictly executes:
  ```python
  if domain in (Domain.UNCOVERED, "uncovered"):
      return set()
  ```
  Because this check occurs before `if query:`, queries classified as uncovered (e.g. MCA SPICe+, LPG, or Scholarships) will never be granted `{ "tax", "pan", "civic" }`.
- **Verdict**: PASS. No uncovered domain contamination.

### Challenge 2: Accidental Penalty on Legitimate Hybrid Documents
- **Assumption Challenged**: Does the symptom cluster conflict penalty (-0.40) mistakenly penalize an official tax document that mentions both Section 148A and Section 139(9)?
- **Stress-Test**: Inspected `backend/rag/retriever.py:321`:
  ```python
  if any(c in lowered_doc for c in sc["conflicts"]) and not has_boost:
  ```
  And line 344:
  ```python
  if any(term in lowered_doc for term in ("139(9)", "defective return", "119(2)(b)", "condonation")) and not any(term in lowered_doc for term in ("148a", "section 148a", "section 149", "reassessment")):
  ```
  Both penalty mechanisms require that the document does NOT contain the targeted boost terms. Therefore, a legitimate document referencing both sections is protected and receives the boost rather than the penalty.
- **Verdict**: PASS. Robust guard logic prevents false-positive penalties.

### Challenge 3: Preservation of Corpus Size Invariant
- **Assumption Challenged**: Does replacing the UTIITSL record violate corpus size invariants in existing tests?
- **Stress-Test**: Inspected `tests/test_rag_retriever.py:52` which asserts `pan.searched_documents in (242, 244)`. Replacing the redundant UTIITSL record with the Circular 03/2023 record maintained the exact count of 244 documents.
- **Verdict**: PASS. Verified by successful run of all 67 tests in `test_domain_router.py` and `test_rag_retriever.py`.

---

## 4. Caveats

- **Scope Boundary**: Milestone M1 covers Corpus Ingestion & Retriever Coverage. Subsequent Milestones (M2: Pre-synthesis Relevance & Confidence Gating, M3: Query Modality & Decomposition Synthesis, and M4: Full E2E Verification) are responsible for live LLM prompt execution, checklist suppression, and query decomposition. Tests invoking full live LLM synthesis (`test_tier4_case1...`, `test_tier4_case2...`) depend on M2 and M3.
- **Vector DB Dense Reindexing**: Lexical BM25 search and exact statutory code matching immediately index and retrieve the new JSONL records at rank 1. Dense vector embedding reindexing via `backend/offline/crawl_portal.py` or vector builder can be run if dense vector representation is additionally required.

---

## 5. Conclusion

Milestone M1 (Corpus Ingestion & Retriever Coverage) is implemented with genuine logic, official statutory provenance, strong anti-hijacking protections, zero regressions, and complete integrity.

**Final Verdict**: **APPROVE**

---

## 6. Verification Method

To independently reproduce the review findings:
1. Run M1 Gating Regression Tests:
   ```powershell
   py -m pytest tests/test_case1_case2_gating_regression.py -k "corpus_existence or domain_routing or dual_category or conflict_penalties" -v
   ```
   *Expected Output*: 6 passed, 13 deselected, 0 failed.
2. Run Full Domain Router & Retriever Test Suite:
   ```powershell
   py -m pytest tests/test_domain_router.py tests/test_rag_retriever.py -v
   ```
   *Expected Output*: 67 passed, 0 failed.
3. Review Source Files:
   - `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`
   - `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`
   - `backend/data/rag_manifest.json`
   - `backend/modules/domain_router.py`
   - `backend/rag/retriever.py`
   - `backend/rag/runtime.py`
