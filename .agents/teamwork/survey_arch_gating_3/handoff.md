# Handoff Report: R1, R2, R3 Pipeline Architecture, Confidence Gating & Test Specifications

**Agent ID**: `survey_arch_gating_3`  
**Role**: Specification and Architecture Investigator (`teamwork_spec_miner`)  
**Working Directory**: `c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_arch_gating_3`  
**Date**: 2026-11-09T12:10:00Z  
**Recipient**: `39a4200a-88ea-4d70-9ed4-ca0bc59538f8`

---

## 1. Observation

### 1.1 R1 Response Shape & Scaffolding: Exact Code Loci
1. **Mandatory 3-Step Checklist Fallback in `backend/modules/explainer.py:352-361`**:
   ```python
   352:     if not dynamic_steps and not _is_direct_or_binary_question(user_question):
   353:         for idx, c in enumerate(citations[:2], 1):
   354:             clean_name = re.sub(r"[|\-].*$", "", c.title).strip() or f"Official guideline {idx}"
   355:             dynamic_steps.append(Step(title=f"Review {clean_name}"[:80], detail=c.excerpt[:350].strip()))
   356:         dynamic_steps.append(
   357:             Step(
   358:                 title="Verify Official Portal and Apply",
   359:                 detail=f"Visit {first.url} to review current deadlines, official eligibility, and submit applications directly.",
   360:             )
   361:         )
   ```
   - `dynamic_steps` is populated ONLY if the raw chunk text contains numbered regex patterns matching `^[1-9]\.\s+[A-Z]` (`explainer.py:331-343`) or blocks matching `Statutory Penalty|Escalation|Delivery TAT` (`explainer.py:344-350`).
   - For statutory text, sections of the Income Tax Act, CBDT circulars, or analytical questions, `dynamic_steps` evaluates to `[]`.
   - `_is_direct_or_binary_question(user_question)` (`explainer.py:152-159` and `llm.py:34-41`) only matches 13 hardcoded English prefix strings:
     `"can i"`, `"can we"`, `"can a"`, `"should i"`, `"should we"`, `"do i need"`, `"does it"`, `"will it"`, `"is it"`, `"is there"`, `"are we"`, `"am i"`, `"whether"`, `"do we need"`.
   - Any question starting with narrative context (e.g. Case 1: *"I got an email notice under Section 148A(b)..."*; Case 2: *"My salary credit in August came with a flat 20% TDS..."*) evaluates to `False`.
   - This unconditionally forces the 3-step procedural checklist:
     - Step 1: `Review [Citation 1 Title]`
     - Step 2: `Review [Citation 2 Title]`
     - Step 3: `Verify Official Portal and Apply`

2. **Step Re-Inflation in `backend/modules/llm.py:802-806`**:
   ```python
   802:     elif answer.citations and len(answer.steps) <= 3 and any("review" in s.title.lower() or "read" in s.title.lower() for s in answer.steps):
   803:         ai_steps = _extract_dynamic_steps_from_summary(rewrite.summary)
   804:         if len(ai_steps) >= 2:
   805:             updates["steps"] = ai_steps
   ```
   - Even when the local LLM correctly responds to an analytical query with `steps: []`, `apply_rewrite_to_answer` checks if the existing answer had <= 3 review steps.
   - If `_extract_dynamic_steps_from_summary` finds >= 2 sentences with action words (`visit`, `check`, `verify`), it synthesizes new artificial steps.
   - If fewer than 2 sentences match action words, `updates["steps"]` is not set, leaving `answer.steps` unchanged — thus retaining the artificial 3-step checklist!

3. **Pytest Offline Bypass in `backend/modules/llm.py:838`**:
   ```python
   838:     if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("TEST_LIVE_LLM"):
   839:         return answer
   ```
   - During automated tests, `enhance_grounded_answer` immediately returns the un-enhanced `answer`.
   - As a result, the deterministic 3-step checklist from `explainer.py:352-361` directly leaks into test assertions.

4. **Web Synthesizer Step Penalty in `backend/web_search/synthesizer.py:391-396`**:
   ```python
   391:         if len(step_objects) >= 2 and len(summary) >= 60:
   392:             confidence_val = "high"
   393:         elif len(summary) >= 40:
   394:             confidence_val = "medium"
   395:         else:
   396:             confidence_val = "low"
   ```
   - Live web synthesis explicitly penalizes answers that have no steps: even a comprehensive analytical response cannot receive `confidence="high"` unless `len(step_objects) >= 2`.

