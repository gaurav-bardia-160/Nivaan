# Handoff Report: Case 1 — Section 148A(b) Reassessment Notice (AY 2018-19)

**Author:** survey_reassess_1 (teamwork_explorer)  
**Date:** 2026-11-09T12:12:00Z  
**Status:** Hard Handoff (Investigation Complete)  
**Target Audience:** Orchestrator & Implementer Agents (R1, R2, R4)  

---

## 1. Observation

### 1.1 Complete Corpus Void on Statutory Reassessment Provisions
A search across all manifest datasets in `backend/data/rag_manifest.json` revealed that **no statutory provisions or guidance documents for Income Tax Act reassessment (Sections 147, 148, 148A, 149, 151) exist anywhere in the corpus**.

Specifically:
- **`backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`** (`lines 1–7`):
  Contains exactly 6 records:
  1. `itr_bank_validation_manual_01`: Bank Account Pre-Validation and Failure Resolution
  2. `itr_refund_reissue_manual_01`: Resolving 'Refund Unpaid' and Refund Reissue Requests
  3. `itr_condonation_delay_manual_01`: Section 119(2)(b) Condonation of Delay for Expired ITR Verification
  4. `itr_defective_return_manual_01`: Responding to Section 139(9) Defective Return Notices
  5. `itr_individual_filing_workflow_01`: Individual Taxpayer ITR Filing Workflow
  6. `itr_ais_feedback_manual_01`: Submitting Online Feedback on AIS and TIS
- **`backend/data/refined/official_sources/incometax_portal/877328334e1048279b4ea224ffa10d4c3c1a2639f0c36b1b92d3cf230d1ec436.jsonl`** (`146 lines`):
  Contains only scraped web help pages from `incometax.gov.in` covering Prima Facie Adjustment (PFA), Section 139(9) Defective Return, Bank Account pre-validation, and Service Requests.
- **`backend/data/refined/itr_synthetic/itr_chunks_clean.jsonl`**:
  Contains synthetic return filings and basic guides for ITR forms 1–6, Section 139(4) belated returns, Section 234F fees, and advance tax (Sections 234A/B/C).
- A case-insensitive ripgrep query across all files in `backend/data` for `"reassessment"` and `"148a"` returned **0 results**.

---

### 1.2 Processing of the Case 1 Query in the Existing Codebase
For the benchmark query:
> *"I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit to issue this notice expire under the 3-year vs 10-year rule, and how many days do I have to submit my reply?"*

Here is what directly occurs at each stage of the current pipeline:

#### A. Domain Routing (`backend/modules/domain_router.py`)
- `classify_domain` checks `_DOMAIN_PATTERNS[Domain.TAXATION]` (`lines 102–110`).
- Matches `"income tax"` (`re.compile(r"\b(?:income\s+tax|incometax|itr|...)\b")`) and `"assessment year"` (`re.compile(r"\b(?:...|assessment\s+year|ay\s+20\d\d)\b")`).
- Returns `Domain.TAXATION`.
- **Deficiency Observed**: Section numbers `147`, `148`, `148A`, `149`, `151` and terms `"reassessment"`, `"escaped income"`, `"time-barred"` are **completely absent** from `_DOMAIN_PATTERNS[Domain.TAXATION]`. If a citizen omitted the phrase "Income Tax Act", the query would fail classification as `Domain.TAXATION`.

#### B. Category Selection (`backend/rag/runtime.py`)
- `retrieve_if_enabled` (`lines 164–165`):
  `elif domain in (Domain.TAXATION, "tax", "taxation"): category = "tax"`
- `category` is resolved to `"tax"`.
- Calls `get_retriever().search(expanded_query, category="tax", domain=Domain.TAXATION, top_k=top_k)`.
- **Deficiency Observed**: In `_CATEGORY_TERMS["tax"]` (`lines 23–29`), `148`, `148a`, `147`, `149`, `151`, and `reassessment` are missing. If fallback to `supported_category` occurred, it would fail.

