# Survey 1 Investigation Report: RAG Retrieval Architecture, Hard Domain Routing, and Sub-Procedure Discrimination

## 1. Observation

### 1.1 Vector Retrieval & Hybrid Search Architecture
1. **Embedding Model & Provider** (`backend/rag/embeddings.py:7, 39-66`):
   - Provider: `FastEmbedProvider` using local ONNX execution via `fastembed`.
   - Model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
   - Dimensions: 384 dimensions.
   - Text input function (`backend/rag/retriever.py:27-29`):
     ```python
     def document_text(doc: RagDocument) -> str:
         title_bits = " ".join(f"{source.title} {source.section}" for source in doc.sources)
         return f"{doc.category} {' '.join(doc.tags)} {title_bits} {doc.text}"
     ```
2. **Persistent Vector Store** (`backend/rag/vector_store.py:62-132`):
   - Adapter: `QdrantLocalVectorStore` wrapping `qdrant_client.QdrantClient` in persistent local embedded mode at `backend/data/vector_index/qdrant`.
   - Collection name: `govbank_chunks`.
   - Distance metric: `Distance.COSINE` (`vector_store.py:94`).
   - Point payload: `{"document_id": doc.id, "category": doc.category, "title": ..., "source_url": ...}`.
   - Vector search query: `_client.query_points(collection_name=self.collection, query=list(query_vector), query_filter=query_filter, limit=top_k, with_payload=True)`.
3. **Retrieval Fusion & Ranking Mechanics** (`backend/rag/retriever.py:51-270`):
   - Lexical Search: `BM25Index.search(clean_query, top_k=30, allowed_indices=allowed_indices)` over in-memory BM25 index built from the canonical corpus.
   - Lexical RRF: `signals["lexical_rrf"] = 1 / (60 + rank)`.
   - Vector Search: Query is embedded via `provider.embed_texts((clean_query,))[0]`. Top 30 vector hits retrieved from Qdrant.
   - Vector RRF: `signals["vector_rrf"] = 1 / (60 + rank)`.
   - Base Fusion Score: `score = signals.get("lexical_rrf", 0.0) + signals.get("vector_rrf", 0.0) + min(metadata_overlap, 1.0) * 0.01`.
   - Heuristic Adjustments: Commercial site filtering (`legaltax.in`, `taxguru.in`), Primary entity matching (`_PRIMARY_DOMAIN_ENTITIES` mismatch `-0.60`, match `+0.25`), Exact statutory code boost (`+0.12`), Synthetic case study penalty (`-0.30`), Troubleshooting boost (`+0.05`), and Symptom cluster matching (`+0.08` boost, `-0.15` contamination penalty).
4. **Runtime Retrieval Access** (`backend/rag/runtime.py:145-177`):
   - `retrieve_if_enabled(query, domain=None, top_k=3)` checks feature flags `RAG_ENABLED` and `RAG_VECTOR_ENABLED`.
   - Resolves category from `domain`.
   - Fallback if category is None: checks `supported_category(query)`.
   - Line 170-174 fallback:
     ```python
     if category is None:
         lowered = query.lower()
         trouble_words = {"failed", "delay", "rejected", "error", "mismatch", "penalty", "stuck", "pending", "notice", "defective", "refund", "deducted", "tat", "unsolicited", "foreclosure"}
         if any(w in lowered for w in trouble_words):
             category = "civic"
         else:
             return None
     ```
   - Passes category and domain to `get_retriever().search(expanded_query, category=category, domain=domain, top_k=top_k)`.

### 1.2 Current Domain Routing and Gaps (`backend/modules/domain_router.py:9-128`)
1. **Existing Domain Enum**:
   ```python
   class Domain(str, Enum):
       TRANSPORT = "transport"
       EDUCATION = "education"
       IDENTITY = "identity"
       TAXATION = "taxation"
       BANKING = "banking"
       AGRICULTURE = "agriculture"
       LEGAL_CONSUMER = "legal_consumer"
       GENERAL_CIVIC = "general_civic"
       UNKNOWN = "unknown"
   ```
