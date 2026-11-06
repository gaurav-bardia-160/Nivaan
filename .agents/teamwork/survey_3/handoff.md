# Survey 3 Handoff Report: Test Suite, Confidence Badge Decoupling, LLM Synthesis Guardrails, and AGENTS.md

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Test Harness | Pytest Runner & Suite | Repository test harness running 163 tests via `py -m pytest` with `pyproject.toml` configuration (`testpaths = ["tests"]`, `python_files = ["test_*.py"]`). | Test invocation command | 156 passed, 7 failed out of 163 tests | Exit code 1 when test assertions fail | `pyproject.toml:47-51`, `tests/` directory |
| 2 | Test Batch | Scenes 1-3 Conversations | Canonical production failure batch from Nov 2026 recorded as JSON conversation histories in `backend/data/conversations/`. | User queries in JSON turns | Assistant answers, source URLs, titles | Recorded failure responses including hallucination, bleed, DOM noise | `backend/data/conversations/chat_1793792993115_k2y6f.json`, `chat_1793793767437_wbeu6.json`, `chat_1793794139711_p0bhr.json` |
| 3 | Confidence | RRF & Cosine Score Thresholding | Mathematical confidence score calculation based on top hit score in `backend/modules/explainer.py` (`score >= 0.05 -> high`, `>= 0.02 -> medium`, `< 0.02 -> low`) and `backend/web_search/confidence.py` (`top_score / 0.040`). | `RetrievalResult.hits[0].score` (RRF fused score combining Qdrant cosine distance rank & BM25 rank) | Normalized confidence float `[0.0, 1.0]` and categorical string badge (`"low" \| "medium" \| "high"`) | Irrelevant queries with accidental keyword or vector matches receive undeserved "medium" or "high" confidence badges | `backend/modules/explainer.py:364-366`, `backend/web_search/confidence.py:23-52`, `backend/rag/vector_store.py:94` |
| 4 | Confidence Decoupling | Post-Retrieval Relevance Gate | Semantic evaluation mechanism (`MATCH`, `PARTIAL`, `NO_MATCH`) required by R3 to decouple confidence badges from raw cosine similarity. | `(query, query_domain, retrieved_chunks)` | Categorical relevance verdict (`MATCH`, `PARTIAL`, `NO_MATCH`) | `NO_MATCH` overrides score to `"low"` or triggers refusal; `PARTIAL` sets `"medium"`/`"low"`; `MATCH` allows `"high"` | `ORIGINAL_REQUEST.md:18-20` (R3), `backend/pipeline.py:590-605` |
| 5 | LLM Synthesis | Prompt Directives & Relevance Gate | System instructions and strict grounding directives in `_build_llm_prompt()` in `backend/modules/llm.py` controlling LLM output generation. | Citizen query, verified evidence, conversation context | JSON payload with `summary`, `documents_needed`, `steps` | Triggers refusal string `"Insufficient data in the verified civic knowledge base for this specific portal."` if mismatched | `backend/modules/llm.py:249-321` |
| 6 | LLM Guardrails | Anti-Hallucination of Unstated Facts | Specific prompt directive required by R4 prohibiting assumption of unstated citizen premises (e.g., asserting an employer is closed or non-operational when not stated). | Citizen prompt + conditional evidence | Strictly conditioned advice or honest refusal | Prevents fabricating false premises like assuming establishment is closed | `ORIGINAL_REQUEST.md:21-23` (R4), `backend/modules/llm.py:300-309` |
| 7 | System Directives | AGENTS.md & GEMINI.md Directives | High-level behavioral rules loaded into all agent contexts. Currently defines Zero Predefined Responses; needs R1-R6 operational guardrails per R7. | Agent prompt context | Agent behavioral adherence | Agent violates project standards if directives are missing | `AGENTS.md:1-11`, `GEMINI.md:1-11` |

