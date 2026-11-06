# Milestone 2 Review and Adversarial Critique Report: Hard Domain Routing & Retrieval Bleed Prevention (R2)

## Review Summary

**Verdict**: **`REQUEST_CHANGES`**

While worker_m2 correctly implemented the architectural wiring required by Milestone 2 (the `Domain.UNCOVERED` enum, the short-circuiting in `RagRetriever.search()`, runtime isolation in `runtime.py`, honest dynamic refusals in `pipeline.py`, and logging to `unresolved_queries.csv`), independent adversarial testing identified **two major failure modes** that break production queries:
1. **Critical False-Positive Regression on Hindi/Hinglish Covered Queries**: Using case-insensitive `\bdin\b` to match Director Identification Number (DIN) causes EVERY Hindi/Hinglish query asking about days/timelines ("din" = दिन, e.g. *"Passport banne me kitne din lagte hai?"*, *"Driving license kitne din me aayega?"*, *"Aadhaar card update hone me kitne din lagte hain?"*) to be falsely classified as `Domain.UNCOVERED` (MCA corporate affairs), short-circuiting retrieval and issuing ungrounded refusals on core covered civic domains.
2. **Domain Mislabeling via Fragile Substrings in Refusal Generator**: `_build_uncovered_domain_refusal()` in `pipeline.py` uses substring checks `k in lowered` for 3-letter tokens like `"roc"` and `"din"`. As a result, valid NSP scholarship queries such as *"What is the NSP scholarship application process?"* match `"roc"` inside the word `"process"` (`p-roc-ess`) and tell the user: `"Official procedural guidance for Ministry of Corporate Affairs (MCA / SPICe+) corporate registration ('What is the NSP scholarship application process?')..."`

No integrity violations, facades, or test cheating were found. The changes are genuinely implemented, but these two failure modes must be remediated before Milestone 2 can be approved.

---

## Findings

### [Critical] Finding 1: Regex Keyword Collision with Hindi Word "Din" (दिन / Days)
- **What**: Case-insensitive `\bdin\b` in `_UNCOVERED_DOMAIN_PATTERNS["mca_spice"]` intercepts common Hindi/Hinglish citizen queries containing the word "din" (meaning "day" or "days").
- **Where**: `backend/modules/domain_router.py:26`
- **Why**:
  In India, asking about processing times in Hinglish using "kitne din" ("how many days") is standard citizen phrasing.
  Direct reproduction:
  ```python
  from backend.modules.domain_router import classify_domain
  classify_domain('Passport banne me kitne din lagte hai?')  # Returns Domain.UNCOVERED
  classify_domain('Driving license kitne din me aayega?')    # Returns Domain.UNCOVERED
  classify_domain('Voter ID card kitne din me banta hai?')   # Returns Domain.UNCOVERED
  classify_domain('Aadhaar card update hone me kitne din lagte hain?') # Returns Domain.UNCOVERED
  ```
  All of these core covered civic queries are completely blocked from RAG retrieval and web search, and return a refusal stating that MCA corporate registration is uncovered!
- **Suggestion**:
  Do NOT match bare lowercase `\bdin\b` case-insensitively. Match DIN specifically:
  - Require contextual tokens or explicit capitalization: e.g. `r"\b(?:director\s+identification\s+number|din\s+(?:number|kyc|status|application|allotment|verification|portal|form)|(?:director|mca)\s+din)\b"`
  - Or if using `\bDIN\b`, ensure case-sensitivity (only uppercase DIN, never lowercase `din`).

### [Major] Finding 2: Substring Collision in `_build_uncovered_domain_refusal()` Misattributes Queries to MCA
- **What**: In `backend/pipeline.py:345`, `_build_uncovered_domain_refusal()` identifies the domain name using raw substring search:
  `if any(k in lowered for k in ("mca", "mca21", "spice", "roc", "company", "director", "din", "cin", "inc-", "dir-", "mgt-")):`
- **Where**: `backend/pipeline.py:345-353`
- **Why**:
  `"roc"` is a substring of the common English word `"process"` (`p-roc-ess`).
  When an uncovered NSP query mentions "process" (e.g. *"What is the NSP scholarship application process?"*), the query is correctly classified as `Domain.UNCOVERED`, but `_build_uncovered_domain_refusal()` checks `"roc" in lowered`, matches `"process"`, and falsely labels the domain as:
  `"Official procedural guidance for Ministry of Corporate Affairs (MCA / SPICe+) corporate registration ('What is the NSP scholarship application process?')..."`
  Furthermore, `"din"` is a substring of `"pending"`, `"standing"`, `"coordination"`, and `"ordinance"`. An NSP query like *"NSP scholarship pending verification"* matches `"din"` inside `"pending"` and is also mislabeled as MCA!