#### C. Retriever Filtering & Token Hijacking (`backend/rag/retriever.py`)
- `allowed_categories = get_allowed_rag_categories(resolved_domain)` (`lines 118–120`):
  `Domain.TAXATION` returns `{"tax", "civic"}` (`domain_router.py:203`).
  Intersection with `category="tax"` yields `allowed_categories = {"tax"}`.
- BM25 and vector search query only the tax corpus (which lacks reassessment documents).
- Generic legal tokens in the user query—`"notice"`, `"Section"`, `"Income Tax"`, `"Assessment Year"`, `"days"`—heavily match:
  - `itr_defective_return_manual_01` (Section 139(9) Defective Return Notice, 15 days deadline)
  - `itr_condonation_delay_manual_01` (Section 119(2)(b) Delay Condonation, 30 days deadline)
- `_TROUBLE_TOKENS` check (`retriever.py:164`):
  Contains `"limit"`. Because the user asks `"Did the time limit to issue this notice expire"`, `is_trouble_query` evaluates to `True`.
- Troubleshooting Boost (`retriever.py:233–236`):
  ```python
  if is_trouble_query and (allowed_categories is None or document.category in allowed_categories) and any(tag in doc_tags for tag in ("troubleshooting", "escalation", "sop", "manual")):
      score += 0.05
      signals["troubleshooting_boost"] = 0.05
  ```
  Both `itr_defective_return_manual_01` and `itr_condonation_delay_manual_01` carry the tag `"troubleshooting"` and receive an automatic `+0.05` boost!

---

### 1.3 Confidence Gate & CRAG Suppression (`backend/web_search/confidence.py` & `backend/pipeline.py`)
- `compute_rag_confidence` (`confidence.py:20, 50`):
  ```python
  _RRF_HIGH_CONFIDENCE_FLOOR = 0.040
  normalized = min(top_score / _RRF_HIGH_CONFIDENCE_FLOOR, 1.0)
  ```
- Because the top retrieved document receives:
  - Rank 1 Lexical RRF: `1 / (60 + 1) ≈ 0.01639`
  - Rank 1 Vector RRF: `1 / (60 + 1) ≈ 0.01639`
  - Troubleshooting Boost: `+0.05000`
  - Top Score: `0.01639 + 0.01639 + 0.05000 = 0.08278`
- `normalized` score: `min(0.08278 / 0.040, 1.0) = 1.000`!
- In `backend/pipeline.py` (`lines 604–606`):
  ```python
  rag_confidence = compute_rag_confidence(rag_result)
  if rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD: # default 0.75
  ```
  Since `1.000 < 0.75` is `False`, **live CRAG web search fallback is completely bypassed**.
- In `backend/pipeline.py` (`line 665`):
  `top_hit.score (0.08278) < MIN_RRF_CONFIDENCE_THRESHOLD (0.010)` is `False`. The strict grounding refusal gate does NOT trigger.

---

### 1.4 Explainer Scaffolding & False HIGH Badge (`backend/modules/explainer.py`)
- Direct vs. Binary Question Detector (`explainer.py:152–159`):
  ```python
  def _is_direct_or_binary_question(query: str) -> bool:
      lowered = query.strip().lower()
      return any(lowered.startswith(p) for p in (
          "can i", "can we", "can a", "should i", "should we", "do i need", "does it",
          "will it", "is it", "is there", "are we", "am i", "whether", "do we need"
      ))
  ```
  The user query begins with `"I got an email notice..."`. Since it does not match any prefix, `_is_direct_or_binary_question` returns `False`.
- Step Scaffolding Forcing (`explainer.py:330–361`):
  - If `top_hit_text` has numbered steps (as in `itr_defective_return_manual_01`), it extracts the Section 139(9) defective return steps.
  - If `dynamic_steps` are empty, lines 353–361 unconditionally inject the generic 3-step checklist:
    1. `Review Income Tax User Manual on Responding to Section 139(9) Defective Return Notices`
    2. `Review Income Tax Manual on Section 119(2)(b) Condonation of Delay for Expired ITR Verification`
    3. `Verify Official Portal and Apply` (`Visit https://www.incometax.gov.in/...`)