---

### 1.2 R2 Relevance & Confidence Gating: Exact Code Loci
1. **Isolated RRF Confidence Scoring in `backend/web_search/confidence.py:23-53`**:
   ```python
   23: def compute_rag_confidence(rag_result) -> float:
   ...
   40:     top_score: float = 0.0
   41:     try:
   42:         top_score = float(hits[0].score)
   ...
   50:     normalized = min(top_score / _RRF_HIGH_CONFIDENCE_FLOOR, 1.0)
   51:     return normalized
   ```
   - `_RRF_HIGH_CONFIDENCE_FLOOR = 0.040`.
   - `compute_rag_confidence` accepts ONLY `rag_result`; it does not accept the user's `query`.
   - It performs zero term matching, zero entity verification, and zero semantic alignment.
   - If `top_score >= 0.040`, `normalized = 1.0` (100% / HIGH confidence).

2. **CRAG Suppression Gate in `backend/pipeline.py:605-606` & `962-963`**:
   ```python
   605:         rag_confidence = compute_rag_confidence(rag_result)
   606:         if rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD:
   ```
   - `WEB_SEARCH_CONFIDENCE_THRESHOLD = 0.35` (`backend/config.py:35`).
   - If `top_score >= 0.014`, `rag_confidence = 0.014 / 0.040 = 0.35 >= 0.35`.
   - Consequently, any retrieved document with score >= 0.014 marks the query as "confident", completely bypassing live CRAG web search.

3. **Arbitrary Dynamic Confidence Badge in `backend/modules/explainer.py:364-366` & `backend/pipeline.py:1076-1077`**:
   ```python
   364:     top_score = result.hits[0].score
   365:     calc_conf = "high" if top_score >= 0.05 else ("medium" if top_score >= 0.02 else "low")
   ```
   ```python
   1076:    score_conf = compute_rag_confidence(rag_result)
   1077:    dynamic_conf = "high" if score_conf >= 0.75 else ("medium" if score_conf >= 0.35 else "low")
   ```
   - When an off-topic query (e.g. Case 1: Section 148A(b) reassessment notice) is processed, the query contains words like "Income Tax Act", "Assessment Year 2018-19", "notice", "days", "reply".
   - The BM25 index in `backend/rag/retriever.py:129` matches `itr_condonation_delay_manual_01` (Section 119(2)(b)) or `itr_defective_return_manual_01` (Section 139(9)) or `pan_protean_application_troubleshooting_01`.
   - Because multiple words match, BM25 rank 1 yields RRF score ~0.025-0.045.
   - The pipeline calculates `confidence = "high"`, attaches a "Relevant official material" title from Section 119(2)(b), suppresses CRAG, and emits a high-confidence false answer.

---

### 1.3 R3 Multi-Part Query Decomposition: Exact Code Loci
1. **Monolithic Query Ingestion in `backend/rag/retriever.py:81-89` & `backend/rag/runtime.py:149-185`**:
   - `RagRetriever.search(clean_query)` receives compound queries as a single flat string.
   - `tokenize(clean_query)` pools all tokens from both sub-questions into a single set `q_terms`.
   - In dense vector search (`retriever.py:143`), `FastEmbedProvider.embed_texts((clean_query,))[0]` embeds the entire 45-word multi-part paragraph into a single vector.
   - This creates severe semantic dilution: the vector is a centroid between factual background ("unexplained share trading transactions"), statutory limitation rule ("3-year vs 10-year rule"), and procedural reply deadline ("how many days").
2. **Absence of Sub-Question Tracking in `backend/modules/explainer.py` & `llm.py`**:
   - `explain_rag_result` clips the first paragraph of `hits[0].document.text`.
   - In `backend/modules/llm.py:249-320`, `_build_llm_prompt` dumps the entire query into `Citizen Question`.
   - There is no parsing of compound questions, no check whether retrieved chunks satisfy both sub-intents, and no structural prompting requiring answers to all sub-questions.

---