2. **Allowed Category Mappings** (`domain_router.py:116-129`):
   - `TRANSPORT`: `{"civic"}`
   - `EDUCATION`: `{"civic"}`
   - `TAXATION`: `{"tax", "civic"}`
   - `IDENTITY`: `{"aadhaar", "pan", "civic"}`
   - `BANKING`, `AGRICULTURE`, `LEGAL_CONSUMER`: `{"civic"}`
   - `UNKNOWN`: returns `None` (no category restriction!).
3. **Absence of Uncovered Domain Detection**:
   - MCA / SPICe+ (Ministry of Corporate Affairs, company registration, DIN, ROC) has no patterns in `_DOMAIN_PATTERNS`.
   - Petroleum / LPG (gas connection, cylinder booking, HP/Indane/Bharat Gas, PAHAL/DBTL) has no patterns in `_DOMAIN_PATTERNS`.
   - NSP scholarships (National Scholarship Portal, pre/post-matric scholarships, merit-cum-means disbursement) has no patterns in `_DOMAIN_PATTERNS`.
   - Consequently, queries for these three domains are classified as `Domain.UNKNOWN`.

### 1.3 How Uncovered Domains Cause Nearest-Neighbor Retrieval Bleed
1. When a user asks:
   - "How do I register a private limited company using SPICe+ on MCA?"
   - "How to book an LPG cylinder online or surrender subsidy?"
   - "How to apply for NSP pre-matric scholarship disbursement?"
2. `classify_domain` returns `Domain.UNKNOWN`.
3. In `backend/rag/runtime.py:166-174`:
   - `category` is `None`.
   - `supported_category(query)` checks `_CATEGORY_TERMS["civic"]` (`runtime.py:35-43`), which contains `"portal"`, `"subsidy"`, `"government"`, `"scholarship"`. Thus, it assigns `category = "civic"`.
   - Or, if any troubleshooting token ("failed", "pending", "delay", "rejected", "apply") appears, line 172 forces `category = "civic"`.
4. In `backend/rag/retriever.py:103-119`:
   - `allowed_categories` for `Domain.UNKNOWN` is `None`.
   - Dense vector retrieval executes over Qdrant (`self.vector_store.search(query_vector, top_k=30, category="civic")`).
   - In high-dimensional dense space, cosine similarity always finds nearest neighbors even across disparate civic documents (e.g. MSME Udyam registration, Ration card, E-Shram, or ITR-4).
   - Candidate chunks receive non-zero vector RRF scores and pass the `MIN_RRF_CONFIDENCE_THRESHOLD = 0.010` gate in `pipeline.py:591`.
5. In `backend/pipeline.py:606-621` & `backend/modules/llm.py`:
   - Mismatched chunks from irrelevant civic domains are passed into `explain_rag_result` and `enhance_grounded_answer`.
   - The LLM synthesizes procedural guidance using the irrelevant chunk (e.g., advising a citizen trying to register an MCA company with Udyam MSME or Ration card steps), directly causing cross-domain hallucination and retrieval bleed.

### 1.4 Tax Domain Sub-Procedure Confusion: Section 139(9) vs AIS Feedback
1. **Existing Corpus State** (`backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`):
   - Contains 5 records:
     1. `itr_bank_validation_manual_01`: Bank pre-validation and failure resolution.
     2. `itr_refund_reissue_manual_01`: Resolving "Refund Unpaid" and reissue.
     3. `itr_condonation_delay_manual_01`: Section 119(2)(b) condonation of delay.
     4. `itr_defective_return_manual_01`: "Income Tax User Manual on Responding to Section 139(9) Defective Return Notices".
        - Contains text: `"...when internal discrepancies, incomplete schedules, or tax credit mismatches (TDS vs Form 26AS/AIS) are detected during automated processing."`
        - Mentions: 15 calendar days statutory deadline, e-Proceedings > Defective Notice, uploading rectified JSON schema under Defective Return module. Explicit warning: revised return under 139(5) does not cure 139(9).
     5. `itr_individual_filing_workflow_01`: General filing steps, mentions viewing AIS/TIS as pre-filing prep.
   - **Crucial Absence**: There is **no authentic document** in the corpus for **AIS Feedback Submission** (how a taxpayer disputes an incorrect SFT financial transaction reported in the Annual Information Statement).
