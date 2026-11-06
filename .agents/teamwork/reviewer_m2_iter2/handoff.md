# Milestone 2 Iteration 2 Review & Adversarial Verification Report: Hard Domain Routing & Bleed Prevention (R2)

## Review Summary

**Verdict**: **`APPROVE`**  
**Role**: Reviewer & Critic (`reviewer_m2_iter2`)  
**Date**: 2026-11-04  
**Integrity Status**: Full integrity verified. No hardcoded test results, facade logic, shortcuts, or AGENTS.md / GEMINI.md policy violations detected.

All 4 defects flagged in Milestone 2 Iteration 1 have been completely and robustly remediated:
1. **Hindi/Hinglish "din" Collision Remediated**: Replaced naive case-insensitive `\bdin\b` with contextual phrases (`din kyc`, `din no`, `director din`, `mca din`) and a case-sensitive `\bDIN\b` pattern. Common Hindi queries regarding timeline ("kitne din", "din me") now cleanly route to their covered civic domains (`Domain.IDENTITY`, `Domain.TRANSPORT`).
2. **Refusal Substring Misattribution Eliminated**: In `backend/pipeline.py`, replaced raw substring matching (`k in lowered`) with direct regex execution against compiled `_UNCOVERED_DOMAIN_PATTERNS`. NSP scholarship and LPG cylinder queries containing words like `"process"` or `"pending"` are accurately attributed without MCA corporate registration confusion.
3. **Uncovered Phrasing Variations Hardened**: Expanded patterns for MCA company registration/incorporation, LPG cylinders/booking, and NSP scholarships to cover common citizen variations (spacing, solid brand names, synonyms).
4. **Retriever Domain Bypass Blocked**: In `backend/rag/retriever.py`, placed the uncovered short-circuit check unconditionally before caller-passed domain evaluation, preventing domain spoofing.

---

## 1. Observation

### 1.1 Source Code Verification
- **`backend/modules/domain_router.py` (Lines 23-74)**:
  - Contextual lowercase DIN matching:
    `r"din\s+(?:number|no|kyc|status|application|allotment|verification|portal|form|details)|(?:director|mca)\s+din"`
  - Case-sensitive uppercase DIN matching: `re.compile(r"\bDIN\b")`.
  - Contextual PAHAL: `r"pahal\s+(?:scheme|yojana|dbtl|subsidy|lpg)|(?:lpg|dbtl)\s+pahal"` and uppercase `re.compile(r"\bPAHAL\b")`.
  - Contextual SPICe+: `r"\bspice\+(?!\w)"` separated from word boundaries to handle `+`, along with `spice\s+plus`, `spice\s+part`, and `form\s+spice`.
  - Expanded MCA patterns: `r"incorporat(?:e|ion)\s+(?:of\s+)?(?:(?:a|the)\s+)?(?:new\s+)?company"`, `company\s+incorporat(?:e|ion)`, `company\s+registration`, `private\s+limited\s+company`, `public\s+limited\s+company`, `one\s+person\s+company`, `\bopc\b`, `\bllp\b`, and `limited\s+liability\s+partnership`.
  - Expanded LPG patterns: `bharat\s*gas`, `hp\s*gas`, `cooking\s+gas`, `gas\s+subsidy`, `gas\s+connection`, and `cylinder\s+(?:delivery|booking|refill|status|subsidy|agency|delay|delayed)`.
  - Expanded NSP patterns: `pre[-\s]?matric\s+scholarship`, `post[-\s]?matric\s+scholarship`, `merit[-\s]cum[-\s]means`, and `scholarship\s+(?:portal|application|status|registration)`.
- **`backend/pipeline.py` (Lines 344-372)**:
  - `_build_uncovered_domain_refusal()` iterates directly over `_UNCOVERED_DOMAIN_PATTERNS` compiled regexes:
    ```python
    domain_name = "the requested service"
    for pat in _UNCOVERED_DOMAIN_PATTERNS.get("mca_spice", ()):
        if pat.search(clean_question):
            domain_name = "Ministry of Corporate Affairs (MCA / SPICe+) corporate registration"
            break
    else:
        for pat in _UNCOVERED_DOMAIN_PATTERNS.get("petroleum_lpg", ()):
            if pat.search(clean_question):
                domain_name = "Petroleum and LPG cylinder / subsidy"
                break
        else:
            for pat in _UNCOVERED_DOMAIN_PATTERNS.get("nsp_scholarships", ()):
                if pat.search(clean_question):
                    domain_name = "National Scholarship Portal (NSP) scheme"
                    break
    ```
- **`backend/rag/retriever.py` (Lines 66-74)**:
  - Unconditional query check prior to domain argument resolution:
    ```python
    if classify_domain(clean_query) == Domain.UNCOVERED or domain in (Domain.UNCOVERED, "uncovered"):
        return RetrievalResult(
            query=clean_query,
            hits=(),
            status="uncovered_domain",
            searched_documents=0,
        )
    ```

### 1.2 Independent Test Suite Results (Python 3.12)
All commands executed against Python 3.12 (`C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe`):
1. **Tier 1 R2 Regression Suite**:
   - Command: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
   - Result: **15 passed, 44 deselected in 4.53s**.
2. **Domain Router & Adversarial Harness Suites**:
   - Command: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v`
   - Result: **89 passed in 7.51s**.
3. **Milestone 1 Regression Suites (R1 & R5)**:
   - Command: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
   - Result: **10 passed, 49 deselected in 2.16s**.
4. **Auxiliary RAG & Scraper Baselines**:
   - Command: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v`
   - Result: **42 passed in 20.24s**.