### 1.4 Corpus Gap for Reassessment (148A, 149) and Inoperative PAN (206AA, 114AAA)
- Search across `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl` (7 lines), `troubleshooting_pan.jsonl` (3 lines), and `backend/data/refined/itr_synthetic/itr_chunks_clean.jsonl` (111 lines):
  - Section 147, 148, 148A, 149, 151: **0 occurrences**.
  - Section 206AA, Rule 114AAA, CBDT Circular 03/2023: **0 occurrences**.
- Local corpus completely lacks reassessment and inoperative PAN statutory provisions, making relevance gating and CRAG web search triggering critical.

---

## 2. Logic Chain

```
[Observation 1.1.1: explainer.py:352-361]
     │
     ├─> dynamic_steps is [] for statutory/analytical text.
     ├─> _is_direct_or_binary_question() only detects 13 English prefixes ("can i", "is it").
     ├─> Case 1 & Case 2 start with narrative statements -> _is_direct_or_binary_question() returns False.
     │
     ▼
[Finding 1: Mandatory Checklist Trap]
Pipeline unconditionally forces artificial 3-step checklist ("Review [Doc 1], Review [Doc 2], Verify Official Portal").
In pytest mode (Observation 1.1.3), LLM rewrite is disabled, directly failing R1 acceptance criteria.

[Observation 1.2.1: confidence.py:23-53 & explainer.py:364-366]
     │
     ├─> compute_rag_confidence() evaluates hits[0].score / 0.040 in complete isolation from query terms.
     ├─> Query terms "Income Tax", "Assessment Year", "notice", "days", "reply" match Section 119(2)(b) or PAN FAQ.
     ├─> BM25 rank 1 produces RRF score ~0.035.
     │
     ▼
[Finding 2: Gating Hole & False High Confidence]
rag_confidence evaluates to 0.035 / 0.040 = 0.875 >= 0.35.
CRAG live search is bypassed; off-topic chunks receive HIGH confidence badge, directly violating R2 acceptance criteria.

[Observation 1.3.1: retriever.py:81-89 & runtime.py:149-185]
     │
     ├─> Compound user queries are tokenized and vector-embedded as a single flat string.
     ├─> Dense vector suffers semantic dilution; BM25 matches whichever clause has higher term frequency.
     ├─> Explainer and LLM prompt treat the query as a single monolithic block.
     │
     ▼
[Finding 3: Multi-Part Conflation]
Neither sub-question is cleanly isolated. One sub-question is either omitted or conflated, failing R3 acceptance criteria.
```

---

## 3. Architecture Specification & Design

### Track 1: R1 Response Shape & Scaffolding Architecture

#### 1.1 Query Modality Classification
Implement an intent modality classifier `classify_query_modality(query: str) -> QueryModality`:
```python
class QueryModality(str, Enum):
    PROCEDURAL = "procedural"           # "How do I apply...", "Steps to renew...", "Link PAN"
    ANALYTICAL = "analytical"           # "Did time limit expire...", "What are legal consequences..."
    CALCULATION = "calculation"         # "Calculate limitation...", "Late fee under 234H..."
    LEGAL_INTERPRETATION = "legal"      # "Can employer refund...", "Section 148A(b) reply window..."
```

**Classification Criteria**:
- A query is classified as `ANALYTICAL`, `CALCULATION`, or `LEGAL_INTERPRETATION` if:
  1. It contains statutory reference tokens: `\b(?:section|sec\.?|rule|circular)\s+[0-9]+[a-z]*\b` (e.g. `148A`, `149`, `206AA`, `114AAA`, `234H`, `138`).
  2. It contains temporal/limitation inquiry patterns: `\b(?:time\s+limit|expire|expired|limitation|3-year|10-year|barred|deadline\s+to\s+reply|how\s+many\s+days\s+to\s+reply)\b`.
  3. It contains validity/legal consequence patterns: `\b(?:valid|invalid|consequence|legal\s+consequences|inoperative|penalty\s+applicable|can\s+(?:company|employer)\s+refund)\b`.
  4. It contains calculation patterns: `\b(?:calculate|computation|threshold|excess\s+20%|flat\s+20%|late\s+fee)\b`.
- A query is classified as `PROCEDURAL` ONLY if it explicitly asks for a step-by-step application, submission, or operational process (e.g. `how to apply`, `procedure to register`, `step by step`, `how to file`).

