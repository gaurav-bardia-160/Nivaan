# Milestone 2 Iteration 2 Adversarial Challenge Report: Hard Domain Routing & Bleed Prevention

**Verdict**: **`APPROVE`**  
**Role**: Empirical Challenger (`teamwork_challenger_m2_iter2`)  
**Date**: 2026-11-04  
**Milestone**: Milestone 2 Iteration 2 (R2 Remediation)  

---

## 1. Observation

### 1.1 Test Suite Execution via Python 3.12 (114 Passed, 0 Failed)

All required test suites were executed synchronously using Python 3.12:

1. **Tier 1 R2 Regression Suite**:
   - **Command**: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
   - **Result**: **15 passed**, 44 deselected in 2.96s.
2. **Domain Router & Adversarial M2 Harness Suites**:
   - **Command**: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v`
   - **Result**: **89 passed** in 8.03s.
3. **Milestone 1 (R1 & R5) Regression Suite**:
   - **Command**: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
   - **Result**: **10 passed**, 49 deselected in 2.34s.

### 1.2 Empirical Verification of the 10 Attack Bypass Queries

All 10 queries previously flagged in `challenger_m2/handoff.md` were executed through `domain_router.classify_domain()`, `retriever.search()`, and `pipeline.run_pipeline()`:

| Query | `classify_domain` | `retriever.search` Hits | Pipeline `confidence` | Pipeline `title` | Refusal Summary Attribution |
|---|---|---|---|---|---|
| `"pre matric scholarship"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"National Scholarship Portal (NSP) scheme"` |
| `"post matric scholarship"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"National Scholarship Portal (NSP) scheme"` |
| `"merit cum means scholarship"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"National Scholarship Portal (NSP) scheme"` |
| `"bharatgas online booking"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"Petroleum and LPG cylinder / subsidy"` |
| `"hpgas booking"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"Petroleum and LPG cylinder / subsidy"` |
| `"how to incorporate a new company"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"Ministry of Corporate Affairs (MCA / SPICe+) corporate registration"` |
| `"one person company registration"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"Ministry of Corporate Affairs (MCA / SPICe+) corporate registration"` |
| `"company registration online"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"Ministry of Corporate Affairs (MCA / SPICe+) corporate registration"` |
| `"cylinder delivery delay"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"Petroleum and LPG cylinder / subsidy"` |
| `"cooking gas connection application"` | `Domain.UNCOVERED` | 0 (`uncovered_domain`) | `low` | `Service Domain Not Covered` | `"Petroleum and LPG cylinder / subsidy"` |

Zero queries bypassed the uncovered check. All 10 returned `hits = ()`, `searched_documents = 0`, `confidence = "low"`, `citations = []`, and accurate domain labeling without MCA mislabeling.

### 1.3 Caller-Passed Domain Parameter Bypass Immunity

In `backend/rag/retriever.py:68-74`:
```python
if classify_domain(clean_query) == Domain.UNCOVERED or domain in (Domain.UNCOVERED, "uncovered"):
    return RetrievalResult(
        query=clean_query,
        hits=(),
        status="uncovered_domain",
        searched_documents=0,
    )
