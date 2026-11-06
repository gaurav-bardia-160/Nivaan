# Task Assignment: Milestone 2 Iteration 2 Remediation (Hard Domain Routing Hardening)

## Role
Milestone 2 Implementation Worker (Iteration 2)

## Working Directory
`c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2_iter2`

## Mandatory Files to Read First
1. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
3. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2\handoff.md` (Read Section: Findings & Suggestions)
4. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m2\handoff.md` (Read Section 4: Required Changes)
5. `c:\Users\gaura\Documents\nivaan\.agents\teamwork\auditor_m2\handoff.md`

## Write Ownership
- `backend/modules/domain_router.py`
- `backend/rag/retriever.py`
- `backend/pipeline.py`
- `tests/test_domain_router.py`
- `tests/test_adversarial_m2_harness.py`

## Defects to Remediate
### 1. Harden `_UNCOVERED_DOMAIN_PATTERNS` in `backend/modules/domain_router.py`
- **Fix Hindi "din" collision**: Replace bare case-insensitive `\bdin\b` with:
  `r"\b(?:director\s+identification\s+number|din\s+(?:number|no|kyc|status|application|allotment|verification|portal|form)|(?:director|mca)\s+din|\bDIN\b)\b"` (using case-sensitivity or contextual tokens). Ensure queries like `"Passport banne me kitne din lagte hai?"` and `"Driving license kitne din me aayega?"` return `Domain.UNKNOWN` (or covered domain), NOT `Domain.UNCOVERED`.
- **Fix Hindi "pahal" collision**: Require scheme context for PAHAL:
  `r"\b(?:pahal\s+(?:scheme|yojana|dbtl|subsidy|lpg)|(?:lpg|dbtl)\s+pahal|\bPAHAL\b)\b"`.
- **Fix "spice" collision**: Require plus/form context:
  `r"\b(?:spice\+|spice\s+plus|spice\s+part|form\s+spice)\b"` so "spice jet" is not intercepted.
- **Harden MCA patterns**:
  Include `incorporat(?:e|ion)\s+(?:of\s+)?(?:a\s+|the\s+|new\s+)?company`, `company\s+incorporat(?:e|ion)`, `company\s+registration`, `private\s+limited\s+company`, `public\s+limited\s+company`, `one\s+person\s+company`, `\bopc\b`, `\bllp\b`, `limited\s+liability\s+partnership`.
- **Harden Petroleum/LPG patterns**:
  Include `bharat\s*gas`, `hp\s*gas` (matches both "bharat gas" and "bharatgas"), `cooking\s+gas`, `gas\s+subsidy`, `gas\s+connection`, `cylinder\s+(?:delivery|booking|refill|status|subsidy|agency|delay|delayed)`.
- **Harden NSP patterns**:
  Include `pre[-\s]?matric\s+scholarship`, `post[-\s]?matric\s+scholarship`, `merit[-\s]cum[-\s]means`, `scholarship\s+(?:portal|application|status|registration|disbursement|scheme)`.

### 2. Fix Refusal Generator Substring Collision in `backend/pipeline.py`
In `_build_uncovered_domain_refusal()`:
- Do NOT use substring search `any(k in lowered for k in ("roc", "din", ...))` which matches `"process"` (contains `"roc"`) or `"pending"` (contains `"din"`).
- Instead, identify the uncovered domain using word boundaries or regex matching on `_UNCOVERED_DOMAIN_PATTERNS`, so that queries like `"What is the NSP scholarship application process?"` and `"NSP scholarship pending verification"` are correctly attributed to `"National Scholarship Portal (NSP)"`, NOT MCA corporate affairs.

### 3. Enforce Unconditional Short-Circuit in `backend/rag/retriever.py`
In `RagRetriever.search()`:
- Evaluate `classify_domain(clean_query) == Domain.UNCOVERED or domain in (Domain.UNCOVERED, "uncovered")` unconditionally at the very top of `search()`, so that callers passing `domain=Domain.GENERAL_CIVIC` cannot bypass the uncovered short-circuit.

### 4. Tests & Verification
- Augment tests in `tests/test_domain_router.py` and `tests/test_adversarial_m2_harness.py`:
  * Verify Hindi queries with "din" (e.g. `"Passport banne me kitne din lagte hai?"`) do NOT return `Domain.UNCOVERED`.
  * Verify spacing variations (`"pre matric scholarship"`, `"bharatgas online booking"`, `"how to incorporate a new company"`, `"cylinder delivery delay"`) return `Domain.UNCOVERED`.
  * Verify refusal messages in `run_pipeline()` correctly label the matched domain without substring confusion on `"process"` or `"pending"`.
  * Verify caller-passed `domain=Domain.GENERAL_CIVIC` cannot bypass uncovered short-circuit.
- Run all tests on Python 3.12:
  `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
  `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py tests/test_adversarial_m2_harness.py -v`
  `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
  `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v`

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Output
Write your handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2_iter2\handoff.md` and notify the orchestrator via `send_message`.


## 2026-11-04T17:31:21Z
Message from parent:
You are worker_m2_iter2.
Working directory: c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m2_iter2
Remediate the four findings in Milestone 2.