---

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Closed Establishment Assumption (Scene 1 Turn 1) | "When uploading my joint declaration form on the EPFO member portal, it gives error 'DSC not registered or active for the establishment'. My employer says their digital signature is valid. What exact setting or utility is missing on their system?" | LLM assumed and fabricated that the establishment is closed ("due to the establishment being closed or non-operational... Request the employer to provide the necessary documentation to prove that the establishment is closed"), directly contradicting the user's stated fact that their employer is active and has a valid DSC. |
| 2 | Uncovered Domain Bleed: SPICe+ MCA to EPFO (Scene 1 Turn 3) | "My company name reservation SPICe+ Part A form was rejected with resubmission remark 'Proposed name resembles an existing LLP under Rule 8A'. What is the exact turnaround time to resubmit before the fee lapses?" | Nearest-neighbor vector retrieval retrieved EPFO Passbook and Cheque Leaf standards, synthesizing instructions about cancelled cheques and bank KYC for an MCA corporate name reservation query. |
| 3 | Uncovered Domain Bleed: NSP Scholarship to Income Tax 139(9) (Scene 2 Turn 1) | "NSP scholarship application status is showing 'Defective by Institute'. My college clerk says they cannot see any edit button on their login. What is the official SOP to enable re-verification?" | Keyword "Defective" caused vector/lexical retrieval to bleed into Income Tax Section 139(9) Defective Return notices, synthesizing ITR e-proceedings instructions for a student scholarship issue. |
| 4 | Same-Domain Sub-Procedure Conflation: AIS SFT vs 139(9) (Scene 2 Turn 2) | "I received an SMS about 'Significant Financial Transaction (SFT)' mismatch in AIS for mutual fund sales. Where do I submit an online explanation, and what feedback category should I choose if the broker reported gross sales twice?" | Retrieval failed to discriminate between AIS feedback and Defective Return notices within the Income Tax domain, routing the user to Section 139(9) defective return memo rectification rather than AIS feedback portal. |
| 5 | Uncovered Domain Bleed: MoPNG LPG Subsidy to EPFiGMS (Scene 3 Turn 1) | "My LPG subsidy was stopped because my bank account became dormant. I reactivated the account and seeded it at the branch 2 months ago, but subsidy is still not coming. Which portal or officer do I escalate to under the MoPNG grievance matrix?" | Retrieval matched EPFiGMS (EPFO), and LLM hallucinated a false justification ("To escalate your issue under the MoPNG grievance matrix, you should contact the EPFiGMS... portal. This is the most relevant portal for your LPG subsidy issue as it deals with stuck claims"). |
| 6 | Scraper DOM Noise in CRAG Fallback (Scene 3 Turn 2) | "My senior citizen parent passed away without a nomination registered on their Post Office MIS account. The balance is ₹3.5 Lakhs. What legal paperwork is required under the latest Department of Posts rules to claim the funds without a succession certificate" | CRAG web search scraped `https://www.indiapost.gov.in/documents/actsandpolicies` using `trafilatura.extract(..., include_tables=True)`. Fallback synthesized raw table markup containing Aadhaar pdfs, leasing policy pdfs, and act compilations. |
| 7 | Cosine Similarity False Confidence Badge | Query containing generic legal or procedural words (e.g. "subsidy", "locked", "defective") against unrelated documents. | Raw cosine similarity and RRF fusion generate a top hit score > 0.040, awarding a "high" or "medium" confidence badge to an irrelevant or cross-domain bleed answer. |

---

## 1. Observation

### 1.1 Existing Tests and Test Runner Scripts
- **Test Runner**:
  - `py -m pytest` executes the test suite on Windows Python 3.12.3 (pytest 9.1.1).
  - Configured in `pyproject.toml:47-51`:
    ```toml
    [tool.pytest.ini_options]
    testpaths = ["tests"]
    python_files = ["test_*.py"]
    python_functions = ["test_*"]
    ```
- **Test Files**:
  - `tests/test_api.py` (915 lines): Core API endpoints (`/api/ask`, `/api/ask/file`, `/api/ask/stream`), diagnostic workflows, troubleshooting boost, PII masking, rate limiting, and legacy scenarios (`test_scenario1_income_tax_bank_validation_prevents_defective_return_hallucination` and `test_scenario2_aadhaar_pvc_no_srn_provides_exact_tat_and_escalation`).
  - `tests/test_web_search.py` (363 lines): CRAG allowlist filtering, domain query generation, `compute_rag_confidence`, deep link prioritization, and discriminator loop.
  - `tests/test_local_ai.py` (260 lines): Local LLM grounding checks (`_is_grounded`), Ollama inference, and conversation memory redaction.
  - `tests/test_rag_retriever.py` (143 lines): BM25 lexical search, hybrid fusion, category filtering, and address expansion.
  - `tests/test_rag_loader.py` (141 lines): Manifest loading and corpus normalization.
  - `tests/test_build_vector_db.py` (158 lines): Qdrant vector index generation and metadata inspection.
  - `tests/test_ingest_official_source.py` (386 lines): Web scraping contracts and validation.
  - `tests/test_ocr_and_local_privacy.py` (124 lines): RapidOCR/Tesseract engine and PII masking.
  - `tests/test_refiner.py` (142 lines): Markdown cleaning, UIDAI boilerplate stripping, and chunking.
  - `tests/test_streaming.py` (112 lines): SSE event streaming.
  - `tests/test_translation.py` (137 lines): Indic translation and language policy.
  - `tests/test_vector_readiness.py` (86 lines): Vector index integrity checks.
  - `tests/eval_retrieval.py` (249 lines): Retrieval and safety evaluation benchmark runner.
