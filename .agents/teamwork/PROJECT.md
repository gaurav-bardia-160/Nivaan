# Project: Remediation of RAG and Synthesis Pipeline Architectural Gaps (Case 1 & Case 2)

## Architecture
Nivaan is a production civic assistant with a hybrid RAG pipeline:
- **Corpus Ingestion**: Canonical official government documents in JSONL (`backend/data/refined/`) registered in `backend/data/rag_manifest.json`.
- **Vector & Lexical Search**: Qdrant vector store and BM25 lexical search with Reciprocal Rank Fusion (RRF `1 / (60 + rank)`), exact code boosting, and symptom cluster conflict penalties.
- **Domain Router**: Pre-retrieval query intent classifier (`backend/modules/domain_router.py`) with cross-category routing for multi-domain civic inquiries.
- **Query Decomposition**: Multi-part query decomposer splitting compound inquiries into distinct sub-questions for balanced retrieval and complete synthesis coverage.
- **Pre-Synthesis Relevance & Confidence Gating**: Multi-factor confidence evaluation (`backend/web_search/confidence.py`) verifying semantic alignment and statutory entity support between query terms and retrieved chunks, preventing off-topic false HIGH confidence badges and triggering live CRAG web search or honest refusal.
- **Response Shape & Scaffolding**: Query modality classification separating procedural workflows from analytical, calculation, and legal-interpretation queries; suppresses artificial 3-step checklists (`backend/modules/explainer.py`, `backend/modules/llm.py`, `backend/web_search/synthesizer.py`).
- **CRAG Fallback**: Web search fallback on allowlisted government domains with clean text extraction via `trafilatura`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Corpus Ingestion: Reassessment Provisions (Sections 147-151) | Ingest official statutory text for Sections 147, 148, 148A (7-30 days reply window), 149 (3-yr vs 10-yr limitation, ₹50L threshold), and 151 into `troubleshooting_tax.jsonl` & `rag_manifest.json` | M1 | R4, Survey 1 |
| 2 | Corpus Ingestion: Inoperative PAN & TDS (206AA, 114AAA, Cir 03/2023, 234H) | Ingest official text for Rule 114AAA, CBDT Circular 03/2023 (30-day reactivation timeline, ₹1000 fee under 234H), and Section 206AA (employer 20% TDS deposit, employer cannot refund via payroll, employee refund via ITR) into `troubleshooting_pan.jsonl` / `troubleshooting_tax.jsonl` | M1 | R4, Survey 2 |
| 3 | Domain Router Expansion & Cross-Category Access | Add statutory patterns (147-151, 206AA, 234H, reassessment, inoperative PAN) to `domain_router.py`; allow dual-category search (`tax` + `pan`) for PAN-TDS queries | M1 | R4, Survey 1, 2 |
| 4 | Retriever Symptom Clusters & Anti-Hijacking | Add `tax_reassessment` and `inoperative_pan_tds` symptom clusters and exact code matching in `retriever.py` to prevent token hijacking by 139(9) or Protean rejections | M1 | R4, Survey 1, 2 |
| 5 | Multi-Factor Relevance & Confidence Gating | Upgrade `compute_rag_confidence(rag_result, query)` in `confidence.py` to enforce statutory entity alignment and lexical overlap, preventing false HIGH confidence badges on off-topic hits | M2 | R2, Survey 3 |
| 6 | Pre-Synthesis CRAG Triggering & Honest Refusal | Connect confidence gating to `pipeline.py` to trigger live CRAG when retrieved chunks lack semantic alignment (< 0.35) or emit honest refusal if ungrounded | M2 | R2, Survey 3 |
| 7 | Query Modality Classification & Checklist Elimination | Classify queries as PROCEDURAL vs ANALYTICAL/CALCULATION/LEGAL; eliminate artificial 3-step checklist (`steps = []`) in `explainer.py`, `llm.py`, and `synthesizer.py` for non-procedural queries | M3 | R1, Survey 3 |
| 8 | Multi-Part Query Decomposition & Synthesis | Decompose compound user queries into distinct sub-questions in `retriever.py` / `query_decomposer.py`, ensure multi-intent retrieval coverage, and synthesize direct answers to all sub-questions | M3 | R3, Survey 2, 3 |
| 9 | Automated Regression Suite (Case 1, Case 2, Gating, Decomposition) | Implement comprehensive automated regression and unit tests in `tests/` verifying Case 1, Case 2, confidence gating, and decomposition pass 100% | M4 | Acceptance Criteria |
| 10 | Independent E2E Test Suite (Tiers 1-4) | Requirement-driven opaque-box test suite covering feature inventory across Tiers 1-4 publishing `TEST_READY.md` | E2E | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | Independent E2E Testing Suite | Requirement-driven opaque-box test suite covering Tiers 1-4 publishing `TEST_READY.md` | none | IN_PROGRESS |
| M1 | Corpus Ingestion & Retriever Coverage | Features 1, 2, 3, 4: Ingest 147-151 & 206AA/114AAA/Cir 03/2023, update `domain_router.py` & `retriever.py` | none | DONE |
| M2 | Pre-Synthesis Relevance & Confidence Gating | Features 5, 6: Update `compute_rag_confidence` in `confidence.py` with entity alignment, update `explainer.py` & `pipeline.py` | M1 | DONE |
| M3 | Response Shape & Multi-Part Query Decomposition | Features 7, 8: Implement query modality classifier, eliminate 3-step checklist for analytical queries, implement query decomposition | M1, M2 | PLANNED |
| M4 | Regression Test Suite & Verification | Feature 9: Implement regression tests in `tests/test_case1_case2_gating_regression.py` covering Case 1, Case 2, gating, and decomposition; verify 100% pass | M1, M2, M3, E2E | PLANNED |