#### 1.2 Explainer Modification (`backend/modules/explainer.py`)
- Remove the unconditional injection of `Step(title=f"Review {clean_name}"...)` in lines 352-361.
- For `ANALYTICAL`, `CALCULATION`, or `LEGAL_INTERPRETATION` modalities:
  - `steps` MUST be `[]` (empty list).
  - `documents_needed` MUST be `[]` (empty list, unless user explicitly asks "what documents to carry/attach").
  - `summary` MUST contain the direct, substantive analytical explanation.

#### 1.3 LLM Prompt & Post-Processing (`backend/modules/llm.py`)
- Update `_build_llm_prompt` system directive:
  ```text
  QUERY MODALITY DIRECTIVE:
  - If the citizen's question is analytical, legal-interpretation, or calculation (e.g., limitation period, notice validity, statutory deadline, tax refund rules, inoperative PAN consequences):
    1. Provide a comprehensive, structured analytical breakdown directly in 'summary'.
    2. Address every legal rule, arithmetic threshold, and statutory section explicitly.
    3. Return 'steps': [] and 'documents_needed': []. Do NOT synthesize artificial review checklists or procedural steps.
  - If and only if the citizen asks how to perform a multi-step administrative procedure:
    Provide actionable sequential steps in 'steps'.
  ```
- In `apply_rewrite_to_answer` (`llm.py:802-806`):
  - If `rewrite.steps` is empty, or if query modality is non-procedural, do NOT call `_extract_dynamic_steps_from_summary`. Set `updates["steps"] = []`.

---

### Track 2: R2 Relevance and Confidence Gating Architecture

#### 2.1 Multi-Factor Relevance & Confidence Calculation
Update `compute_rag_confidence` in `backend/web_search/confidence.py` to accept BOTH `rag_result` and `query`:
```python
def compute_rag_confidence(
    rag_result: RetrievalResult | None,
    query: str | None = None,
) -> float:
```

**Computation Formula**:
$$\text{Confidence} = \text{BaseScore} \times \text{EntityAlignment} \times \text{TermOverlap}$$

1. **BaseScore**:
   $$\text{BaseScore} = \min\left(\frac{\text{hits}[0].\text{score}}{\text{RRF\_HIGH\_CONFIDENCE\_FLOOR}}, 1.0\right) \quad (\text{floor} = 0.040)$$
2. **Statutory Entity Alignment Factor** ($\text{EntityAlignment} \in [0.0, 1.0]$):
   - Extract statutory sections and primary entities from `query`:
     $\mathcal{E}_{\text{query}} = \{e \in \text{query} \mid e \text{ matches statutory section, rule, or circular}\}$.
   - If $\mathcal{E}_{\text{query}} \neq \emptyset$:
     - Check if any entity in $\mathcal{E}_{\text{query}}$ appears in candidate chunk text, title, or tags:
       $$\text{EntityAlignment} = \begin{cases} 1.0 & \text{if } \exists e \in \mathcal{E}_{\text{query}} \text{ present in candidate chunk} \\ 0.15 & \text{if none present (severe statutory mismatch penalty)} \end{cases}$$
   - If $\mathcal{E}_{\text{query}} = \emptyset$, $\text{EntityAlignment} = 1.0$.
3. **Lexical/Semantic Overlap Factor** ($\text{TermOverlap} \in [0.0, 1.0]$):
   - Extract informative content words $W_{\text{query}}$ (length $\ge 3$, excluding civic stopwords).
   - Compute Jaccard / containment overlap against chunk text:
     $$\text{TermOverlap} = \min\left(\frac{|W_{\text{query}} \cap W_{\text{chunk}}|}{|W_{\text{query}}| \times 0.30}, 1.0\right)$$

#### 2.2 Gate Behavior
- If $\text{Confidence} < 0.35$ (`WEB_SEARCH_CONFIDENCE_THRESHOLD`):
  - In `backend/pipeline.py:606` & `963`: Live CRAG web search is triggered.
  - If live CRAG search finds matching official pages on allowlisted domains (`incometax.gov.in`, etc.), synthesize from web.
  - If live CRAG search fails or finds no relevant content:
    - Return `not_found_answer(safe_text)` with `confidence = "low"`.
    - Refusal summary explicitly states lack of verified canonical documentation.
    - Off-topic chunks (e.g. PAN FAQ or 119(2)(b) for a 148A reassessment query) can NEVER produce a HIGH confidence badge.