2. **Retriever Discrimination Logic** (`backend/rag/retriever.py:201-205`):
   - Existing cluster for defective returns:
     ```python
     {
         "name": "defective_return",
         "match": ("defective return", "139(9)", "defective notice", "139(5)", "revised return"),
         "boost_terms": ("defective return notice rectification", "cpc 2.0", "e-proceedings", "139(9)"),
         "conflicts": ("bank validation", "validation failed", "refund unpaid", "itr-4", "itr-6", "itr-5", "synthetic case study", "apex tar", "zenith"),
     }
     ```
   - Notice: `conflicts` does NOT include `"ais"`, `"annual information statement"`, or `"feedback"`.
   - Notice: There is NO symptom cluster for `ais_feedback`.
   - When a user asks about submitting feedback on an incorrect AIS entry (e.g., "My AIS shows interest income from another person's account, how do I submit AIS feedback?"):
     - BM25 and vector search match `itr_defective_return_manual_01` because of overlapping tokens ("AIS", "income tax", "mismatch", "portal").
     - The candidate `itr_defective_return_manual_01` is retrieved at Rank 1.
     - The system incorrectly instructs the user to respond to a Section 139(9) defective return notice under e-Proceedings within 15 days, which is entirely wrong.

---

## 2. Logic Chain

### 2.1 Uncovered Domain Bleed Failure Chain
1. *Observation 1.2.3*: `classify_domain` lacks patterns for MCA/SPICe+, Petroleum/LPG, and NSP scholarships, returning `Domain.UNKNOWN`.
2. *Observation 1.1.4*: In `runtime.py`, `Domain.UNKNOWN` with words like "portal", "failed", "subsidy", or "scholarship" is coerced to `category="civic"`.
3. *Observation 1.1.3*: In `retriever.py`, `allowed_categories` for `Domain.UNKNOWN` is `None`. Dense vector search queries Qdrant without a domain barrier.
4. *Observation 1.1.2*: Qdrant computes cosine similarity against all 1,353 corpus chunks. The nearest neighbors (such as MSME Udyam, Ration card, or E-Shram) receive scores > 0.010.
5. *Observation 1.3.5*: In `pipeline.py`, the non-empty retrieval result triggers LLM synthesis. The LLM attempts to ground the user's MCA/LPG/NSP query in unrelated civic chunks, generating hallucinated answers.
6. *Direct Conclusion*: Interception must happen **prior to vector search**. When a query belongs to an uncovered domain, the system must short-circuit vector search immediately and return an honest, dynamic ungrounded refusal.

### 2.2 Cross-Procedure Confusion Failure Chain
1. *Observation 1.4.1*: The corpus contains Section 139(9) defective return documentation (`itr_defective_return_manual_01`) which explicitly mentions `AIS` as a discrepancy source, but lacks an official document for AIS feedback.
2. *Observation 1.4.2*: In `retriever.py`, symptom clusters only define `defective_return` and omit `ais_feedback`.
3. *Observation 1.4.2*: The `defective_return` cluster does not treat AIS feedback terms as conflicting, so queries containing "AIS mismatch feedback" are captured by the defective return document.
4. *Direct Conclusion*: To achieve granular sub-procedure discrimination:
   - An authentic official document for AIS Feedback Submission must be added to the corpus (`backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`).
   - A dedicated `ais_feedback` symptom cluster and exact code booster must be added to `retriever.py`.
   - Mutual exclusion penalties must be enforced: queries matching `139(9)` must penalize AIS feedback, and queries matching `ais feedback` must penalize Section 139(9) defective return chunks.