- **Suggestion**:
  Do not use bare substring membership `k in lowered`.
  Instead:
  1. Have `classify_domain()` return the specific uncovered category key (`mca_spice`, `petroleum_lpg`, `nsp_scholarships`) or map directly to domain names.
  2. Or use regular expressions with word boundaries (`\broc\b`, `\bcin\b`) rather than substring `in`.

### [Minor] Finding 3: Secondary Keyword Collisions for "pahal" and "spice"
- **What**:
  - `petroleum_lpg`: `\bpahal\b` (case-insensitive) matches the common Hindi word "pahal" (पहल, meaning "initiative", e.g. *"Sarkar ki nayi shiksha pahal kya hai?"* -> returns `Domain.UNCOVERED`).
  - `mca_spice`: `spice\+?` has optional `\+?`, matching bare "spice" (e.g. *"Spice jet complaint in consumer court"* -> returns `Domain.UNCOVERED`).
- **Where**: `backend/modules/domain_router.py:26, 32`
- **Why**: Overly broad regex without mandatory scheme context triggers false-positive uncovered routing.
- **Suggestion**:
  - For PAHAL: require scheme context: `r"\b(?:pahal\s+(?:scheme|yojana|dbtl|subsidy|lpg)|(?:lpg|dbtl)\s+pahal|PAHAL)\b"`.
  - For SPICe+: require plus or form context: `r"\b(?:spice\+|spice\s+plus|spice\s+part|form\s+spice)\b"`.

---

## 1. Observation

1. **Independent Test Execution**:
   - Tier 1 R2 regression suite:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`
     -> **15 passed, 44 deselected in 3.46s** (100% pass on worker_m2's target tests).
   - Domain router unit tests:
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v`
     -> **35 passed in 3.42s** (100% pass).
   - Regression on previous milestones (R1 & R5):
     `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`
     -> **10 passed, 49 deselected in 1.74s** (100% pass).
   - Full auxiliary test suites (`test_web_search.py`, `test_rag_loader.py`, `test_build_vector_db.py`):
     -> **42 passed in 31.40s** (100% pass).

2. **Code Implementation Audit**:
   - `backend/modules/domain_router.py`:
     * `Domain.UNCOVERED = "uncovered"` is added to `Domain` enum (line 18).
     * `get_allowed_rag_categories(Domain.UNCOVERED)` returns `set()` (line 150).
     * `entry_matches_domain(..., Domain.UNCOVERED)` returns `False` (line 167).
     * `_UNCOVERED_DOMAIN_PATTERNS` evaluated first in `classify_domain()` (lines 133-136).
   - `backend/rag/retriever.py`:
     * `RagRetriever.search()` checks `resolved_domain == Domain.UNCOVERED` at lines 85-91 and immediately returns `RetrievalResult(query=clean_query, hits=(), status="uncovered_domain", searched_documents=0)`.
     * Vector store and BM25 index are completely bypassed. Verified via mock assertion in unit test.
   - `backend/rag/runtime.py`:
     * `supported_category` and `retrieve_if_enabled` check for `Domain.UNCOVERED` and return `None` (lines 107-108, 157-158).
   - `backend/pipeline.py`:
     * Intercepts `query_domain == Domain.UNCOVERED` at lines 427-442 (and 744-775 in `run_stream`), logs to `unresolved_queries.csv` via `log_unresolved_query()`, and generates dynamic refusal via `_build_uncovered_domain_refusal()`.
     * Convenience helper `run_pipeline` is exported at lines 1207-1215.

3. **Adversarial Reproduction of Failures**:
   - Command:
     `& python -c "from backend.modules.domain_router import classify_domain; print(classify_domain('Passport banne me kitne din lagte hai?'))"`
     Output: `Domain.UNCOVERED` (FAIL: Covered query hijacked).
   - Command:
     `& python -c "from backend.pipeline import run_pipeline; print(run_pipeline('What is the NSP scholarship application process?').summary)"`
     Output: `Official procedural guidance for Ministry of Corporate Affairs (MCA / SPICe+) corporate registration ('What is the NSP scholarship application process?') is currently not covered...` (FAIL: Mislabeled domain name due to "roc" in "process").

---

## 2. Logic Chain