---

### Track 3: R3 Multi-Part Query Decomposition Architecture

#### 3.1 Pre-Retrieval Decomposer
Implement `decompose_query(query: str) -> list[str]` in `backend/rag/retriever.py` (or a dedicated `backend/rag/decomposition.py`):
1. **Clause & Conjunction Boundary Detection**:
   - Split on coordinate conjunctions connecting distinct questions: `\b(?:and\s+(?:how|what|did|can|is|where|who)|;|\?)\b`.
2. **Sub-Question Extraction for Case 1**:
   - $Q_1$: `"Did the time limit to issue notice under Section 148A(b) expire for Assessment Year 2018-19 under 3-year vs 10-year rule Section 149 for ₹6.5 Lakhs?"`
   - $Q_2$: `"How many days do I have to submit reply to Section 148A(b) notice?"`
3. **Sub-Question Extraction for Case 2**:
   - $Q_1$: `"How long before inoperative PAN becomes active after paying ₹1000 late fee under Section 234H Rule 114AAA Circular 03/2023?"`
   - $Q_2$: `"How do I get company employer to refund excess 20% TDS deducted under Section 206AA or claim in ITR?"`

#### 3.2 Multi-Intent Retrieval & Coverage Tracking
- Execute retrieval for each sub-question $Q_i$.
- Track coverage per sub-question:
  $$\text{Coverage}(Q_i) = \begin{cases} \text{True} & \text{if top hit has statutory entity alignment} \\ \text{False} & \text{otherwise} \end{cases}$$
- If $Q_1$ is covered locally but $Q_2$ lacks evidence, live CRAG query specifically targets $Q_2$.

#### 3.3 Multi-Part Synthesis Enforcement
- The prompt explicitly structures the citizen's questions:
  ```text
  CITIZEN QUESTIONS TO ANSWER:
  1. [Sub-question 1 text]
  2. [Sub-question 2 text]

  MANDATORY REQUIREMENT:
  Your summary must provide distinct, direct answers to ALL numbered questions above.
  Do not ignore or omit any question.
  ```

---

## 4. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Response Shape | Extractive Review Steps Fallback | When `dynamic_steps` is empty, creates 2 "Review [Doc]" steps and 1 "Verify Portal" step | `user_question`, `citations` | `list[Step]` (len 3) | Forces checklists onto non-procedural queries | `backend/modules/explainer.py:352-361` |
| 2 | Response Shape | Binary Question Filter | Checks if query starts with 13 narrow English prefixes | `query: str` | `bool` | Misses analytical questions with context | `backend/modules/explainer.py:152-159` |
| 3 | Response Shape | Dynamic Step Extraction | Extracts sentences with action verbs from LLM summary | `summary: str` | `list[Step]` | Re-injects steps into analytical answers | `backend/modules/llm.py:748-763, 802-806` |
| 4 | Response Shape | Offline Pytest LLM Bypass | Bypasses local LLM when running under pytest | `os.environ` | `Answer` (unmodified) | Leaks raw 3-step checklists into test runs | `backend/modules/llm.py:838-840` |
| 5 | Response Shape | Web Synthesizer Confidence Floor | Requires $\ge 2$ steps for HIGH confidence badge | `step_objects`, `summary` | `confidence: str` | Penalizes valid analytical responses to medium/low | `backend/web_search/synthesizer.py:391-396` |
| 6 | Confidence Gating | RAG Confidence Score | Maps top RRF score linearly to $[0.0, 1.0]$ | `rag_result` (hits[0].score) | `float` in $[0.0, 1.0]$ | Disregards query terms; off-topic chunks score HIGH | `backend/web_search/confidence.py:23-53` |
| 7 | Confidence Gating | CRAG Confidence Gate | Bypasses live web search if score $\ge 0.35$ | `rag_confidence` | Triggers or skips CRAG | Bypasses CRAG when off-topic chunk hits RRF 0.014 | `backend/pipeline.py:605-606, 962-963` |
| 8 | Confidence Gating | Explainer Dynamic Confidence | Assigns HIGH if RRF $\ge 0.05$, MEDIUM if $\ge 0.02$ | `result.hits[0].score` | `"high" \| "medium" \| "low"` | Assigns HIGH confidence to off-topic chunks | `backend/modules/explainer.py:364-366` |
| 9 | Query Retrieval | Anti-Keyword-Hijacking | Penalizes chunks lacking explicit domain entities (FASTag, etc.) | `query_entities`, `lowered_doc` | `score -= 0.60` | Only covers 14 hardcoded entities | `backend/rag/retriever.py:204-212` |
| 10 | Query Retrieval | Symptom Cluster Penalties | Boosts matching cluster and penalizes conflicts | `_SYMPTOM_CLUSTERS` | `score \pm 0.15` | Covers 9 specific clusters; lacks 148A/inoperative PAN | `backend/rag/retriever.py:239-305` |
| 11 | Query Retrieval | Sub-Procedure Discrimination | Disambiguates 139(9) vs AIS feedback | `is_139_query`, `is_ais_query` | `score \pm 0.40` | Specialized for 139(9)/AIS; lacks 148A / 149 / 206AA | `backend/rag/retriever.py:306-321` |
| 12 | Query Retrieval | Domain Allowed Categories | Filters retrieval corpus by domain | `query_domain` | Allowed RAG categories | Allows `"tax", "civic"` for taxation; permits off-topic tax hits | `backend/modules/domain_router.py:194-210` |

