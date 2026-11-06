# Project: RAG Pipeline Failure Remediation (Scenes 1-3)

## Architecture
The system is a production civic assistant with a hybrid RAG pipeline:
- **Corpus Ingestion**: Canonical official government documents in JSONL (`backend/data/refined/`) registered in `backend/data/rag_manifest.json`.
- **Vector & Lexical Search**: Qdrant persistent embedded store (`govbank_chunks`) using FastEmbed multilingual MiniLM-L12 (384-dim, cosine distance) combined with BM25 lexical search via Reciprocal Rank Fusion (RRF `1 / (60 + rank)`).
- **Domain Router**: Pre-retrieval query intent classifier (`backend/modules/domain_router.py`).
- **Post-Retrieval Relevance & Confidence**: Decouples confidence badges from raw cosine similarity via semantic relevance evaluation (`MATCH`, `PARTIAL`, `NO_MATCH`).
- **LLM Synthesis**: Local Ollama / vLLM synthesis (`backend/modules/llm.py`) with strict relevance-gating and anti-hallucination directives.
- **CRAG Fallback**: Web search fallback on allowlisted government domains with clean text extraction via `trafilatura` (tables disabled).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | EPFO Corpus Verification & Source Remediation | Verify and remediate EPFO documents in `rag_manifest.json` / `troubleshooting_civic.jsonl` (ensure valid official circular URL and content) | M1 | R1, Survey 2 |
| 2 | Scraper DOM Noise Elimination in CRAG | Configure `trafilatura` in `fetcher.py` (`include_tables=False`, `favor_precision=True`) and add table detection in `synthesizer.py` | M1 | R5, Survey 2 |
| 3 | Hard Domain Routing for Uncovered Domains | Add `Domain.UNCOVERED` with regex patterns for MCA/SPICe+, petroleum/LPG, and NSP scholarships | M2 | R2, Survey 1 |
| 4 | Retriever Short-Circuit on Uncovered Domains | Pre-vector search short-circuit in `RagRetriever.search()` returning empty hits and status `uncovered_domain` without cosine bleed | M2 | R2, Survey 1 |
| 5 | Honest Refusal for Uncovered Domains | Dynamic honest ungrounded refusal adhering to `AGENTS.md` zero-predefined-response directive | M2 | R2, Survey 1, Survey 3 |
| 6 | Sub-Procedure Granularity: AIS Feedback Manual Ingestion | Add authentic official document `itr_ais_feedback_manual_01` to `troubleshooting_tax.jsonl` | M3 | R6, Survey 1 |
| 7 | Sub-Procedure Granularity: Retriever AIS vs 139(9) Discrimination | Add `ais_feedback` symptom cluster and exact code booster, with bidirectional sub-procedure conflict penalty in `retriever.py` | M3 | R6, Survey 1 |
| 8 | Post-Retrieval Confidence Decoupling | Decouple confidence badge from raw cosine similarity by evaluating retrieved context into MATCH, PARTIAL, NO_MATCH | M4 | R3, Survey 3 |
| 9 | LLM Synthesis Relevance Gating & Anti-Fabrication | Add relevance-gate directive in `backend/modules/llm.py` preventing synthesizing answers from mismatched domains or fabricating unstated facts (e.g. closed establishment) | M4 | R4, Survey 3 |
| 10 | AGENTS.md & GEMINI.md Guardrail Updates | Add operational guardrails reflecting R1-R6 failure mitigations while maintaining zero-predefined-response directive | M5 | R7, Survey 3 |
| 11 | Scenes 1-3 Regression Test Suite & Verification | Pass 100% of E2E tests (Tiers 1-4) covering Scenes 1-3 scenarios, followed by Tier 5 adversarial hardening | M6 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Corpus Integrity & Scraper Cleanup | R1 (EPFO document source fix in `troubleshooting_civic.jsonl`) & R5 (`trafilatura` DOM noise elimination in `fetcher.py`) | none | DONE |
| M2 | Hard Domain Routing & Bleed Prevention | R2 (`Domain.UNCOVERED` in `domain_router.py`, short-circuit in `retriever.py`, refusal in `runtime.py`/`pipeline.py`) | none | DONE |
| M3 | Same-Domain Sub-Procedure Granularity | R6 (`itr_ais_feedback_manual_01` in `troubleshooting_tax.jsonl`, symptom clusters & bidirectional penalty in `retriever.py`) | M1 | IN_PROGRESS |
| M4 | Confidence Decoupling & LLM Relevance Gating | R3 (MATCH/PARTIAL/NO_MATCH confidence badge) & R4 (anti-fabrication of unstated facts in `llm.py`) | M2, M3 | PLANNED |
| M5 | System Guardrail Updates | R7 (Update `AGENTS.md` and `GEMINI.md` with pipeline failure mitigations) | M1-M4 | PLANNED |
| M6 | Final Verification & Coverage Hardening | Phase 1: Pass 100% E2E test suite (Tiers 1-4); Phase 2: Adversarial coverage hardening (Tier 5) | M1-M5, TEST_READY.md | PLANNED |