1. *From Observation 1.1 & 1.2*: Worker_m2 successfully implemented all nominal requirements of R2. The tests designed for English phrases all pass, and the retriever short-circuit mechanism is architecturally sound.
2. *From Observation 1.2 & Finding 1*: In `backend/modules/domain_router.py:26`, `\bdin\b` was added under `re.IGNORECASE`. In the Romanized transliteration of Hindi / Hinglish, "din" means "day/days" (दिन). A user asking about turn-around time for any civic document will use the phrase "kitne din" or "din". Because `_UNCOVERED_DOMAIN_PATTERNS` is checked first before all other domains, any query containing "din" will immediately match `mca_spice` and evaluate to `Domain.UNCOVERED`.
3. *From Observation 1.2 & Finding 2*: In `backend/pipeline.py:345`, domain name labeling inside `_build_uncovered_domain_refusal()` performs raw substring matching (`k in lowered`). The acronym `"roc"` (Registrar of Companies) is a substring of `"process"`, and `"din"` is a substring of `"pending"`. When an NSP scholarship query uses standard procedural language such as "application process" or "pending status", it matches `"roc"` or `"din"` and falsely reports to the user that they asked for MCA corporate registration.
4. *Direct Deduction*: These regressions violate the core requirements of domain routing (which must isolate domains without collateral damage to covered domains) and provide factually inaccurate domain attribution in user-facing refusals.
5. *Integrity Audit*: No hardcoded bypasses, dummy facades, or test cheating were found. The flaws stem from regex overbreadth and substring fragility, not intentional manipulation.
6. *Direct Conclusion*: The architecture is approved in principle, but the implementation requires concrete fixes to regex patterns and refusal string parsing. Verdict: **`REQUEST_CHANGES`**.

---

## 3. Caveats

- Milestone 3 (R6 - AIS feedback vs Section 139(9) discrimination) and Milestone 4 (R3/R4 - Confidence decoupling & anti-fabrication) are currently pending in their respective milestones. The 19 failing tests in `test_scenes_1_to_3_regression.py` pertain strictly to those future milestones and are expected at this stage.
- Substring and regex improvements for DIN/PAHAL/SPICe+ will not require database re-indexing or vector schema migrations.

---

## 4. Conclusion

- **Verdict**: **`REQUEST_CHANGES`**
- Worker_m2 must apply the following specific remediations:
  1. In `backend/modules/domain_router.py`:
     - Replace `\bdin\b` in `_UNCOVERED_DOMAIN_PATTERNS["mca_spice"]` with contextual DIN patterns (e.g. `r"\b(?:director\s+identification\s+number|din\s+(?:number|kyc|status|application|allotment|verification|portal|form)|(?:director|mca)\s+din)\b"` or case-sensitive uppercase `r"\bDIN\b"`).
     - Replace `spice\+?` with `r"\b(?:spice\+|spice\s+plus|spice\s+part|form\s+spice)\b"`.
     - Replace `pahal\b` with `r"\b(?:pahal\s+(?:scheme|yojana|dbtl|subsidy|lpg)|(?:lpg|dbtl)\s+pahal|PAHAL)\b"`.
  2. In `backend/pipeline.py`:
     - In `_build_uncovered_domain_refusal()`, replace fragile substring checks (`"roc" in lowered`, `"din" in lowered`, `"cin" in lowered`) with word-boundary regex patterns or match against the uncovered pattern key directly.
  3. In `tests/test_domain_router.py`:
     - Add regression tests verifying that:
       * `"Passport banne me kitne din lagte hai?"` does NOT evaluate to `Domain.UNCOVERED`.
       * `"Driving license kitne din me aayega?"` does NOT evaluate to `Domain.UNCOVERED`.
       * `"What is the NSP scholarship application process?"` produces a refusal for NSP scholarship, NOT MCA corporate registration.
       * `"Spice jet complaint in consumer court"` does NOT evaluate to `Domain.UNCOVERED`.

---

## 5. Verification Method

Once worker_m2 applies the changes, run the following verification commands:

```powershell
# 1. Verify that Hinglish 'din' queries are not hijacked
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.modules.domain_router import classify_domain, Domain; assert classify_domain('Passport banne me kitne din lagte hai?') != Domain.UNCOVERED; assert classify_domain('Driving license kitne din me aayega?') != Domain.UNCOVERED; print('PASS: Hinglish din queries preserved')"

# 2. Verify that NSP process query does not output MCA corporate registration
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.pipeline import run_pipeline; ans = run_pipeline('What is the NSP scholarship application process?'); assert 'Ministry of Corporate Affairs' not in ans.summary; assert 'National Scholarship Portal' in ans.summary; print('PASS: NSP process domain correctly labeled')"

# 3. Run all Tier 1 R2 regression tests (all 15 must pass)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v

# 4. Run domain router unit tests (all unit tests must pass)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v

# 5. Run baseline non-regression suites
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v
```

### Invalidation Conditions
- Any query containing "kitne din" or "din" being classified as `Domain.UNCOVERED`.
- Any NSP scholarship query with "process" generating an MCA refusal summary.
- Any failure in the 15 Tier 1 R2 regression tests.
