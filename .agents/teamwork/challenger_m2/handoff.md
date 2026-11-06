# Milestone 2 Adversarial Challenge Report: Hard Domain Routing & Retrieval Bleed Prevention (R2)

**Verdict**: **`REQUEST_CHANGES`**  
**Role**: Empirical Challenger (`teamwork_challenger_m2`)  
**Date**: 2026-11-04  

---

## 1. Observation

### 1.1 Baseline Test Suite Execution (All Passing)
All existing test suites were executed using Python 3.12:
- **Command 1**: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
  - *Result*: **15 passed**, 44 deselected in 4.73s.
- **Command 2**: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v`
  - *Result*: **35 passed** in 6.44s.
- **Command 3**: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
  - *Result*: **10 passed**, 49 deselected in 4.09s.

### 1.2 Empirical Stress-Test Execution (`tests/test_adversarial_m2_harness.py`)
An independent empirical challenge harness was implemented in `tests/test_adversarial_m2_harness.py` (20 automated tests):
- **Command 4**: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m2_harness.py -v`
  - *Result*: **20 passed** in 2.93s.

### 1.3 Verified Protections
1. **Trouble-Token Immunity**:
   Adversarial queries combining uncovered keywords with trouble or procedural tokens were successfully intercepted as `Domain.UNCOVERED`, short-circuited in `RagRetriever.search()`, and cleanly refused in `backend.pipeline.run_pipeline()` with `confidence="low"`, zero citations, and zero search:
   - `"MCA21 portal SPICe+ registration payment failed refund pending"`
   - `"LPG cylinder subsidy stopped bank account mismatch"`
   - `"NSP scholarship status is defective notice under section 139(9)"`
   - `"Director identification number DIN verification delay in court"`
   - `"HP Gas domestic cylinder delivery delayed consumer court complaint"`
   - `"SPICe plus company incorporation ROC filing delay RTI application"`
   - `"National scholarship portal merit-cum-means Aadhaar biometric authentication failed error 330"`
2. **Boundary Discrimination (PMUY Ujjwala vs LPG)**:
   - `"PMUY Ujjwala 2.0 eligibility criteria"` correctly evaluates to `Domain.UNKNOWN` and retrieves authentic `PMUY Ujjwala - eligibility` chunks (8 hits).
   - General LPG refill/booking queries (e.g. `"How to book an LPG cylinder online through HP Gas?"`) are intercepted as `Domain.UNCOVERED` with 0 hits.

### 1.4 Critical Vulnerabilities & Empirical Reproductions

#### Vulnerability 1: Spacing and Hyphenation Brittleness in `_UNCOVERED_DOMAIN_PATTERNS`
In `backend/modules/domain_router.py:36-41`:
```python
    "nsp_scholarships": (
        re.compile(
            r"\b(?:nsp|national\s+scholarship\s+portal|pre-?matric\s+scholarship|post-?matric\s+scholarship|merit-?cum-?means|scholarship\s+disbursement|scholarship\s+scheme|scholarships\.gov\.in)\b",
            re.IGNORECASE,
        ),
    ),
```
- `pre-?matric` and `post-?matric` use `-?`, which matches an optional hyphen but **not** whitespace (`\s`).
- `merit-?cum-?means` requires hyphens.
- Queries without hyphens evaluate to `Domain.UNKNOWN`:
  * `"pre matric scholarship"` -> `Domain.UNKNOWN`
  * `"post matric scholarship"` -> `Domain.UNKNOWN`
  * `"merit cum means scholarship"` -> `Domain.UNKNOWN`
- Solid brand names in `petroleum_lpg` (`backend/modules/domain_router.py:30-35`) require whitespace (`bharat\s+gas`, `hp\s+gas`):
  * `"bharatgas online booking"` -> `Domain.UNKNOWN`
  * `"hpgas booking"` -> `Domain.UNKNOWN`

#### Vulnerability 2: Phrasing Gaps for Company Incorporation & Registration
In `backend/modules/domain_router.py:24-29`:
```python
re.compile(r"\b(?:...|incorporat(?:e|ion)\s+(?:of\s+)?company|private\s+limited\s+company|...)\b", re.IGNORECASE)
```
- The pattern `incorporat(?:e|ion)\s+(?:of\s+)?company` fails on:
  * `"how to incorporate a company in India"` (fails due to article `"a"`)
  * `"how to incorporate a new company"` (fails due to `"a new"`)
  * `"company incorporation process"` (fails due to reversed word order)
  * `"one person company registration"` (OPC / One Person Company omitted)
  * `"company registration online"` (company registration omitted)
  * `"llp registration process"` (LLP omitted)