- Confidence Badge Assignment (`explainer.py:364–365`):
  ```python
  top_score = result.hits[0].score
  calc_conf = "high" if top_score >= 0.05 else ("medium" if top_score >= 0.02 else "low")
  ```
  Because `top_score` is `0.08278 >= 0.05`, `calc_conf` is set to **`"high"`**.
- The system returns an answer about Section 139(9) Defective Returns or Section 119(2)(b) with a **HIGH confidence badge** for a Section 148A(b) reassessment notice query.

---

## 2. Logic Chain

```
[Observation 1.1: Zero statutory reassessment documents in manifest/troubleshooting]
         │
         ▼
[Step 1: BM25/Vector search forced to match nearest lexical neighbors in "tax"]
         │ (Tokens "notice", "Section", "Income Tax", "Assessment Year", "days" match 139(9) & 119(2)(b))
         ▼
[Observation 1.2: Query contains "limit" -> matches _TROUBLE_TOKENS]
         │
         ▼
[Step 2: retriever.py grants unconditional +0.05 troubleshooting_boost to 139(9)/119(2)(b)]
         │
         ▼
[Observation 1.3: top_score reaches ~0.0828, exceeding _RRF_HIGH_CONFIDENCE_FLOOR (0.040)]
         │
         ▼
[Step 3: compute_rag_confidence outputs 1.0; CRAG web search fallback is suppressed]
         │
         ▼
[Observation 1.4: explainer.py checks top_score >= 0.05 -> assigns confidence="high"]
         │
         ▼
[Step 4: Off-topic 139(9) document receives HIGH confidence badge despite 0% relevance to 148A]
         │
         ▼
[Observation 1.4: _is_direct_or_binary_question fails on "I got..." prefix]
         │
         ▼
[Step 5: Analytical legal question forced into 3-step procedural checklist ("Review Doc 1, Review Doc 2, Apply")]
```

---

## 3. Official Statutory Rules: Section 149 Limitation & Section 148A(b) Reply Window

### 3.1 Legislative Framework (Finance Act 2021 Reassessment Scheme)
Under the substituted scheme of reassessment introduced by Finance Act 2021 (effective 1 April 2021):
- **Section 147**: Authorizes the Assessing Officer (AO) to assess or reassess income escaping assessment.
- **Section 148**: Requires issue of notice before assessment/reassessment. Such notice **cannot be issued without prior compliance with Section 148A and statutory approvals under Section 151**.
- **Section 148A**: Mandatory pre-issuance procedure:
  - **Clause (a)**: Preliminary inquiry (if needed) with prior approval.
  - **Clause (b)**: Service of a Show Cause Notice (SCN) giving the taxpayer an opportunity of being heard.
  - **Statutory Reply Window**: Under Section 148A(b), the time allowed to the taxpayer to submit a reply shall be:
    > **"not less than seven days and but not exceeding thirty days from the date on which such notice is issued, or such further period as may be allowed on application made by the taxpayer."**
  - **Clause (c)**: Consideration of taxpayer's reply.
  - **Clause (d)**: Passing an order deciding whether it is a fit case to issue notice under Section 148.

### 3.2 Limitation Period Analysis under Section 149(1) for AY 2018-19
- **Relevant Assessment Year (AY)**: AY 2018-19 (Financial Year 2017-18).
- **End of Relevant Assessment Year**: **31 March 2019**.
- **Normal Limitation Period (3 Years) — Section 149(1)(a)**:
  - Notice under Section 148 cannot be issued after **three years from the end of the relevant assessment year**.
  - Calculation: 31 March 2019 + 3 years = **31 March 2022**.
  - **The 3-year normal limitation period expired on 31 March 2022**.
- **Extended Limitation Period (Up to 10 Years) — Section 149(1)(b)**:
  - An extended period of up to 10 years (i.e. up to 31 March 2029) can ONLY be invoked if:
    The Assessing Officer has in his possession books of account, documents, or evidence revealing that income chargeable to tax which has escaped assessment—represented in the form of:
    (i) an **asset**;
    (ii) **expenditure** in respect of a transaction or in relation to an event or occasion; or
    (iii) an **entry or entries in the books of account**—
    amounts to or is likely to amount to **fifty lakh rupees (₹50,00,000) or more** for that assessment year.