- **Current Test Suite Execution Status**:
  - Command: `py -m pytest`
  - Output: `156 passed, 7 failed in 136.60s`.
  - The 7 failures stem from:
    1. `tests/test_api.py::test_ask_endpoint_supported_question_uses_real_backend_boundary`: Query "What should I check in a loan agreement?" retrieved MUDRA yojana instead of loan agreement due to removal of canned knowledge entries in commit `f0847ef`.
    2. `tests/test_build_vector_db.py::test_build_unified_vector_db_uses_canonical_loader`: Asserted 1,354 documents; corpus now has 1,387 documents.
    3. `tests/test_local_ai.py::test_pipeline_uses_redacted_backend_memory_for_follow_up`: Expected `first.entry_id == "pan_card_new"`; now `entry_id` is None due to dynamic RAG.
    4. `tests/test_local_ai.py::test_conversation_delete_endpoint_clears_backend_memory`: Same `entry_id` expectation.
    5. `tests/test_rag_loader.py::test_loader_default_repo_corpus_counts_are_explicit`: Corpus counts changed.
    6. `tests/test_streaming.py::test_ask_stream_verified_query`: Same `entry_id` expectation.
    7. `tests/test_translation.py::test_pipeline_recognizes_aadhar_spelling_and_natural_language`: Title was generic FAQ chunk instead of Aadhaar.
  - **Pytest Live LLM Bypass**: Line 838 of `backend/modules/llm.py`:
    ```python
    if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("TEST_LIVE_LLM"):
        return answer
    ```
    Pytest bypasses local LLM generation by default unless `TEST_LIVE_LLM=1` or direct synthesis methods are invoked.

### 1.2 Scenes 1-3 Test Batch Identification
Located in `backend/data/conversations/`:
1. **Scene 1**: `chat_1793792993115_k2y6f.json`
   - Turn 1: EPFO Joint Declaration DSC error: `"When uploading my joint declaration form on the EPFO member portal, it gives error 'DSC not registered or active for the establishment'. My employer says their digital signature is valid. What exact setting or utility is missing on their system?"`
     - Retrieved: `epfo_closed_establishment_attestation_01` ("EPFO Attestation Framework for Closed Establishments and Untraceable Employers", `https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/09/100.pdf`).
     - LLM Synthesis: `"The error 'DSC not registered or active for the establishment' suggests that the EPFO member portal is unable to proceed with the digital signature verification due to the establishment being closed or non-operational... Request the employer to provide the necessary documentation to prove that the establishment is closed or non-operational."`
     - Failure: Hallucinated that the establishment is closed, directly contradicting the citizen who stated their employer is active. (R1, R3, R4)
   - Turn 2: Sarathi driving license payment lock: `"I booked my driving license slot on Sarathi, but the payment failed midway. Now when I try to pay again, it says 'Application is locked under pending transaction'. How do I break this lock without waiting 72 hours?"`
     - Output: `"No verified guide found"` (honest refusal).
   - Turn 3: SPICe+ Part A MCA company name reservation: `"My company name reservation SPICe+ Part A form was rejected with resubmission remark 'Proposed name resembles an existing LLP under Rule 8A'. What is the exact turnaround time to resubmit before the fee lapses?"`
     - Retrieved: `epfo_claim_passbook_cheque_standards_01` ("EPFO Passbook and Cheque Leaf Validation Standards for Form 19 and 31 Claims", `https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/08/Manual_for_Inspector_cum_Facilitator.pdf`).
     - LLM Synthesis: Detailed cancelled cheque and bank passbook KYC instructions for a corporate name reservation query.
     - Failure: Cross-domain bleed from uncovered domain (MCA / SPICe+) into EPFO. (R2)