---

## 5. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Response Shape | Narrative query: *"I got an email notice under Section 148A(b)..."* | `_is_direct_or_binary_question` returns `False`; forces 3-step checklist ("Review [Doc 1], Review [Doc 2], Verify Official Portal") |
| 2 | Confidence Gating | Query: *"Did Section 148A(b) notice expire under 3-yr rule?"* against 119(2)(b) chunk | Term overlap on "income tax", "notice", "days", "reply" yields RRF $\approx 0.035$; `compute_rag_confidence` outputs $\approx 0.875$ (HIGH), suppressing CRAG |
| 3 | Query Decomposition | Compound Query: Case 1 (Limitation rule + Reply window) | Single dense vector embedding dilutes both clauses; BM25 ranks whichever clause matches more frequent terms; other clause neglected |
| 4 | Query Decomposition | Compound Query: Case 2 (PAN reactivation timeline + TDS refund) | Retrieves PAN FAQ or bank validation; fails to answer refund impossibility from payroll under Section 206AA |
| 5 | Web Synthesizer Confidence | Direct analytical web answer with valid prose but `steps: []` | Line 393 sets `confidence_val = "medium"`, improperly downgrading high-quality analytical answers |
| 6 | Offline Pytest LLM | Test asserting analytical response shape without live LLM | Returns raw deterministic Answer containing 3-step checklist from `explainer.py:352`, failing `steps == []` assertion |

---

## 6. Automated Test Specifications

### 6.1 Test Suite Structure
Create a dedicated test file: `tests/test_case1_case2_gating_regression.py` (or add to `tests/test_scenes_1_to_3_regression.py`).

### 6.2 Exact Test Requirements & Assertions

#### Test 1: Case 1 — Section 148A(b) Reassessment Notice (AY 2018-19)
```python
def test_case1_reassessment_section_148a_analytical_shape():
    """Verify Case 1 query returns direct analytical answer without artificial checklists."""
    query = (
        "I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 "
        "alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit to issue this "
        "notice expire under the 3-year vs 10-year rule, and how many days do I have to submit my reply?"
    )
    ans = run_pipeline(query)

    # 1. R1: Response Shape & Scaffolding
    assert ans.steps == [], f"Analytical query must not have procedural steps, got: {ans.steps}"
    assert not any("review" in s.title.lower() for s in ans.steps), "Must not have artificial 'Review [Doc]' steps"
    assert not any("verify official portal and apply" in s.title.lower() for s in ans.steps)

    # 2. Sub-Question 1: Limitation calculation under Section 149
    summary_lower = ans.summary.lower()
    assert "149" in ans.summary, "Must cite Section 149 for reassessment time limits"
    assert any(term in summary_lower for term in ("3-year", "3 years", "three years")), "Must explain 3-year rule"
    assert any(term in summary_lower for term in ("10-year", "10 years", "ten years", "50 lakh", "50,00,000")), "Must explain 50 Lakhs threshold for 10-year period"
    assert any(term in summary_lower for term in ("expired", "time-barred", "barred by limitation", "invalid", "cannot be issued")), (
        "Must conclude notice is time-barred since ₹6.5 Lakhs is below ₹50 Lakhs and 3 years expired on 31 March 2022"
    )

    # 3. Sub-Question 2: Reply Window under Section 148A(b)
    assert any(term in summary_lower for term in ("7 days", "minimum 7", "7 to 30 days", "30 days")), (
        "Must specify reply window under Section 148A(b) is minimum 7 days up to 30 days"
    )
```

