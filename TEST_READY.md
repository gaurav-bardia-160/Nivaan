# TEST_READY: Case 1, Case 2, Gating & Decomposition Regression Suite

**Published**: 2026-11-09  
**Author**: `e2e_cases_test_writer` (specialist, qa)  
**Target File**: `tests/test_case1_case2_gating_regression.py`  
**Test Runner**: `py -m pytest tests/test_case1_case2_gating_regression.py -v`  

---

## 1. Test Suite Summary

The automated regression test suite for Case 1 (Section 148A(b) reassessment notice), Case 2 (Inoperative PAN / 20% TDS refund), Pre-Synthesis Relevance & Confidence Gating, and Multi-Part Query Decomposition has been fully authored, compiled, and executed via pytest. It covers **Tiers 1 through 4** with **19 comprehensive, requirement-driven test cases**.

| Tier | Category | Test Count | Description |
|:---:|:---|:---:|:---|
| **Tier 1** | Feature Coverage (R1–R4) | 8 | Feature contracts covering Sections 147-151 corpus existence (Feature 1), Inoperative PAN / 206AA / 114AAA / Cir 03/2023 corpus existence (Feature 2), Domain router statutory pattern recognition (Feature 3), Dual-category routing for PAN-TDS queries (Feature 3), Pre-synthesis relevance & confidence gating blocking off-topic HIGH confidence (Feature 5), Query modality classification (Feature 7), Explainer 3-step checklist elimination for analytical queries (Feature 7), and Multi-part query decomposition (Feature 8). |
| **Tier 2** | Boundary & Corner Cases | 5 | ₹50 Lakhs threshold under Section 149(1)(b) distinguishing 3-year from 10-year limit (₹49.9L vs ₹50L), 3-year date boundary calculation (31 March 2022 expiry for AY 2018-19), Section 148A(b) minimum 7-day reply window boundary, Offline pytest execution without live LLM, and Adversarial zero predefined responses compliance per AGENTS.md / GEMINI.md. |
| **Tier 3** | Cross-Feature Combinations | 4 | Query decomposition with confidence gating on mixed supported/hallucinated queries, Analytical shape with multi-part synthesis answering both sub-questions without procedural checklists, Dual-category retrieval across `tax` and `pan`, and Retriever symptom cluster conflict penalties preventing token hijacking by 139(9) or Protean. |
| **Tier 4** | Real-World Application Scenarios | 2 | Verbatim end-to-end execution of Case 1 (AY 2018-19 ₹6.5L share trading notice) and Case 2 (Salary 20% TDS on inoperative PAN, Section 234H late fee, reactivation timeline and employer payroll vs ITR refund). |
| **Total** | | **19** | **Full Regression Coverage for Case 1, Case 2, Gating, and Decomposition** |

---

## 2. Baseline Verification Execution

- **Command**: `py -m pytest tests/test_case1_case2_gating_regression.py -v`
- **Result**: `14 failed, 5 passed, 1 warning in 144.61s` (Exit code: 1)
- **Status**: **READY FOR MILESTONE GATING**. The 5 passing tests confirm valid baseline behaviors (dual-category category resolution, zero predefined responses compliance, rejection of unsupported quantum tokens, basic dual-category retrieval access, and symptom cluster non-hijacking of rank 1). The 14 failing tests precisely establish the baseline failure state across M1, M2, and M3 to be resolved sequentially.

### Initial Baseline Test Breakdown:

| # | Test Name | Tier | Status | Root Cause in Baseline State |
|---|-----------|:----:|:------:|------------------------------|
| 1 | `test_tier1_corpus_existence_reassessment_sections_147_to_151` | 1 | **FAILED** | Statutory Sections 147-151 missing from `troubleshooting_tax.jsonl` & manifest (M1) |
| 2 | `test_tier1_corpus_existence_inoperative_pan_tds_provisions` | 1 | **FAILED** | Rule 114AAA, Cir 03/2023, Sec 206AA missing from `troubleshooting_pan.jsonl` (M1) |
| 3 | `test_tier1_domain_routing_reassessment_statutory_patterns` | 1 | **FAILED** | Section numbers 148A, 149, 151 missing from `_DOMAIN_PATTERNS[Domain.TAXATION]` (M1) |
| 4 | `test_tier1_domain_routing_inoperative_pan_tds_dual_category` | 1 | **PASSED** | Query maps to IDENTITY/TAXATION and returns valid allowed categories |
| 5 | `test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic` | 1 | **FAILED** | `compute_rag_confidence` lacks `query` parameter; off-topic 119(2)(b) chunk scores high (M2) |
| 6 | `test_tier1_query_modality_classification_analytical_vs_procedural` | 1 | **FAILED** | `classify_query_modality` not yet implemented in codebase (M3) |
| 7 | `test_tier1_explainer_checklist_elimination_for_analytical_queries` | 1 | **FAILED** | `explainer.py:352-361` unconditionally injects 3-step checklist for analytical queries (M3) |
| 8 | `test_tier1_query_decomposition_isolates_subquestions` | 1 | **FAILED** | `decompose_query` not yet implemented in retriever/decomposition module (M3) |
| 9 | `test_tier2_boundary_section_149_50_lakhs_threshold` | 2 | **FAILED** | Unimplemented statutory calculation in pipeline responses (M1/M3) |
| 10 | `test_tier2_boundary_3_year_limitation_date_calculation` | 2 | **FAILED** | Expiry date 31 March 2022 not calculated or synthesized (M1/M3) |
| 11 | `test_tier2_boundary_section_148a_minimum_7_day_reply_window` | 2 | **FAILED** | Minimum 7-day window under 148A(b) not stated (M1/M3) |
| 12 | `test_tier2_offline_pytest_execution_without_live_llm` | 2 | **FAILED** | Explainer leaks procedural review steps into offline test mode (M3) |
| 13 | `test_tier2_adversarial_zero_predefined_responses_compliance` | 2 | **PASSED** | Output adheres to Zero Predefined Responses directive |
| 14 | `test_tier3_decomposition_with_confidence_gating` | 3 | **PASSED** | Hallucinated crypto query does not receive HIGH confidence badge |
| 15 | `test_tier3_analytical_shape_with_multipart_synthesis` | 3 | **FAILED** | Output has procedural steps and omits complete answers to both sub-questions (M3) |
| 16 | `test_tier3_dual_category_retrieval_tax_and_pan` | 3 | **PASSED** | Retriever accesses both PAN and TAX categories |
| 17 | `test_tier3_retriever_symptom_cluster_conflict_penalties` | 3 | **PASSED** | Retriever ranking does not allow 139(9) or Protean to hijack rank 1 |
| 18 | `test_tier4_case1_verbatim_reassessment_section_148a_end_to_end` | 4 | **FAILED** | Steps not empty; Sec 149 limitation and 148A(b) reply window missing (M1-M4) |
| 19 | `test_tier4_case2_verbatim_inoperative_pan_tds_refund_end_to_end` | 4 | **FAILED** | Steps not empty; 30-day reactivation and Sec 206AA ITR refund missing (M1-M4) |

---

## 3. Milestone Failure Mapping & Implementation Directives

Each milestone must turn its assigned test failures from `FAILED` to `PASSED`:

### Milestone M1: Corpus Ingestion & Retriever Coverage (Features 1, 2, 3, 4)
Target files: `backend/data/rag_manifest.json`, `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`, `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`, `backend/modules/domain_router.py`, `backend/rag/retriever.py`, `backend/rag/runtime.py`.
- **Target Tests to Turn Green**:
  - `test_tier1_corpus_existence_reassessment_sections_147_to_151`
  - `test_tier1_corpus_existence_inoperative_pan_tds_provisions`
  - `test_tier1_domain_routing_reassessment_statutory_patterns`

### Milestone M2: Pre-Synthesis Relevance & Confidence Gating (Features 5, 6)
Target files: `backend/web_search/confidence.py`, `backend/pipeline.py`, `backend/modules/explainer.py`.
- **Target Tests to Turn Green**:
  - `test_tier1_relevance_confidence_gating_blocks_high_confidence_on_offtopic`

### Milestone M3: Response Shape & Multi-Part Query Decomposition (Features 7, 8)
Target files: `backend/modules/explainer.py`, `backend/modules/llm.py`, `backend/rag/retriever.py` (or `query_decomposer.py`), `backend/web_search/synthesizer.py`.
- **Target Tests to Turn Green**:
  - `test_tier1_query_modality_classification_analytical_vs_procedural`
  - `test_tier1_explainer_checklist_elimination_for_analytical_queries`
  - `test_tier1_query_decomposition_isolates_subquestions`
  - `test_tier2_offline_pytest_execution_without_live_llm`
  - `test_tier3_analytical_shape_with_multipart_synthesis`

### Milestone M4: Full Regression Verification (Features 9, 10)
Target files: Full pipeline end-to-end integration.
- **Target Tests to Turn Green**:
  - `test_tier2_boundary_section_149_50_lakhs_threshold`
  - `test_tier2_boundary_3_year_limitation_date_calculation`
  - `test_tier2_boundary_section_148a_minimum_7_day_reply_window`
  - `test_tier4_case1_verbatim_reassessment_section_148a_end_to_end`
  - `test_tier4_case2_verbatim_inoperative_pan_tds_refund_end_to_end`

---

## 4. Final Verification Command

Upon completion of Milestones M1 through M4, run:
```powershell
py -m pytest tests/test_case1_case2_gating_regression.py -v
```
**Success Threshold**: `19 passed, 0 failed in < 180s` (Exit code: 0).
