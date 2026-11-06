# TEST_READY: Scenes 1-3 Regression Test Suite

**Published**: 2026-11-04  
**Author**: `e2e_test_writer` (specialist, qa)  
**Target File**: `tests/test_scenes_1_to_3_regression.py`  
**Test Runner**: `py -m pytest tests/test_scenes_1_to_3_regression.py -v`  

---

## 1. Test Suite Summary

The automated regression test suite for RAG pipeline failure mitigations (Scenes 1-3, Nov 2026 batch) has been fully authored, compiled, and verified via pytest. It covers **Tiers 1 through 4** with **59 comprehensive test cases**.

| Tier | Category | Test Count | Description |
|:---:|:---|:---:|:---|
| **Tier 1** | Feature Coverage (R1–R6) | 40 | 5 tests per feature covering EPFO authenticity (R1), Hard Domain Routing for MCA/LPG/NSP (R2), Confidence Decoupling (R3), LLM Relevance Gating & Anti-Fabrication (R4), Scraper DOM Noise Elimination (R5), and Sub-Procedure Discrimination (R6). |
| **Tier 2** | Boundary & Corner Cases | 9 | Civic trouble words on uncovered vs covered domains, keyword collisions between AIS and Section 139(9), HTML table-only pages, empty/whitespace queries. |
| **Tier 3** | Cross-Feature Combinations | 4 | Domain routing + confidence decoupling, sub-procedure discrimination + confidence badge, anti-fabrication prompt + conditional chunk, CRAG DOM filter + zero predefined responses. |
| **Tier 4** | Real-World Application Scenarios | 6 | Exact reproduction of all 6 turns from the canonical Scenes 1-3 test batch (`chat_1793792993115_k2y6f`, `chat_1793793767437_wbeu6`, `chat_1793794139711_p0bhr`). |
| **Total** | | **59** | **Full Regression Coverage for Scenes 1-3** |

---

## 2. Baseline Verification Execution

- **Command**: `py -m pytest tests/test_scenes_1_to_3_regression.py -v`
- **Result**: `48 failed, 11 passed in 19.91s` (Exit code: 1)
- **Status**: **READY FOR MILESTONE GATING**. The 11 passing tests confirm existing valid contracts (manifest allowlist, JD SOP content, 100.pdf attestation circular, no PMVBRY boilerplate, zero predefined responses compliance, clean prose extraction, and valid domain boundaries). The 48 failing tests precisely capture the 48 unmitigated failure points across Scenes 1-3 to be resolved by milestones M1 through M5.

---

## 3. Milestone Failure Mapping & Implementation Directives

Each milestone must turn its assigned test failures from `FAILED` to `PASSED`:

### Milestone M1: Corpus Integrity & Scraper Cleanup (R1 & R5)
Target files: `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl`, `backend/web_search/fetcher.py`, `backend/web_search/synthesizer.py`.
- `test_tier1_r1_epfo_passbook_cheque_standards_source_validity`: Update `source_url` of `epfo_claim_passbook_cheque_standards_01` to remove reference to `Manual_for_Inspector_cum_Facilitator.pdf` and link to authentic EPFO passbook circular.
- `test_tier1_r5_trafilatura_extraction_tables_disabled`: Change `include_tables=True` to `include_tables=False` in `backend/web_search/fetcher.py`.
- `test_tier1_r5_markdown_table_rejection`: Update `is_navigation_or_boilerplate_text()` to reject markdown table rows (`| ... | ... |`).
- `test_tier1_r5_pdf_directory_catalog_rejection`: Update `is_navigation_or_boilerplate_text()` to reject file download catalogs (`Format: PDFSize:`).
- `test_tier1_r5_table_only_page_yields_empty_or_refusal`: Reject pure table pages without procedural steps.
- `test_tier3_crag_dom_filter_with_zero_predefined_responses`: Verify dynamic refusal without canned templates.
- `test_tier4_scene3_turn2_post_office_mis_claim_no_nomination`: Eliminate raw table noise on India Post claim query.