#### Test 2: Case 2 — Inoperative PAN / 20% TDS Refund
```python
def test_case2_inoperative_pan_tds_refund_decomposition():
    """Verify Case 2 query answers both sub-questions directly without artificial checklists."""
    query = (
        "My salary credit in August came with a flat 20% TDS deduction because my PAN became 'Inoperative' "
        "for missing the Aadhaar linking deadline. I just paid the ₹1,000 late fee under Section 234H on the portal. "
        "How long before my PAN becomes active, and how do I get my company to refund the excess 20% TDS?"
    )
    ans = run_pipeline(query)

    # 1. R1: Response Shape
    assert ans.steps == [], "Analytical query must not have procedural steps"
    summary_lower = ans.summary.lower()

    # 2. Sub-Question 1: Reactivation Timeline (~30 days)
    assert any(term in summary_lower for term in ("30 days", "thirty days", "within 30")), (
        "Must specify PAN reactivation takes ~30 days under Rule 114AAA / CBDT Circular 03/2023"
    )

    # 3. Sub-Question 2: Employer cannot refund deposited TDS; claim via ITR
    assert any(term in summary_lower for term in ("cannot refund", "employer cannot", "company cannot", "no refund by employer")), (
        "Must explain employer cannot refund excess TDS once deposited under Section 206AA"
    )
    assert any(term in summary_lower for term in ("itr", "tax return", "income tax return", "claim refund", "file itr")), (
        "Must explain excess TDS credit/refund must be claimed by filing ITR after PAN is operative"
    )
```

#### Test 3: R2 Relevance & Confidence Gating on Off-Topic Chunks
```python
def test_relevance_confidence_gating_blocks_high_confidence_on_offtopic():
    """Verify off-topic chunks (PAN FAQ or 119(2)(b)) cannot produce HIGH confidence for reassessment query."""
    from backend.web_search.confidence import compute_rag_confidence

    query = (
        "I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 "
        "alleging ₹6.5 Lakhs in unexplained share trading transactions."
    )
    # Mock retrieval hit that returns Section 119(2)(b) condonation of delay
    mock_doc = RagDocument(
        id="itr_condonation_delay_manual_01",
        category="tax",
        title="Income Tax Manual on Section 119(2)(b) Condonation of Delay for Expired ITR Verification",
        section="Section 119(2)(b) Delay Condonation Petitions",
        text="Section 119(2)(b) Condonation of Delay for Expired e-Verification...",
        sources=(),
        tags=("condonation_of_delay", "section_119_2_b"),
    )
    mock_hit = RetrievalHit(document=mock_doc, score=0.038, rank=1)
    mock_result = RetrievalResult(query=query, hits=(mock_hit,), status="supported_lexical", searched_documents=100)

    # With relevance gating incorporating query terms:
    confidence = compute_rag_confidence(mock_result, query=query)
    assert confidence < 0.35, f"Off-topic chunk must have confidence < 0.35 to trigger CRAG, got: {confidence}"
```

#### Test 4: Query Decomposition Unit Test
```python
def test_query_decomposition_isolates_subquestions():
    """Verify multi-part queries are decomposed into distinct sub-questions."""
    from backend.rag.retriever import decompose_query  # Or from decomposition module

    q1 = (
        "I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 "
        "alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit to issue this "
        "notice expire under the 3-year vs 10-year rule, and how many days do I have to submit my reply?"
    )
    sub_qs = decompose_query(q1)
    assert len(sub_qs) == 2
    assert any("time limit" in sq.lower() or "149" in sq.lower() or "3-year" in sq.lower() for sq in sub_qs)
    assert any("reply" in sq.lower() or "days" in sq.lower() for sq in sub_qs)

    q2 = (
        "My salary credit in August came with a flat 20% TDS deduction because my PAN became 'Inoperative' "
        "for missing the Aadhaar linking deadline. I just paid the ₹1,000 late fee under Section 234H on the portal. "
        "How long before my PAN becomes active, and how do I get my company to refund the excess 20% TDS?"
    )
    sub_qs2 = decompose_query(q2)
    assert len(sub_qs2) == 2
    assert any("active" in sq.lower() or "operative" in sq.lower() or "how long" in sq.lower() for sq in sub_qs2)
    assert any("refund" in sq.lower() or "company" in sq.lower() or "tds" in sq.lower() for sq in sub_qs2)
```