2. **Scene 2**: `chat_1793793767437_wbeu6.json`
   - Turn 1: NSP scholarship defective application: `"y NSP scholarship application status is showing 'Defective by Institute'. My college clerk says they cannot see any edit button on their login. What is the official SOP to enable re-verification?"`
     - Retrieved: `spider_www.incometax.gov.in_54df54d2_chunk_4.json` ("Income Tax User Manual on Responding to Section 139(9) Defective Return Notices", `https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/prima%20facie%20adjustment`).
     - LLM Synthesis: `"Section 139(9) Defective Return Notice Rectification: The Centralized Processing Center (CPC 2.0) issues an intimation under Section 139(9)... Log in to incometax.gov.in with PAN..."`
     - Failure: Cross-domain bleed from uncovered domain (NSP scholarship) into Income Tax defective returns due to the word "Defective". (R2, R4)
   - Turn 2: AIS SFT mismatch mutual fund sales: `"I received an SMS about 'Significant Financial Transaction (SFT)' mismatch in AIS for mutual fund sales. Where do I submit an online explanation, and what feedback category should I choose if the broker reported gross sales twice?"`
     - Retrieved: Re-matched Section 139(9) Defective Return Notices.
     - LLM Synthesis: Instructed user on Section 139(9) defective return memos instead of AIS feedback navigation.
     - Failure: Same-domain sub-procedure conflation: failed to discriminate between AIS feedback and Section 139(9) within the `tax` domain. (R6)

3. **Scene 3**: `chat_1793794139711_p0bhr.json`
   - Turn 1: LPG subsidy dormant account MoPNG grievance: `"My LPG subsidy was stopped because my bank account became dormant. I reactivated the account and seeded it at the branch 2 months ago, but subsidy is still not coming. Which portal or officer do I escalate to under the MoPNG grievance matrix?"`
     - Retrieved: `epfo_epfigms_grievance_sop_01` ("EPFiGMS Grievance Registration and Field Office Escalation Matrix for Stuck EPF Claims", `https://epfigms.gov.in`).
     - LLM Synthesis: `"To escalate your issue under the MoPNG grievance matrix, you should contact the EPFiGMS... portal. This is the most relevant portal for your LPG subsidy issue as it deals with stuck claims, which aligns with your situation of subsidy not coming after reactivating your bank account."`
     - Failure: Cross-domain bleed from uncovered domain (MoPNG / LPG subsidy) into EPFO; hallucinated that EPFiGMS handles LPG subsidies. (R2, R4)
   - Turn 2: Post Office MIS claim without nomination: `"My senior citizen parent passed away without a nomination registered on their Post Office MIS account. The balance is ₹3.5 Lakhs. What legal paperwork is required under the latest Department of Posts rules to claim the funds without a succession certificate"`
     - Retrieved: CRAG web search fallback fetched `https://www.indiapost.gov.in/documents/actsandpolicies`.
     - Output: `"| List of Acceptable Documents for Aadhaar Enrolment and Update Language: English Version | 11-06-2026 | Format: PDFSize: 838.3 KB | | | Long term leasing policy for hiring accommodation for office purpose in Department of Posts Language: English Version | 03-06-2026 | Format: PDFSize: 11 MB | | | Compilation of Post Office Act, Rules and Regulations."`
     - Failure: Scraper DOM noise in CRAG fallback path; raw HTML table containing document download links returned as user answer. (R5)

### 1.3 Confidence Calculation & Cosine Similarity in the Codebase
- **Qdrant Vector Store Metric**: In `backend/rag/vector_store.py:94`:
  ```python
  self._client.create_collection(
      collection_name=self.collection,
      vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
  )
  ```
  Vectors are compared using Cosine similarity.
- **RRF Fusion in Retriever**: In `backend/rag/retriever.py:117-153`:
  ```python
  signals["vector_score"] = hit.score  # Cosine similarity
  signals["vector_rrf"] = 1 / (self.config.rrf_k + rank)
  score = signals.get("lexical_rrf", 0.0) + signals.get("vector_rrf", 0.0) + min(metadata_overlap, 1.0) * 0.01
  ```