## Interface Contracts
### Domain Router & Retriever ↔ Runtime
- `classify_domain(query: str) -> Domain`:
  - Matches reassessment sections (`147`, `148`, `148A`, `149`, `151`) into `Domain.TAXATION`.
  - Matches inoperative PAN / TDS queries (`206AA`, `234H`, `salary TDS`, `inoperative PAN`) into `Domain.TAXATION` or `Domain.IDENTITY` with dual-category allowance `{"tax", "pan"}`.
- `RagRetriever.search(query, category=None, domain=None, top_k=None) -> RetrievalResult`:
  - Exact code matches for `"148a(b)"`, `"148a"`, `"149"`, `"206aa"`, `"114aaa"`, `"234h"`.
  - Cluster boost for `tax_reassessment` with conflict penalty on `139(9)`, `119(2)(b)`.
  - Cluster boost for `inoperative_pan_tds` with conflict penalty on Protean application rejections.

### Confidence Gating ↔ Pipeline & Explainer
- `compute_rag_confidence(rag_result: RetrievalResult, query: str = None) -> float`:
  - Accepts both `rag_result` and `query`.
  - Enforces statutory entity alignment: If query contains specific sections (`148A`, `149`, `206AA`, etc.) and top hit lacks matching entities, caps confidence below `0.35`.
  - Triggers live CRAG in `pipeline.py` when confidence < 0.35. If ungrounded, outputs honest refusal with `confidence="low"`.
  - In `explainer.py:365`, dynamic confidence is set to `"low"` if statutory alignment fails.

### Query Modality & Response Scaffolding
- `classify_query_modality(query: str) -> QueryModality`:
  - Returns `QueryModality.ANALYTICAL`, `CALCULATION`, `LEGAL_INTERPRETATION`, or `PROCEDURAL`.
- `explain_rag_result(result, user_question) -> Answer`:
  - For non-procedural modalities, `dynamic_steps` is strictly `[]`. Artificial checklists ("Review [Doc 1]", "Review [Doc 2]", "Verify Official Portal") are suppressed.
  - Summary directly answers the query's analytical and legal questions.
- `decompose_query(query: str) -> list[str]`:
  - Splits compound queries into distinct sub-questions for isolated retrieval and comprehensive synthesis.

## Code Layout
- `backend/data/rag_manifest.json`: Corpus manifest and metadata.
- `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`: Tax statutory provisions (147-151, 206AA refund workflow).
- `backend/data/refined/troubleshooting/troubleshooting_pan.jsonl`: PAN statutory provisions (Rule 114AAA, Circular 03/2023, 234H).
- `backend/modules/domain_router.py`: Domain patterns and cross-category allowances.
- `backend/rag/retriever.py`: Symptom clusters, exact codes, conflict penalties, and query decomposition.
- `backend/rag/runtime.py`: Runtime category resolution.
- `backend/web_search/confidence.py`: Pre-synthesis multi-factor relevance and confidence gating.
- `backend/modules/explainer.py`: Query modality classifier, checklist elimination, analytical response generation.
- `backend/modules/llm.py`: Prompt directives and post-processing step handling.
- `backend/web_search/synthesizer.py`: CRAG synthesis confidence handling without step penalties.
- `tests/`: Automated unit and regression test suite.