- All of the above evaluate to `Domain.UNKNOWN`.

#### Vulnerability 3: Petroleum Queries with Standalone Cylinder or Cooking Gas
In `backend/modules/domain_router.py:30-35`:
- Fails to match:
  * `"cylinder delivery delay"` -> evaluates to `Domain.UNKNOWN`
  * `"cooking gas connection application"` -> evaluates to `Domain.UNKNOWN`
  * `"cooking gas subsidy"` -> evaluates to `Domain.UNKNOWN`

#### Vulnerability 4: Retriever Bypass via Caller-Passed `domain` Argument
In `backend/rag/retriever.py:68-83`:
```python
        resolved_domain: Domain = Domain.UNKNOWN
        if domain is not None:
            if isinstance(domain, Domain):
                resolved_domain = domain
            ...
        if resolved_domain == Domain.UNKNOWN:
            inferred = classify_domain(clean_query)
            if inferred == Domain.UNCOVERED:
                resolved_domain = inferred
```
- If any caller explicitly passes `domain=Domain.GENERAL_CIVIC` (or `Domain.TAXATION`), `resolved_domain` is set directly to that domain and the check `if inferred == Domain.UNCOVERED` is skipped.
- **Empirical test**: Calling `retriever.search("How to file SPICe+ Part A on MCA portal?", domain=Domain.GENERAL_CIVIC)` bypassed short-circuiting and returned 8 hits (`Help | MyGov`, `SEBI SCORES`, `Aadhaar IDENTITY VERIFICATION`).

#### Vulnerability 5: Real-World Consequences in `backend.pipeline.run_pipeline()`
When queries bypass `Domain.UNCOVERED` due to Vulnerabilities 1-3, `pipeline.py` falls back to live CRAG web search or nearest-neighbor RAG retrieval:
1. `run_pipeline("how to incorporate a new company")`:
   - Fell through to CRAG live web search on `incometax.gov.in`.
   - **Result**: `Confidence: high`, `Title: Official Civic Procedure (incometax.gov.in)`, hallucinates: *"Valid and Active PAN of the Company Step 2: Select Register as Taxpayer and enter the PAN of the company."*
2. `run_pipeline("cylinder delivery delay")`:
   - Trouble token `"delay"` coerced category to `"civic"`.
   - **Result**: `Confidence: high`, `Title: Centralized Public Grievance Redress and Monitoring System (CPGRAMS) Operating Guidelines`, cites RBI Banking TAT compensation rules for a gas cylinder.
3. `run_pipeline("bharatgas online booking")`:
   - Fell through to CRAG live web search on `pib.gov.in` (`Confidence: medium`).
4. `run_pipeline("pre matric scholarship")`:
   - Lexical retrieval retrieved RAG chunk `National Scholarship Portal - OTR and student application` (`Confidence: medium`).

---

## 2. Logic Chain

1. *From Obs 1.1*: Worker_m2's changes successfully resolve all predefined tests in `test_scenes_1_to_3_regression.py` and `test_domain_router.py`.
2. *From Obs 1.3*: The architecture of pre-retrieval classification and dynamic ungrounded refusal is sound for queries matching the current regex patterns.
3. *From Obs 1.4 (Vuln 1-3)*: Realistic citizen queries routinely use alternate word orders ("company incorporation"), spacing instead of hyphens ("pre matric scholarship"), solid brand names ("bharatgas"), or common synonyms ("cooking gas", "cylinder delivery delay").
4. *From Obs 1.4 (Vuln 5)*: Because these variants evaluate to `Domain.UNKNOWN`, they fail to trigger the uncovered short-circuit. In `pipeline.py`, they trigger CRAG web search (synthesizing wrong guidance with "high" confidence, e.g. incorporating a company on incometax.gov.in) or fall back to RAG nearest neighbors (citing RBI banking TAT for cylinder delivery).
5. *From Obs 1.4 (Vuln 4)*: In `retriever.py`, trusting caller-passed `domain` arguments without verifying `classify_domain(query) == Domain.UNCOVERED` allows bypass of the hard boundary.
6. *Direct Conclusion*: To satisfy the core objective of Milestone 2 (preventing RAG bleed and hallucination on uncovered domains), `_UNCOVERED_DOMAIN_PATTERNS` must be hardened against common citizen phrasing variations, and `RagRetriever.search()` must enforce the uncovered domain short-circuit unconditionally.