## Interface Contracts
### Domain Router ↔ Retriever
- `classify_domain(query: str) -> Domain`: Returns `Domain.UNCOVERED` for queries matching MCA/SPICe+, petroleum/LPG, or NSP scholarships.
- `RagRetriever.search(query, category=None, domain=None, top_k=None) -> RetrievalResult`:
  If `resolved_domain == Domain.UNCOVERED`:
    Returns `RetrievalResult(query=clean_query, hits=(), status="uncovered_domain", searched_documents=0)`.

### Retriever ↔ Explainer / Pipeline (Confidence Decoupling)
- `evaluate_relevance(query: str, domain: Domain, top_hit: RagHit) -> RelevanceGrade`:
  Returns `MATCH`, `PARTIAL`, or `NO_MATCH`.
- `compute_rag_confidence(result: RetrievalResult, grade: RelevanceGrade) -> float`:
  Confidence badge (`high`, `medium`, `low`) is driven by `grade`:
  - `MATCH`: permits `"high"` if vector/lexical score threshold met.
  - `PARTIAL`: bounded to `"medium"` or `"low"`.
  - `NO_MATCH`: strictly forced to `"low"` / triggers ungrounded refusal.

### Retriever Sub-Procedure Discrimination (Section 139(9) vs AIS Feedback)
- In `backend/rag/retriever.py`:
  - `is_139_query`: queries matching `139(9)`, `defective return`, `defective notice`, `defect memo`.
  - `is_ais_query`: queries matching `ais feedback`, `feedback on ais`, `annual information statement`, `ais mismatch`.
  - Mutual penalty of `-0.40` applied to mismatched sub-procedure hits.

### Scraper Fetcher ↔ CRAG Synthesizer
- `fetch_page_text(url: str) -> str`: Calls `trafilatura.extract(html, include_tables=False, favor_precision=True)`.
- `is_navigation_or_boilerplate_text(text: str) -> bool`: Rejects Markdown table directory blocks and file download catalogs.

## Code Layout
- `backend/data/rag_manifest.json`: Ingested datasets and host allowlists.
- `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl`: EPFO troubleshooting records.
- `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`: Tax troubleshooting records (including AIS feedback).
- `backend/modules/domain_router.py`: Domain classification and uncovered domain regex patterns.
- `backend/rag/retriever.py`: Hybrid search, symptom clusters, sub-procedure discrimination, and short-circuit.
- `backend/rag/runtime.py`: Runtime retrieval dispatch.
- `backend/modules/explainer.py` & `backend/web_search/confidence.py`: Post-retrieval relevance and confidence badge computation.
- `backend/modules/llm.py`: Local LLM synthesis prompt directives and hallucination guardrails.
- `backend/web_search/fetcher.py` & `backend/web_search/synthesizer.py`: CRAG scraper extraction and DOM noise filtering.
- `AGENTS.md` & `GEMINI.md`: Core directives and operational guardrails.
- `tests/`: Automated unit and regression test suite.