- **Explainer Confidence Badge Assignment**: In `backend/modules/explainer.py:364-366`:
  ```python
  top_score = result.hits[0].score
  calc_conf = "high" if top_score >= 0.05 else ("medium" if top_score >= 0.02 else "low")
  ```
- **Web Search Confidence Gate**: In `backend/web_search/confidence.py:50`:
  ```python
  normalized = min(top_score / _RRF_HIGH_CONFIDENCE_FLOOR, 1.0)  # _RRF_HIGH_CONFIDENCE_FLOOR = 0.040
  ```
- **Pipeline Dynamic Confidence**: In `backend/pipeline.py:968-975`:
  ```python
  score_conf = compute_rag_confidence(rag_result)
  dynamic_conf = "high" if score_conf >= 0.80 else ("medium" if score_conf >= 0.40 else "low")
  ```

### 1.4 LLM Synthesis Prompt Directives in `backend/modules/llm.py`
- Prompt is constructed in `_build_llm_prompt(question, answer, memory)` at lines 249-320.
- Current Relevance Guardrail (lines 301-304):
  ```python
  "- RELEVANCE GUARDRAIL DIRECTIVE: Critically evaluate the retrieved documents against the user's prompt. "
  "If the documents do not explicitly mention the specific government portal, scheme, or error code queried by the user "
  "(e.g., retrieving Income Tax documents for a FASTag query), you MUST NOT output a step-by-step procedure. "
  "Instead, output: 'Insufficient data in the verified civic knowledge base for this specific portal.' and stop generating.\n"
  ```
- Current Refusal Interception (lines 468-473 and 775-784):
  ```python
  is_refusal = (
      "does not contain the specific procedure for this issue" in summary_candidate.lower()
      or "verified knowledge base does not contain" in summary_candidate.lower()
      or "insufficient data in the verified civic knowledge base" in summary_candidate.lower()
      or "does not explicitly mention the specific government portal" in summary_candidate.lower()
  )
  if is_refusal:
      from backend.modules.explainer import not_found_answer
      return not_found_answer(question)
  ```
- **Gap in Directive**: Does not forbid fabricating unstated factual premises (such as assuming an employer/establishment is closed when the user explicitly said the employer is valid and active).

### 1.5 Current Directives in `AGENTS.md` and `GEMINI.md`
- Total Lines: 11
- Current Rule:
  ```markdown
  # Nivaan - Project Core Directives & Memory

  ## Rule: Zero Predefined Responses
  - **NEVER use or re-introduce predefined, hardcoded, or pre-canned responses.**
  - All user-facing procedural answers, steps, document lists, and summaries must be dynamically generated from:
    1. Dense vector and lexical RAG retrieval against official canonical government documents.
    2. Live Corrective RAG (CRAG) web search on allowlisted official portals (parivahan.gov.in, incometax.gov.in, uidai.gov.in, passportindia.gov.in, epfindia.gov.in, etc.).
    3. Dynamic local LLM synthesis over the retrieved passages.
  - Never output disclaimers referencing "pre-verified guides" or "predefined responses".
  - If neither RAG nor live search has evidence to answer a question, provide an honest, ungrounded refusal rather than falling back to a pre-canned answer template.
  ```

---

## 2. Logic Chain

1. **Root Cause of Retrieval Bleed (R2)**:
   - When a citizen asks about an uncovered domain (MCA / SPICe+, MoPNG / Petroleum & LPG subsidies, NSP / National Scholarship Portal), `backend/modules/domain_router.py:classify_domain()` evaluates the input against patterns for `TRANSPORT`, `EDUCATION`, `IDENTITY`, `TAXATION`, `BANKING`, `AGRICULTURE`, `LEGAL_CONSUMER`.
   - None of those patterns match MCA/SPICe+ or MoPNG, returning `Domain.UNKNOWN`.
   - In `get_allowed_rag_categories(Domain.UNKNOWN)`, the function returns `None` (unfiltered).
   - In `backend/rag/retriever.py`, an unfiltered search passes the query to both BM25 and Qdrant. Because dense vector retrieval maps all queries into semantic embedding space, nearest-neighbor vector search ALWAYS returns top-k documents (e.g., matching words like "resubmission", "Rule", "defective", "subsidy", "bank account", "dormant").
   - Nearest-neighbor documents from completely unrelated domains (EPFO, Income Tax) are returned with non-zero scores, causing retrieval bleed.