---

## 7. Caveats

1. **Local Corpus Ingestion (R4 Dependency)**:
   - Official statutory provisions (Sections 147, 148, 148A, 149, 151) and CBDT Circular 03/2023 / Rule 114AAA are currently absent from `backend/data/refined/`.
   - If Case 1 and Case 2 are to pass deterministically without network access in test environments, official text chunks for these sections must be ingested into `troubleshooting_tax.jsonl` or `rag_manifest.json` under R4.
2. **Local LLM Availability in CI/CD**:
   - Because `os.getenv("PYTEST_CURRENT_TEST")` bypasses local LLM synthesis unless `TEST_LIVE_LLM` is set (`backend/modules/llm.py:838`), the deterministic `explain_rag_result` in `explainer.py` MUST independently implement the correct response shape (`steps: []`) and substantive summary logic. Relying solely on LLM prompt rewriting will fail automated unit tests when LLM is offline.
3. **CRAG Network Boundary**:
   - In production, live DuckDuckGo web search is enabled, but in offline test harnesses, all web search requests must be mocked or fall back to local corpus hits.

---

## 8. Conclusion

1. **R1**: The artificial 3-step checklist ("Review [Doc 1], Review [Doc 2], Verify Official Portal") is enforced in `backend/modules/explainer.py:352-361` and reinforced in `llm.py:802-806` and `synthesizer.py:391-396`. Introducing a Query Modality Classifier (`QueryModality.ANALYTICAL`) and setting `steps = []` for non-procedural queries completely resolves this architectural gap.
2. **R2**: Off-topic documents produce HIGH confidence badges because `backend/web_search/confidence.py:23-53` calculates `top_score / 0.040` without inspecting the query text. Upgrading `compute_rag_confidence` to enforce statutory entity alignment and term overlap penalizes off-topic hits below 0.35, triggering live CRAG search or honest refusal.
3. **R3**: Compound queries currently suffer semantic dilution due to single-string retrieval in `backend/rag/retriever.py:81-89`. Pre-retrieval decomposition into distinct sub-questions, multi-query retrieval, and structured synthesis guarantees that both sub-questions are directly and comprehensively answered.
4. **Tests**: Four comprehensive test specifications with exact assertions for Case 1, Case 2, relevance gating, and query decomposition have been fully defined and ready for test-suite implementation.

---

## 9. Verification Method

To verify these findings and specifications independently:
1. **Inspect Code Locations**:
   - `backend/modules/explainer.py`: Lines 152-159 (narrow binary filter), lines 352-361 (3-step checklist).
   - `backend/modules/llm.py`: Lines 802-806 (step re-inflation), line 838 (pytest bypass).
   - `backend/web_search/confidence.py`: Lines 23-53 (isolated RRF score calculation).
   - `backend/pipeline.py`: Lines 605-606 & 962-963 (CRAG suppression threshold).
   - `backend/web_search/synthesizer.py`: Lines 391-396 (step penalty in confidence calculation).
2. **Inspect Existing Test Suite**:
   - `tests/test_scenes_1_to_3_regression.py`: Inspect Tier 1-3 tests for pattern parity.
   - `tests/test_domain_router.py`: Inspect domain isolation and refusal patterns.
   - `tests/test_web_search.py`: Inspect `TestComputeRagConfidence` (lines 57-100) to confirm isolated score testing.
3. **Invalidation Conditions**:
   - If `compute_rag_confidence` is modified to accept `query` and penaliizes off-topic chunks, Test 3 will pass.
   - If `explainer.py` removes the 3-step checklist for analytical queries, Test 1 and Test 2 will verify `steps == []`.