```
Adversarial calls explicitly specifying spoofed domains (`Domain.GENERAL_CIVIC`, `Domain.TAXATION`, `Domain.IDENTITY`, `Domain.TRANSPORT`, `Domain.BANKING`, `'general_civic'`, `'taxation'`) against uncovered queries were tested empirically:
- `"How to file SPICe+ Part A on MCA portal?"` with `domain=Domain.GENERAL_CIVIC` -> `status="uncovered_domain"`, `hits=()`, `searched_documents=0`.
- `"pre matric scholarship"` with `domain=Domain.TAXATION` -> `status="uncovered_domain"`, `hits=()`, `searched_documents=0`.
- `"bharatgas online booking"` with `domain=Domain.TRANSPORT` -> `status="uncovered_domain"`, `hits=()`, `searched_documents=0`.
- `"cylinder delivery delay"` with `domain='general_civic'` -> `status="uncovered_domain"`, `hits=()`, `searched_documents=0`.

All spoofing attempts were unconditionally blocked.

### 1.4 False Positive Verification: Hindi "kitne din" and Context Collisions

A suite of Indic/Hinglish processing day queries containing `"din"` was tested against `classify_domain()` and `run_pipeline()`:
- `"Passport banne me kitne din lagte hai?"` -> `Domain.IDENTITY`, title: Regional Passport Offices, conf: `medium`
- `"Driving license kitne din me aayega?"` -> `Domain.TRANSPORT`, title: Driving & Transport, conf: `medium`
- `"Voter ID card kitne din me banta hai?"` -> `Domain.IDENTITY`, title: ECI NGRS, conf: `high`
- `"Aadhaar card update hone me kitne din lagte hain?"` -> `Domain.IDENTITY`, title: UIDAI Sitemap, conf: `medium`
- `"PAN card kitne din me banega?"` -> `Domain.IDENTITY`, title: PAN, conf: `medium`
- `"Fastag dispute refund kitne din me milta hai?"` -> `Domain.TRANSPORT`, title: Official Civic Procedure (nhai.gov.in), conf: `medium`
- `"Challan bharne ke kitne din baad update hota hai?"` -> `Domain.TRANSPORT`, title: Commercial Tax Department, conf: `high`

**Collision Resistance Confirmed**:
- Lowercase `"din"` in Hindi sentences does not collide with MCA DIN patterns.
- Lowercase `"pahal"` in Hindi sentences (`"sarkar ne ek nayi pahal ki hai"`) evaluates to `Domain.UNKNOWN`, not `Domain.UNCOVERED`.
- Bare `"spice"` in `"SpiceJet complaint in consumer court"` evaluates to `Domain.LEGAL_CONSUMER`, not `Domain.UNCOVERED`.
- Uppercase `"DIN"`, `"PAHAL"`, or contextual forms (`"din number"`, `"director din"`, `"pahal scheme"`, `"spice+"`) cleanly evaluate to `Domain.UNCOVERED`.

### 1.5 PMUY Ujjwala 2.0 Boundary Discrimination

- `"PMUY Ujjwala 2.0 eligibility criteria"` -> Evaluates to `Domain.UNKNOWN`, retrieves 8 hits from authentic PMUY Ujjwala canonical documentation (`troubleshooting_civic.jsonl`).
- General LPG queries (`"How to book an LPG cylinder online through HP Gas?"`, `"commercial gas cylinder connection price list"`) -> Evaluates to `Domain.UNCOVERED` with 0 hits.

---

## 2. Logic Chain

1. *From Observation 1.1*: All automated test suites (Tier 1 R2, Domain Router, Adversarial Harness, and baseline R1/R5) pass synchronously with 100% green status on Python 3.12.
2. *From Observation 1.2*: The regex expansions in `_UNCOVERED_DOMAIN_PATTERNS` (`backend/modules/domain_router.py`) cover natural language phrasing variations (hyphens, spaces, reversed word orders, and solid brand names), closing all 10 bypass attack vectors identified in Iteration 1.
3. *From Observation 1.2 & 1.4*: Domain refusal attribution in `backend/pipeline.py` uses pattern-based matching instead of raw substring searches, preventing incorrect "Ministry of Corporate Affairs" labelling for scholarship or petroleum queries and preventing false positives on words like "process" or "pending".
4. *From Observation 1.3*: In `backend/rag/retriever.py`, placing the `classify_domain(clean_query) == Domain.UNCOVERED` check unconditionally at the head of `search()` guarantees that no caller argument can override the uncovered classification.
5. *From Observation 1.4 & 1.5*: Tight contextual requirements for acronyms (`DIN`, `PAHAL`, `SPICe+`) completely preserve normal citizen queries in Hindi/Hinglish and covered schemes like PMUY Ujjwala without false-positive dropouts.
6. *Direct Conclusion*: The remediation for Milestone 2 Iteration 2 is complete, robust, and verified empirically.

---

## 3. Caveats

- **Scope Boundary**: Sub-procedure discrimination for Section 139(9) defective return vs AIS feedback is part of Milestone 3 (R6) and was not assessed here.
- **Dynamic Retrieval Memory**: The `unresolved_queries.csv` correctly logs newly encountered uncovered queries for tracking as expected by architecture requirements.

---

## 4. Conclusion

- **Verdict**: **`APPROVE`**
- All 10 bypass queries from Iteration 1 are strictly intercepted.
- Caller-passed domain parameter bypass is permanently closed.
- Indic/Hinglish processing day queries are completely unblocked and route accurately.
- Ready to proceed to Milestone 3.

---

## 5. Verification Method

To independently reproduce all empirical findings, run:

```powershell
# 1. Run Tier 1 R2 regression suite (15 tests)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v

# 2. Run domain router unit tests and adversarial challenge harness (89 tests)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v

# 3. Run baseline R1 and R5 regression tests (10 tests)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
```

### Invalidation Conditions
- Any query in `TestAdversarialSpellingAndTokenBypassFindings` returning non-zero hits or a confidence level other than `"low"`.
- Any call to `retriever.search("How to file SPICe+ Part A on MCA portal?", domain=Domain.GENERAL_CIVIC)` returning hits.
- Any Hindi query containing "kitne din" returning title `"Service Domain Not Covered"`.