2. **Root Cause of Misleading Confidence Badges (R3)**:
   - In `backend/modules/explainer.py:364-366` and `backend/web_search/confidence.py:50`, confidence is computed strictly by formula:
     `calc_conf = "high" if top_score >= 0.05 else ("medium" if top_score >= 0.02 else "low")`
   - Even when the top document is from a completely wrong domain, the rank 1 RRF score is typically ~0.030 to 0.060.
   - Consequently, the system marks completely wrong answers with a `medium` or `high` confidence badge.
   - Decoupling requires a post-retrieval semantic relevance verification step evaluating the retrieved chunk into `MATCH`, `PARTIAL`, or `NO_MATCH`:
     - `MATCH`: Exact domain and procedure match -> confidence `high`.
     - `PARTIAL`: Same domain/topic but incomplete sub-procedure details -> confidence `medium`/`low` with qualification.
     - `NO_MATCH`: Mismatched domain, portal, or entity -> confidence clamped to `low` or short-circuiting to `not_found_answer`.

3. **Root Cause of Unstated Fact Fabrication (R4)**:
   - In Scene 1 Turn 1, the user asks about an active employer DSC error on EPFO. The corpus only contained a document about "Attestation Framework for Closed Establishments".
   - The LLM synthesis prompt lacked an explicit instruction forbidding the assumption of unstated conditional premises.
   - The LLM rationalized that because the document applies to closed establishments, the citizen's employer must be closed, advising the citizen to prove the establishment is closed.
   - To fix this, `backend/modules/llm.py` must contain a directive:
     *Never fabricate or assume unstated factual premises about the citizen's situation (e.g. never assume an establishment is closed or untraceable unless explicitly stated). If a retrieved document's prerequisite conditions do not match the citizen's stated facts, state clearly that the document applies only to that specific condition and refuse to invent procedural advice.*

4. **Root Cause of Same-Domain Conflation (R6)**:
   - In Scene 2 Turn 2, both Section 139(9) defective returns and AIS duplicate feedback are within `tax`.
   - In `backend/rag/retriever.py`, the `_SYMPTOM_CLUSTERS` define `defective_return` and `bank_validation`, but omit an `ais_sft_feedback` cluster.
   - The term "mismatch" triggered the `_TROUBLE_TOKENS` boost, and without an explicit AIS feedback cluster, Section 139(9) dominated the ranking.
   - Discriminating sub-procedures requires symptom clusters and conflict penalties distinguishing AIS feedback from Section 139(9) defective returns.

5. **Root Cause of Scraper DOM Noise (R5)**:
   - In Scene 3 Turn 2, `backend/web_search/fetcher.py:100-106` calls `trafilatura.extract(html, include_tables=True)`.
   - When `include_tables=True` is enabled on portal index pages (like `indiapost.gov.in/documents/actsandpolicies`), table listings of downloadable PDF forms are converted to Markdown table rows.
   - If the LLM call times out or is bypassed, `_extract_extractive_answer()` in `backend/web_search/synthesizer.py` picks these table rows directly as the summary.

---

## 3. Caveats

1. **Pytest Test Bypass**:
   `backend/modules/llm.py:838` short-circuits `enhance_grounded_answer()` during `pytest` runs if `TEST_LIVE_LLM` is not set. Unit/regression tests targeting R4 prompt directives must invoke `LocalLLMClient().synthesize_grounded_answer()` or test the prompt builder directly, or run with a mock client.
2. **Local Model Availability**:
   Ollama CPU inference latency varies between 5s and 30s. Tests should mock the LLM inference boundary or test prompt formatting and post-synthesis validation filters deterministically.
3. **Corpus Counts in Existing Tests**:
   Existing tests `test_build_unified_vector_db_uses_canonical_loader` and `test_loader_default_repo_corpus_counts_are_explicit` assert specific document counts (1,354). Ingestion of authentic EPFO documents in R1 may alter these document counts, which will need updating in test assertions.

---

## 4. Conclusion

1. **Test Runner & Harness**:
   The authoritative project test runner is `py -m pytest` executing all tests in `tests/`.