---

## 3. Caveats

- **PMUY Ujjwala 2.0 Boundary**: `PMUY Ujjwala - eligibility` is a verified official document in the corpus. Specific PMUY queries ("PMUY Ujjwala 2.0 eligibility", "PMUY application route") correctly retrieve PMUY documents. If queries include general LPG terms like "PMUY LPG connection", they are currently intercepted as uncovered. This is acceptable to prevent commercial LPG bleed, but regex expansions must avoid aggressively intercepting pure PMUY scheme queries.
- **Sub-Procedure Granularity**: Section 139(9) vs AIS feedback discrimination is owned by Milestone 3 (R6) and was not challenged here.

---

## 4. Conclusion & Required Changes

**Verdict**: **`REQUEST_CHANGES`**

### Required Action 1: Harden `_UNCOVERED_DOMAIN_PATTERNS` in `backend/modules/domain_router.py`
Update `_UNCOVERED_DOMAIN_PATTERNS` as follows:
```python
_UNCOVERED_DOMAIN_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "mca_spice": (
        re.compile(
            r"\b(?:"
            r"mca|mca21|spice\+?|spice\s+plus|roc|registrar\s+of\s+companies|"
            r"director\s+identification\s+number|\bdin\b|\bcin\b|corporate\s+affairs|"
            r"incorporat(?:e|ion)\s+(?:of\s+)?(?:a\s+|the\s+|new\s+)?company|"
            r"company\s+incorporat(?:e|ion)|company\s+registration|"
            r"private\s+limited\s+company|public\s+limited\s+company|"
            r"one\s+person\s+company|\bopc\b|\bllp\b|limited\s+liability\s+partnership|"
            r"inc-?29|inc-?32|dir-?3|mgt-?7"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    "petroleum_lpg": (
        re.compile(
            r"\b(?:"
            r"lpg|liquefied\s+petroleum|gas\s+cylinder|cylinder\s+booking|commercial\s+cylinder|"
            r"domestic\s+cylinder|indane|bharat\s*gas|hp\s*gas|omc|refill\s+booking|"
            r"subsidized\s+cylinder|pahal\b|dbtl|mopng|cooking\s+gas|gas\s+subsidy|gas\s+connection|"
            r"cylinder\s+(?:delivery|booking|refill|status|subsidy|agency|delay|delayed)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    "nsp_scholarships": (
        re.compile(
            r"\b(?:"
            r"nsp|national\s+scholarship\s+portal|"
            r"pre[-\s]?matric\s+scholarship|post[-\s]?matric\s+scholarship|"
            r"merit[-\s]cum[-\s]means|scholarship\s+disbursement|scholarship\s+scheme|"
            r"scholarship\s+(?:portal|application|status|registration)|"
            r"scholarships\.gov\.in"
            r")\b",
            re.IGNORECASE,
        ),
    ),
}
```

### Required Action 2: Unconditional Uncovered Check in `backend/rag/retriever.py`
In `RagRetriever.search()`, unconditionally check `classify_domain(clean_query)` at the very beginning of the method so that no caller-passed `domain` parameter can bypass the short-circuit:
```python
        # 1. Hard Domain Routing Short-Circuit for Uncovered Domains
        # Evaluate unconditionally on the query text to prevent domain spoofing
        if classify_domain(clean_query) == Domain.UNCOVERED or domain in (Domain.UNCOVERED, "uncovered"):
            return RetrievalResult(
                query=clean_query,
                hits=(),
                status="uncovered_domain",
                searched_documents=0,
            )
```

---

## 5. Verification Method

Once Worker M2 applies the changes:
1. Run all regression suites:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
   ```
2. Run the adversarial challenge harness:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m2_harness.py -v
   ```
3. Update `TestAdversarialSpellingAndTokenBypassFindings` in `tests/test_adversarial_m2_harness.py` to assert `domain == Domain.UNCOVERED` and verify all 10 previously failing queries now cleanly return `Domain.UNCOVERED`, 0 hits from `retriever.search()`, and honest refusal from `run_pipeline()`.

### Invalidation Conditions
- Any query involving company incorporation, cooking gas/cylinder delivery, or pre/post matric scholarships classifying as `Domain.UNKNOWN`.
- Any uncovered query returning non-zero hits or triggering web search in `run_pipeline()`.