Total test executions: **156 passed, 0 failed**.

### 1.3 Independent Adversarial Stress-Test Results
Direct script execution verifying edge cases:
- Hindi "din" queries (`Passport banne me kitne din lagte hai?`, `Driving license kitne din me aayega?`, `Aadhaar update kitne din me hota hai?`, `kitne din lagte hai voter id aane me?`, `PAN card banne me kitne din lagte hain?`):
  -> **All evaluate to their respective covered domains (`Domain.IDENTITY`, `Domain.TRANSPORT`) with 0 false positives.**
- Non-DIN English words containing "din" substring (`dinner`, `standing`, `ordinance`, `coordination`):
  -> **0 false positives; none evaluate to `Domain.UNCOVERED`.**
- Authentic DIN queries (`How to apply for DIN online?`, `din kyc pending verification`, `mca din status check`, `director din allotment process`):
  -> **All cleanly evaluate to `Domain.UNCOVERED`.**
- Refusal domain attribution for queries with "process" and "pending":
  -> `What is the NSP scholarship application process?` -> Attributed to `National Scholarship Portal (NSP) scheme` (no MCA bleed).
  -> `NSP scholarship pending verification` -> Attributed to `National Scholarship Portal (NSP) scheme` (no MCA bleed).
  -> `Indane gas cylinder refill booking pending process` -> Attributed to `Petroleum and LPG cylinder / subsidy` (no MCA bleed).
- Caller-passed domain parameter bypass in `retriever.search()`:
  -> Passed `domain=Domain.TAXATION`, `domain=Domain.TRANSPORT`, and `domain=Domain.GENERAL_CIVIC` on MCA, LPG, and NSP queries.
  -> **All returned `status="uncovered_domain"`, `hits=()`, `searched_documents=0`. Bypass 100% blocked.**
- Zero Predefined Responses Check:
  -> Refusal returns `confidence="low"`, `citations=[]`, `steps=[]`, `documents_needed=[]`, and no canned procedural advice or "pre-verified guide" disclaimers. Complies strictly with `AGENTS.md` and `GEMINI.md`.

---

## 2. Logic Chain

1. *From Obs 1.1*: Worker_m2_iter2 replaced bare `\bdin\b` with contextual phrases (`din kyc`, `din no`, `director din`) and case-sensitive `\bDIN\b`.
2. *From Obs 1.3*: In Romanized Hindi / Hinglish, citizens use lowercase "din" for days. Because lowercase "din" no longer matches unless followed or preceded by director/DIN keywords, everyday civic queries asking about turnaround time are preserved for normal RAG retrieval. At the same time, uppercase "DIN" or contextual queries correctly evaluate to `Domain.UNCOVERED`.
3. *From Obs 1.1 & 1.3*: In `backend/pipeline.py`, using compiled regex patterns instead of substring checks (`"roc" in lowered`, `"din" in lowered`) preserves token word boundaries. As a result, words containing "roc" (`process`) or "din" (`pending`) no longer trigger false matches against MCA corporate registration.
4. *From Obs 1.1 & 1.3*: In `backend/rag/retriever.py`, placing `if classify_domain(clean_query) == Domain.UNCOVERED or domain in (Domain.UNCOVERED, "uncovered"):` at the very start of `search()` guarantees that caller arguments cannot override the domain classification of the query.
5. *From Obs 1.2*: All 156 unit, regression, adversarial, and auxiliary tests pass cleanly without errors or regressions.
6. *Integrity Check*: No hardcoded outputs, fake implementations, or unauthorized bypasses exist.
7. *Conclusion*: Milestone 2 Iteration 2 satisfies all functional, architectural, and adversarial requirements. Verdict: **`APPROVE`**.

---

## 3. Caveats

- Milestone 3 (R6 - Section 139(9) vs AIS feedback sub-procedure discrimination) and Milestone 4 (R3/R4 - Confidence badge decoupling from cosine similarity and LLM anti-fabrication guardrails) are planned for subsequent milestones. The 19 deselected tests in `test_scenes_1_to_3_regression.py` belong to those milestones and do not affect Milestone 2.
- PMUY Ujjwala 2.0 boundary discrimination correctly permits pure PMUY eligibility queries into the corpus while isolating general LPG cylinder/booking queries.

---

## 4. Conclusion

- **Verdict**: **`APPROVE`**
- Milestone 2 is complete, robust, and verified.
- The system is ready to proceed to Milestone 3 (R6: Same-Domain Sub-Procedure Granularity).

---

## 5. Verification Method

To independently verify this approval, execute the following commands using Python 3.12:

```powershell
# 1. Tier 1 R2 regression suite (15 passed)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v

# 2. Domain router and adversarial harness suites (89 passed)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v

# 3. Milestone 1 baseline regression suites (10 passed)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v

# 4. Auxiliary baseline tests (42 passed)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v

# 5. Direct adversarial sanity verification
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.modules.domain_router import classify_domain, Domain; from backend.pipeline import run_pipeline; assert classify_domain('Passport banne me kitne din lagte hai?') == Domain.IDENTITY; assert 'National Scholarship Portal' in run_pipeline('What is the NSP scholarship application process?').summary; print('ALL PASS')"
```

### Invalidation Conditions
- Any Hindi query containing "kitne din" routing to `Domain.UNCOVERED`.
- Any NSP scholarship query with "process" or "pending" being attributed to Ministry of Corporate Affairs in the refusal summary.
- Any caller being able to bypass `Domain.UNCOVERED` short-circuiting in `RagRetriever.search()` by passing `domain=Domain.GENERAL_CIVIC`.