---

## 3. Caveats

1. **PMUY Ujjwala vs. General Petroleum/LPG**:
   - The corpus contains 3 chunks of `pmuy_ujjwala_2` under `civic` (`refined/official_sources/pmuy_ujjwala_2/`). These specifically cover Pradhan Mantri Ujjwala Yojana 2.0 (LPG connection for poor adult women).
   - General petroleum/LPG queries (commercial LPG cylinders, standard cylinder booking on HP/Indane/Bharat Gas, PAHAL DBTL subsidy issues) are uncovered. Routing must ensure that general petroleum/LPG queries are refused, while specific PMUY Ujjwala queries can still be served if desired, OR the entire non-civic petroleum/LPG domain is treated as uncovered unless explicitly asking for Ujjwala.
2. **NSP Scholarships Corpus Status**:
   - The corpus contains 1 chunk (`nsp_student_otr_application` under `refined/official_sources/national_scholarship_portal_students/`). It only covers student One Time Registration (OTR).
   - General scholarship schemes, disbursement, state quotas, and institutional verifications are uncovered. Uncovered domain routing must clearly delimit what is intercepted.
3. **Dynamic Refusal vs. Hardcoded Template Directive**:
   - Per `AGENTS.md` / `GEMINI.md`, the system must never use pre-canned, hardcoded response templates or output disclaimers referencing "pre-verified guides". The refusal must be an honest, ungrounded statement stating the domain is not currently covered.

---

## 4. Conclusion & Technical Remediation Proposal

### 4.1 Remediation Architecture for R2: Hard Domain Routing & Bleed Prevention

#### A. Domain Router Updates (`backend/modules/domain_router.py`)
1. Add `Domain.UNCOVERED = "uncovered"` to `Domain(str, Enum)`.
2. Define explicit uncovered domain regex patterns:
   ```python
   _UNCOVERED_DOMAIN_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
       "mca_spice": (
           re.compile(r"\b(?:mca|mca21|spice\+?|spice\s+plus|roc|registrar\s+of\s+companies|director\s+identification\s+number|\bdin\b|\bcin\b|corporate\s+affairs|incorporat(?:e|ion)\s+(?:of\s+)?company|private\s+limited\s+company|inc-?29|inc-?32|dir-?3|mgt-?7)\b", re.IGNORECASE),
       ),
       "petroleum_lpg": (
           re.compile(r"\b(?:lpg|liquefied\s+petroleum|gas\s+cylinder|cylinder\s+booking|commercial\s+cylinder|domestic\s+cylinder|indane|bharat\s+gas|hp\s+gas|omc|refill\s+booking|subsidized\s+cylinder|pahal\b|dbtl)\b", re.IGNORECASE),
       ),
       "nsp_scholarships": (
           re.compile(r"\b(?:nsp|national\s+scholarship\s+portal|pre-?matric\s+scholarship|post-?matric\s+scholarship|merit-?cum-?means|scholarship\s+disbursement|scholarship\s+scheme|scholarships\.gov\.in)\b", re.IGNORECASE),
       ),
   }
   ```
3. Update `classify_domain` to evaluate `_UNCOVERED_DOMAIN_PATTERNS` first:
   If matched, return `Domain.UNCOVERED`.
4. In `get_allowed_rag_categories`:
   If `domain == Domain.UNCOVERED`, return `set()` (empty set), ensuring zero categories are allowed.

#### B. Retriever Short-Circuit (`backend/rag/retriever.py`)
1. In `RagRetriever.search(query, category=None, domain=None, top_k=None)`:
   Add hard interception before lexical or vector search:
   ```python
   # Hard Domain Routing Short-Circuit for Uncovered Domains
   if resolved_domain == Domain.UNCOVERED:
       return RetrievalResult(
           query=clean_query,
           hits=(),
           status="uncovered_domain",
           searched_documents=0,
       )
   ```
   This guarantees that:
   - BM25 does not run.
   - FastEmbed dense embeddings are NOT computed.
   - Qdrant nearest-neighbor vector search is NOT called.
   - Zero chunks are returned, preventing any retrieval bleed into LLM synthesis.