- **Application to Citizen's Factual Matrix**:
  - Alleged escaped income: **₹6.5 Lakhs** (unexplained share trading transactions).
  - Condition check: **₹6.5 Lakhs < ₹50 Lakhs threshold**.
  - Legal Consequence: The extended limitation period under Section 149(1)(b) **does not apply**.
  - **Conclusion on Limitation**: The notice issued for AY 2018-19 where alleged escaped income is ₹6.5 Lakhs is **barred by limitation (time-barred) and jurisdictionally defective**.
- **Application to Sub-Question 2 (Reply Window)**:
  - The taxpayer is entitled to a reply window of **minimum 7 days up to 30 days** from the date of issuance of the Section 148A(b) notice (or any further extension formally requested and granted).

---

## 4. Synthesis of Architectural Gaps & Recommendations

### Gap 1: Corpus Void (Requirement R4)
- **Problem**: The RAG corpus completely lacks official provisions for reassessment (Sections 147, 148, 148A, 149, 151).
- **Remediation**:
  1. Add an official statutory document to `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl` (or a dedicated official statutory file in `backend/data/refined/official_sources/incometax_portal/`) registered in `backend/data/rag_manifest.json`.
  2. The document must define:
     - Section 148A(b) show-cause procedure and statutory reply window: 7 to 30 days.
     - Section 149 limitation calculation: 3-year normal limitation (end of AY + 3 years) vs 10-year extended limitation (requires escaped income represented by asset/expenditure/entry >= ₹50 Lakhs).
     - Section 151 specified authority approvals.
     - Section 148A(d) order requirements.

### Gap 2: Domain Router & Category Selection Blind Spots
- **Problem**: `Domain.TAXATION` regexes in `backend/modules/domain_router.py` only match `139(9)`, `119(2)(b)`, `143(1)`. Reassessment sections are missing.
- **Remediation**:
  - In `backend/modules/domain_router.py`: Add `r"\b(?:section\s+147|section\s+148|section\s+148a|section\s+149|section\s+151|148a\(b\)|148a\(d\)|148a|reassessment|escaped\s+income|time-barred|time\s+limit|limitation\s+period)\b"` to `_DOMAIN_PATTERNS[Domain.TAXATION]`.
  - In `backend/rag/runtime.py`: Add `("148", "148a", "147", "149", "151", "reassessment", "escaped income")` to `_CATEGORY_TERMS["tax"]`.

### Gap 3: Retriever Conflict Suppression & Boosting
- **Problem**: Keyword hijacking allows `itr_defective_return_manual_01` (139(9)) to win rank 1 on reassessment queries due to generic word overlap and unconditional `troubleshooting_boost` (+0.05).
- **Remediation**:
  - In `backend/rag/retriever.py`:
    - Add `"148a(b)"`, `"148a"`, `"148"`, `"149"`, `"147"`, `"151"` to `_EXACT_CODES`.
    - Add a `reassessment` cluster to `_SYMPTOM_CLUSTERS`:
      ```python
      {
          "name": "tax_reassessment",
          "match": ("148a", "148", "reassessment", "149", "escaped income", "time-barred", "unexplained share", "3-year vs 10-year"),
          "boost_terms": ("section 148a", "section 149", "reassessment", "escaped income", "limitation"),
          "conflicts": ("139(9)", "defective return", "119(2)(b)", "condonation", "bank validation", "pan card"),
      }
      ```
    - Apply a `-0.40` cross-contamination penalty against `139(9)` / `119(2)(b)` when the query focuses on `148A` / reassessment.