### Milestone M2: Hard Domain Routing & Bleed Prevention (R2)
Target files: `backend/modules/domain_router.py`, `backend/rag/retriever.py`, `backend/rag/runtime.py`, `backend/pipeline.py`.
- `test_tier1_r2_mca_spice_domain_classification`: Add `Domain.UNCOVERED` and regex patterns for SPICe+, MCA, MCA21, ROC, DIN, INC-29/32.
- `test_tier1_r2_mca_spice_retriever_short_circuit`: Short-circuit `RagRetriever.search()` on `Domain.UNCOVERED` returning `status="uncovered_domain"`, `hits=()`, `searched_documents=0`.
- `test_tier1_r2_mca_spice_zero_vector_bleed`: Ensure zero nearest-neighbor bleed into Udyam or EPFO passbook.
- `test_tier1_r2_mca_spice_allowed_categories_empty`: `get_allowed_rag_categories(Domain.UNCOVERED)` returns `set()`.
- `test_tier1_r2_mca_spice_honest_refusal`: Pipeline returns ungrounded honest refusal.
- `test_tier1_r2_lpg_domain_classification`: Regex patterns for LPG cylinder booking, commercial refill, Indane, Bharat Gas, HP Gas, PAHAL, DBTL, MoPNG grievance.
- `test_tier1_r2_lpg_retriever_short_circuit` & `test_tier1_r2_lpg_zero_vector_bleed_into_epfigms`.
- `test_tier1_r2_lpg_allowed_categories_empty` & `test_tier1_r2_lpg_honest_refusal`.
- `test_tier1_r2_nsp_domain_classification`: Regex patterns for NSP scholarship status, merit-cum-means, pre/post-matric.
- `test_tier1_r2_nsp_retriever_short_circuit` & `test_tier1_r2_nsp_zero_bleed_into_tax_139_9`.
- `test_tier1_r2_nsp_allowed_categories_empty` & `test_tier1_r2_nsp_honest_refusal`.
- `test_tier2_trouble_word_mca_does_not_bleed_to_civic`, `test_tier2_trouble_word_lpg_does_not_bleed_to_banking`, `test_tier2_trouble_word_nsp_does_not_bleed_to_tax`.
- `test_tier3_uncovered_domain_produces_low_confidence_refusal`.
- `test_tier4_scene1_turn3_mca_spice_name_reservation_rule_8a`, `test_tier4_scene2_turn1_nsp_defective_by_institute`, `test_tier4_scene3_turn1_lpg_subsidy_mopng_grievance`.

### Milestone M3: Same-Domain Sub-Procedure Granularity (R6)
Target files: `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`, `backend/rag/retriever.py`.
- `test_tier1_r6_ais_feedback_document_exists`: Ingest authentic official document `itr_ais_feedback_manual_01` into `troubleshooting_tax.jsonl`.
- `test_tier1_r6_ais_feedback_content_accuracy`: Ensure text contains Part B SFT categories, feedback options ("Information is duplicate / already reported"), TIS derived value update, and explicit note that AIS feedback is NOT a 139(9) defective return proceeding.
- `test_tier1_r6_retriever_exact_code_booster`: Add `"ais feedback"`, `"annual information statement"`, `"tis"`, `"sft"` to exact codes.
- `test_tier1_r6_symptom_cluster_ais_vs_139`: Define `ais_feedback` symptom cluster with conflicts on `139(9)`, and add `ais feedback` to `defective_return` conflicts.
- `test_tier1_r6_sub_procedure_bidirectional_discrimination`: Mutual penalty ensures AIS query ranks AIS document #1 and 139(9) query ranks defective return document #1.
- `test_tier2_ais_query_with_defect_keyword` & `test_tier2_139_query_with_ais_keyword`.
- `test_tier4_scene2_turn2_ais_sft_mutual_fund_duplicate`.

### Milestone M4: Post-Retrieval Confidence Decoupling & LLM Relevance Gating (R3 & R4)
Target files: `backend/modules/explainer.py`, `backend/modules/llm.py`, `backend/web_search/confidence.py`.
- `test_tier1_r3_relevance_evaluator_interface`: Implement `evaluate_relevance(query, domain, top_hit) -> RelevanceGrade` in `explainer.py`.
- `test_tier1_r3_no_match_forces_low_confidence`: `NO_MATCH` relevance forces confidence badge to `"low"` / triggers ungrounded refusal.
- `test_tier1_r3_partial_bounds_confidence`: `PARTIAL` relevance bounds confidence to `"medium"` or `"low"`.
- `test_tier1_r3_match_permits_high_confidence`: `MATCH` permits `"high"` confidence badge.
- `test_tier1_r3_decoupling_prevents_false_high_confidence`: Cross-domain nearest-neighbor hit receives `NO_MATCH` and `"low"` confidence.
- `test_tier1_r4_prompt_contains_anti_fabrication_directive`: Add anti-fabrication directive prohibiting assumption of unstated facts (e.g. assuming establishment is closed) to `_build_llm_prompt` in `backend/modules/llm.py`.
- `test_tier1_r4_prompt_contains_domain_relevance_gate`: Include domain relevance refusal directive.
- `test_tier1_r4_anti_fabrication_closed_establishment`: Prevent instructing citizen to prove establishment is closed when citizen states active employer.
- `test_tier1_r4_refusal_interception`: Intercept refusal phrases and return ungrounded `not_found_answer`.
- `test_tier3_active_employer_with_closed_est_chunk_confidence_and_prompt`.
- `test_tier4_scene1_turn1_epfo_active_employer_dsc_error`.

---

## 4. Final Milestone M6 Verification Criteria

Milestone M6 will execute:
```powershell
py -m pytest tests/test_scenes_1_to_3_regression.py -v
```
**Success Threshold**: `59 passed, 0 failed in < 30s` (Exit code: 0).