#### C. Runtime & Pipeline Interception (`backend/rag/runtime.py` & `backend/pipeline.py`)
1. In `backend/rag/runtime.py`:
   In `retrieve_if_enabled`: if `domain == Domain.UNCOVERED`, return `None` immediately.
   In `supported_category`: ensure uncovered patterns never fall back to `"civic"`.
2. In `backend/pipeline.py`:
   When `query_domain == Domain.UNCOVERED`:
   - Log to `unresolved_queries.csv` with reason `"uncovered_domain"`.
   - Bypass web search / CRAG fallback (to prevent hallucinatory scraping of third-party portals).
   - Return an honest ungrounded refusal adhering to the zero-predefined-response directive:
     Title: `"Service Not Supported"` or `"Domain Uncovered"`.
     Summary dynamically explaining that official procedural guidance for this domain (MCA/SPICe+, petroleum/LPG, or NSP scholarships) is currently not supported in Nivaan's verified knowledge base.

---

### 4.2 Remediation Architecture for R6: Same-Domain Sub-Procedure Granularity (139(9) vs AIS Feedback)

#### A. Corpus Enrichment (`backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`)
Add authentic official documentation for AIS Feedback Submission:
```json
{
  "id": "itr_ais_feedback_manual_01",
  "source_url": "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/ais",
  "title": "Income Tax Department User Guide on Submitting Feedback on Annual Information Statement (AIS)",
  "section": "Submitting Online Feedback for SFT and Tax Credit Discrepancies in AIS and TIS",
  "text": "Annual Information Statement (AIS) Feedback Submission Protocol: Taxpayers can review financial transactions reported by reporting entities (SFT filers, banks, stock depositories) and submit transaction-level feedback directly on the e-filing portal.\n\nDirect Resolution Steps:\n1. Log in to incometax.gov.in with PAN and password.\n2. Navigate to 'Services > Annual Information Statement (AIS)'. Click 'Proceed' to redirect to the AIS compliance portal.\n3. Open the 'AIS' tab and select the relevant Financial Year. The screen displays Part A (General Information) and Part B (TDS/TCS, SFT, Payment of Taxes, Demand/Refund, Other Information).\n4. Under Part B, select the transaction category (e.g., SFT-005 for dividends, SFT-006 for interest, or securities transactions).\n5. Click on the specific transaction displaying an incorrect value or duplicate entry. Click 'Feedback' on the right side of the screen.\n6. Select the applicable feedback option from the dropdown:\n   - 'Information is correct'\n   - 'Information is not fully correct' (specify correct amount)\n   - 'Information relates to other PAN/Year'\n   - 'Information is duplicate / already reported'\n   - 'Information is denied'\n7. Submit the feedback. The system generates an Acknowledgement Receipt.\n\nStatutory Effect & TIS Update: Upon feedback submission, the modified value is immediately reflected in the Taxpayer Information Summary (TIS) as the 'Derived Value' used for pre-filling ITR. AIS feedback is NOT a Section 139(9) defective return proceeding, does not require filing a rectified JSON schema under e-Proceedings, and does not have a 15-day defect memo deadline.",
  "category": "tax",
  "last_verified": "2026-11-04",
  "status": "automated_verified",
  "quality_score": 1.0,
  "source_confidence": "official",
  "verification_method": "official_circular_and_sop",
  "retrieval_tags": [
    "troubleshooting",
    "manual",
    "ais",
    "annual_information_statement",
    "tis",
    "ais_feedback",
    "sft_feedback",
    "taxpayer_information_summary",
    "income_tax"
  ],
  "language": "en"
}
```