### Gap 4: Relevance & Confidence Gating Prior to Synthesis (Requirement R2)
- **Problem**: `compute_rag_confidence` in `backend/web_search/confidence.py` and `calc_conf` in `backend/modules/explainer.py` look exclusively at raw numerical RRF scores (which are artificially inflated above 0.040/0.050 by RRF arithmetic and troubleshooting boosts). There is **zero semantic alignment or cross-attention support check** between the query's core legal entities and the retrieved chunks.
- **Remediation**:
  1. Implement a **semantic alignment & entity overlap verification gate**:
     - Extract core query anchors: specific statutory sections (`148A`, `149`), specific error codes, or primary domain entities.
     - If the top retrieved chunks do not contain semantic support for the specific anchors in the user query, **force RAG confidence to "low"** (< 0.25).
  2. With RAG confidence downgraded:
     - `pipeline.py:606` will trigger **live CRAG web search** against official portals (`incometax.gov.in`, `cbdt.gov.in`).
     - If CRAG also lacks evidence, `pipeline.py:665` will output an **honest refusal** rather than guessing or asserting a false "HIGH" confidence badge.

### Gap 5: Response Shape and Multi-part Decomposition (Requirements R1 & R3)
- **Problem**:
  - `_is_direct_or_binary_question` only checks conversational prefixes ("can i", "is it") and fails on citizen narrative statements ("I got an email notice...").
  - `explainer.py` forces all non-direct questions into a generic 3-step checklist ("Review Doc 1, Review Doc 2, Verify Official Portal").
  - Multi-part queries (Limitation expiry + Reply window) are flattened into a single procedural step list.
- **Remediation**:
  1. Expand intent classification to detect **analytical, calculation, and legal-interpretation queries** (e.g., questions with `"did the time limit expire"`, `"is it time-barred"`, `"how many days"`, `"calculate"`, `"what is the limitation"`).
  2. For analytical/interpretive queries:
     - **Suppress artificial numbered step lists** (`steps = []`).
     - Structure the synthesis output to address **each decomposed sub-question explicitly in the summary/analytical body**:
       * **Sub-question 1 (Limitation)**: Clear legal conclusion that for AY 2018-19, the 3-year period expired on 31 March 2022, and the 10-year extended limitation under Section 149(1)(b) is inapplicable because ₹6.5 Lakhs is below the ₹50 Lakh threshold; the notice is time-barred.
       * **Sub-question 2 (Reply Window)**: Clear statement of the Section 148A(b) window: minimum 7 days up to 30 days (with right to seek extension).

---

## 5. Caveats
- No code was modified and no tests were executed during this investigation, strictly preserving read-only explorer constraints.
- The analysis assumes standard Finance Act 2021 reassessment provisions apply to notices issued post-1 April 2021 (the Supreme Court's ruling in *Ashish Agarwal* and CBDT Instruction 01/2022 treated pre-April 2021 notices issued under old law as Section 148A notices, which were subject to Section 149 limitation).

---

## 6. Conclusion
The failure in Case 1 stems from an architectural confluence of three defects:
1. **Corpus Absence (R4)**: Total absence of Sections 147, 148, 148A, 149, 151 in `rag_manifest.json` and `troubleshooting_tax.jsonl`.
2. **Confidence Decoupling (R2)**: A blind RRF scoring and troubleshooting boost formula that grants a `"HIGH"` confidence badge to completely unrelated documents (Section 139(9) defective return or Section 119(2)(b)), simultaneously suppressing CRAG web search fallback.
3. **Rigid Scaffolding (R1 & R3)**: Narrow binary detection that forces analytical legal-interpretation queries into a generic 3-step procedural checklist without decomposing multi-part queries.

---

## 7. Verification Method
To independently verify these findings:
1. **Corpus Absence**:
   Inspect `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl` and `backend/data/rag_manifest.json`. Search for `"148A"` or `"149"` — observe 0 occurrences.
2. **Confidence Escalation**:
   Inspect `backend/web_search/confidence.py:20, 50` and `backend/modules/explainer.py:364–365`. Trace score math: lexical RRF (0.0164) + vector RRF (0.0164) + troubleshooting boost (0.05) = 0.0828 >= 0.05 (`calc_conf = "high"`).
3. **Step Scaffolding Forcing**:
   Inspect `backend/modules/explainer.py:152–159` and `352–361`. Note that `"I got an email notice..."` does not match `_is_direct_or_binary_question`, falling into lines 353–361 ("Review Doc 1", "Review Doc 2", "Verify Official Portal and Apply").