2. **Scenes 1-3 Exact Failure Traces**:
   - Scene 1 Turn 1: Closed establishment assumption hallucination on active employer DSC (R1, R4).
   - Scene 1 Turn 3: SPICe+ MCA name reservation nearest-neighbor bleed into EPFO passbook rules (R2).
   - Scene 2 Turn 1: NSP scholarship application bleed into Income Tax Section 139(9) defective return (R2, R4).
   - Scene 2 Turn 2: AIS SFT mutual fund duplicate feedback misrouted to Section 139(9) (R6).
   - Scene 3 Turn 1: MoPNG LPG subsidy bleed into EPFiGMS with hallucinated justification (R2, R4).
   - Scene 3 Turn 2: Post Office MIS claim without nomination returned raw table DOM noise from indiapost.gov.in (R5).
3. **Confidence Badge Decoupling Architecture (R3)**:
   Confidence must be decoupled from raw RRF/cosine similarity by inserting a post-retrieval relevance check in `backend/modules/explainer.py` / `backend/pipeline.py`:
   - Inputs: query text, query domain, top retrieved document.
   - Check: Domain category match, entity presence (portal/agency/acronym), and symptom alignment.
   - Outputs: `MATCH` (confidence `"high"`), `PARTIAL` (confidence `"medium"` / `"low"`), `NO_MATCH` (confidence `"low"` or triggers `not_found_answer`).
4. **Relevance-Gate Prompt Directive Structure (`backend/modules/llm.py`) (R4)**:
   Add to `_build_llm_prompt()`:
   - A strict directive: "ZERO UNSTATED FACT FABRICATION: Never assume, invent, or project unstated circumstances onto the citizen's situation. For instance, if the citizen has not stated their company/employer is closed or non-operational, NEVER assume or claim it is closed. If a retrieved document applies only under a conditional prerequisite, explicitly state that condition and DO NOT instruct the user to follow that protocol unless they confirm the condition."
   - A strict domain refusal directive: "If the retrieved evidence does not match the specific government department, portal, or scheme queried, output exactly: 'Insufficient data in the verified civic knowledge base for this specific portal.'"
5. **AGENTS.md & GEMINI.md Guardrail Updates (R7)**:
   `AGENTS.md` and `GEMINI.md` must be updated to include 6 specific guardrails:
   1. Uncovered Domain Interception & Retrieval Bleed Prevention (R2).
   2. Post-Retrieval Confidence Decoupling from Cosine Similarity (R3).
   3. Relevance Gating & Zero Unstated Fact Fabrication (R4).
   4. Scraper DOM Noise Elimination in CRAG Fallback (R5).
   5. Same-Domain Sub-Procedure Granularity & Anti-Conflation (R6).
   6. Canonical Corpus Source Authenticity & Anti-Boilerplate (R1).

---

## 5. Verification Method

### 5.1 Commands to Verify Findings
1. **Verify Existing Tests and Runners**:
   ```powershell
   py -m pytest tests/test_api.py -k "test_scenario" -v
   ```
2. **Verify Scenes 1-3 Test Batch Files**:
   ```powershell
   Get-Content backend\data\conversations\chat_1793792993115_k2y6f.json | ConvertFrom-Json | Select-Object -ExpandProperty turns | Select-Object user_text, answer_title
   Get-Content backend\data\conversations\chat_1793793767437_wbeu6.json | ConvertFrom-Json | Select-Object -ExpandProperty turns | Select-Object user_text, answer_title
   Get-Content backend\data\conversations\chat_1793794139711_p0bhr.json | ConvertFrom-Json | Select-Object -ExpandProperty turns | Select-Object user_text, answer_title
   ```
3. **Verify Confidence Badge Coupling in Explainer**:
   Inspect lines 363-366 in `backend/modules/explainer.py`.
4. **Verify LLM Prompt Construction**:
   Inspect lines 285-321 in `backend/modules/llm.py`.
5. **Verify AGENTS.md Directives**:
   Inspect `AGENTS.md` and `GEMINI.md`.

### 5.2 Invalidation Conditions
- If Scenes 1-3 were defined in a different location than `backend/data/conversations/chat_1793792993115_k2y6f.json`, `chat_1793793767437_wbeu6.json`, and `chat_1793794139711_p0bhr.json`. (Invalidated: The verbatim text, timestamps, and error messages in these three conversations match every detail of Scenes 1-3 and requirements R1-R6).
- If confidence was not calculated from cosine similarity/RRF. (Invalidated: Traced directly to Qdrant `Distance.COSINE`, RRF in `RagRetriever.search()`, and `calc_conf` in `explain_rag_result()`).