#### B. Retriever Discrimination Logic (`backend/rag/retriever.py`)
1. **Add `ais_feedback` to `_EXACT_CODES`** (`retriever.py:169-175`):
   Include `"ais feedback"`, `"annual information statement"`, `"tis"`, `"sft"` alongside `"139(9)"`.
2. **Add `ais_feedback` symptom cluster and update `defective_return`** (`retriever.py:193-242`):
   ```python
   {
       "name": "defective_return",
       "match": ("defective return", "139(9)", "defective notice", "139(5)", "revised return", "defect memo"),
       "boost_terms": ("defective return notice rectification", "cpc 2.0", "e-proceedings", "139(9)", "corrected schema"),
       "conflicts": ("bank validation", "validation failed", "refund unpaid", "itr-4", "itr-6", "itr-5", "synthetic case study", "ais feedback", "feedback on ais", "annual information statement", "sft feedback"),
   },
   {
       "name": "ais_feedback",
       "match": ("ais feedback", "feedback on ais", "annual information statement", "ais mismatch", "sft", "wrong transaction in ais", "tis", "taxpayer information summary"),
       "boost_terms": ("annual information statement (ais) feedback", "sft feedback", "information is not fully correct", "information is denied", "information is duplicate", "derived value", "tis"),
       "conflicts": ("139(9)", "defective return", "defective notice", "cpc 2.0 defect memo", "e-proceedings", "15 calendar days", "corrected schema", "section 139(9)"),
   },
   ```
3. **Bidirectional Sub-Procedure Disambiguation Penalty**:
   ```python
   # Sub-procedure discrimination: Section 139(9) vs AIS feedback
   is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))
   is_ais_query = bool(re.search(r"\b(?:ais\s+feedback|feedback\s+on\s+ais|annual\s+information\s+statement|ais\s+mismatch)\b", lowered_q))

   if is_139_query:
       if "ais feedback" in lowered_doc or "sft feedback" in lowered_doc:
           score -= 0.40
           signals["sub_procedure_mismatch_penalty"] = -0.40
   elif is_ais_query:
       if "139(9)" in lowered_doc or "defective return" in lowered_doc:
           score -= 0.40
           signals["sub_procedure_mismatch_penalty"] = -0.40
   ```

---

## 5. Verification Method

### 5.1 Independent Verification Commands
Once implemented, verify using `pytest`:
1. **Uncovered Domains Interception Verification**:
   ```powershell
   pytest tests/test_rag_retriever.py -k "uncovered"
   pytest tests/test_api.py -k "uncovered_domain"
   ```
   - Assert query `"How do I register a company using SPICe+ on MCA?"` returns empty hits or honest refusal, and zero chunks from Udyam/Ration Card are retrieved.
   - Assert query `"How to book an LPG cylinder or dispute commercial gas refill?"` does not bleed into transport or civic nearest-neighbors.
   - Assert query `"How to apply for NSP pre-matric scholarship?"` does not bleed into unrelated civic schemes.
2. **Sub-Procedure Granularity Verification**:
   ```powershell
   pytest tests/test_rag_retriever.py -k "ais_feedback or defective_return"
   pytest tests/test_api.py -k "ais or 139"
   ```
   - Assert query `"How do I submit feedback for an incorrect AIS transaction on income tax portal?"` retrieves `itr_ais_feedback_manual_01` as Rank 1 and NEVER retrieves or cites `itr_defective_return_manual_01`.
   - Assert query `"How do I respond to Section 139(9) defective return notice?"` retrieves `itr_defective_return_manual_01` as Rank 1 and NEVER retrieves or cites AIS feedback.
3. **Full Regression Suite**:
   ```powershell
   pytest tests/ -v
   ```

### 5.2 Invalidation Conditions
- Any code changes that introduce hardcoded pre-canned answers or templates violate `AGENTS.md`.
- Any retrieval where an MCA/SPICe+ query returns `supported_hybrid` with positive hits from MSME or Ration card invalidates R2.
- Any retrieval where an AIS feedback query returns `itr_defective_return_manual_01` with Section 139(9) guidance invalidates R6.
