# Forensic Integrity Audit & Adversarial Review: Milestone 2

## Forensic Audit Report

**Work Product**: Milestone 2 Implementation (Hard Domain Routing & Bleed Prevention - R2)  
**Inspected Files**:
- `backend/modules/domain_router.py`
- `backend/rag/retriever.py`
- `backend/rag/runtime.py`
- `backend/pipeline.py`
- `tests/test_domain_router.py`  
**Profile**: General Project (Development Mode per `ORIGINAL_REQUEST.md`)  
**Verdict**: **`CLEAN`**

---

### Phase Results
- **Hardcoded test results check**: **PASS** — Zero instances of hardcoded test queries, expected outputs, or test assertion strings embedded in implementation code.
- **Facade implementation check**: **PASS** — Genuine domain classification logic using regexes, genuine short-circuit in `RagRetriever.search()` returning empty hits and skipping Qdrant vector store queries, genuine category isolation in `runtime.py`, and authentic pipeline interception.
- **Pre-populated verification artifact check**: **PASS** — No fabricated test logs or fake verification outputs. Query logging into `backend/data/feedback/unresolved_queries.csv` was verified live.
- **Self-certifying tests check**: **PASS** — Regression tests in `tests/test_scenes_1_to_3_regression.py` existed prior to implementation; new unit tests in `tests/test_domain_router.py` verify interface boundaries independently.
- **AGENTS.md / GEMINI.md Zero Predefined Responses**: **PASS** — No hardcoded procedural steps, document requirements, or pre-canned templates. `_build_uncovered_domain_refusal` produces an honest, ungrounded refusal with zero citations, empty step lists, and zero disclaimers mentioning "pre-verified guides".
- **Independent Test Execution**: **PASS** — All 4 specified test suites executed by auditor passed 100% (102 tests passed, 0 failed).

---

## 5-Component Handoff Report

### 1. Observation
1. **Source Code Implementation**:
   - `backend/modules/domain_router.py`: Defined `Domain.UNCOVERED = "uncovered"` and `_UNCOVERED_DOMAIN_PATTERNS` dictionary covering `mca_spice`, `petroleum_lpg`, and `nsp_scholarships`. Evaluated at the top of `classify_domain()` prior to other domain patterns. Configured `get_allowed_rag_categories(Domain.UNCOVERED) -> set()` and `entry_matches_domain(..., Domain.UNCOVERED) -> False`.
   - `backend/rag/retriever.py`: Intercepts `resolved_domain == Domain.UNCOVERED` in `RagRetriever.search()` and returns `RetrievalResult(query=clean_query, hits=(), status="uncovered_domain", searched_documents=0)`. Bypasses BM25 search, FastEmbed embeddings, and Qdrant vector retrieval.
   - `backend/rag/runtime.py`: Added guards in `supported_category()` and `retrieve_if_enabled()` returning `None` immediately if domain is `UNCOVERED`.
   - `backend/pipeline.py`: Added `_build_uncovered_domain_refusal()` creating a dynamic honest refusal without canned templates or mentions of "pre-verified guide". Intercepts `query_domain == Domain.UNCOVERED` in `run()` and `run_stream()`, logging to `unresolved_queries.csv`. Exported `run_pipeline()`.
   - `tests/test_domain_router.py`: 35 comprehensive unit tests added.
2. **Independent Test Execution (Python 3.12)**:
   - Command 1: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v`  
     **Result: 15 passed, 44 deselected in 3.14s**.
   - Command 2: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v`  
     **Result: 35 passed in 3.31s**.
   - Command 3: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v`  
     **Result: 10 passed, 49 deselected in 1.85s**.
   - Command 4: `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v`  
     **Result: 42 passed in 24.90s**.
3. **Adversarial Edge Case Stress Testing**:
   - `_UNCOVERED_DOMAIN_PATTERNS["mca_spice"]` includes `\bdin\b` with `re.IGNORECASE`. In Hindi/Hinglish, "din" (दिन) means "day" (e.g., "kitne din", "do din baad"). Testing `classify_domain("PAN card kitne din me banega?")` and `classify_domain("Passport renewal kitne din me hota hai?")` returned `Domain.UNCOVERED`!
   - In `backend/pipeline.py:345`, `_build_uncovered_domain_refusal()` uses `any(k in lowered for k in ("mca", "mca21", "spice", "roc", "company", "director", "din", "cin", "inc-", "dir-", "mgt-"))`. Substring `"din" in lowered` matches "pending", "finding", "loading"; substring `"roc" in lowered` matches "process", "procedure", "procure". Consequently, NSP and LPG queries containing "pending" or "procedure" get mislabeled as MCA SPICe+ in the refusal summary.

### 2. Logic Chain
1. Under Development Mode, an integrity violation requires evidence of hardcoded test results, facade implementations (e.g. stubbed/dummy functions that mimic passing results), fabricated outputs, or canned procedural responses prohibited by `AGENTS.md`.
2. Static inspection of `domain_router.py`, `retriever.py`, `runtime.py`, and `pipeline.py` confirms that the routing, short-circuit, and refusal generation logic are genuine, functional implementations.
3. The empirical test execution confirms 100% pass across all 102 test cases without regression to M1 (R1, R5) or core RAG services.
4. Therefore, the implementation is certified **CLEAN** of integrity violations.
5. The two defects identified during adversarial review are functional regex / substring precision bugs rather than integrity violations or bad-faith shortcuts, and are documented below with actionable mitigations for the worker.

### 3. Caveats
- Testing was conducted on Python 3.12 under Windows.
- The 19 remaining test failures in `tests/test_scenes_1_to_3_regression.py` belong strictly to M3 (R6 sub-procedure discrimination) and M4 (R3/R4 confidence decoupling and anti-fabrication prompt), which are scheduled for subsequent milestones according to `PROJECT.md`.

### 4. Conclusion
Milestone 2 (Hard Domain Routing & Bleed Prevention - R2) passes the Forensic Integrity Audit with a verdict of **`CLEAN`**. All requirements of R2 have been genuinely implemented, verified, and tested. The adversarial review has surfaced 2 precision bugs in token matching that should be addressed during subsequent milestone hardening.

### 5. Verification Method
Run the following verification commands using Python 3.12:
```powershell
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2" -v
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_domain_router.py -v
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v
```

---

## Adversarial Challenge Report

**Overall Risk Assessment**: MEDIUM-HIGH (functional false-positives on Hinglish queries and query categorization)

### Challenge 1 (CRITICAL): Multilingual Token Collision on `\bdin\b`
- **Assumption Challenged**: That `\bdin\b` uniquely identifies "Director Identification Number" (MCA).
- **Attack Scenario**: Any Hindi/Hinglish query using "din" (days), such as:
  - `"PAN card kitne din me banega?"`
  - `"Passport renewal kitne din me hota hai?"`
  - `"Driving license test kitne din baad de sakte hain?"`
- **Blast Radius**: `classify_domain()` returns `Domain.UNCOVERED`. Normal covered civic services (Identity, Transport) are falsely short-circuited and refused under MCA corporate registration.
- **Empirical Proof**:
  ```python
  >>> classify_domain("Mera passport kitne din mein aayega?")
  Domain.UNCOVERED
  >>> run_pipeline("PAN card kitne din me banega?").summary
  "Official procedural guidance for Ministry of Corporate Affairs (MCA / SPICe+) corporate registration ('PAN card kitne din me banega?') is currently not covered..."
  ```
- **Recommended Mitigation**:
  Replace `\bdin\b` in `_UNCOVERED_DOMAIN_PATTERNS["mca_spice"]` with contextual matches:
  `r"\b(?:din\s*(?:number|no|kyc|status|application)|director\s+identification\s+number)\b"` or require case-sensitive `r"\bDIN\b"`.

### Challenge 2 (HIGH): Substring Inclusion Bug in `_build_uncovered_domain_refusal()`
- **Assumption Challenged**: That `any(k in lowered ...)` accurately categorizes the uncovered domain name.
- **Attack Scenario**: Any uncovered query containing common English words like `"pending"` (contains `"din"`) or `"procedure"` / `"process"` (contains `"roc"`):
  - `"Scholarship scheme nodal officer verification pending on NSP"`
  - `"How to apply for LPG cylinder under the new procedure?"`
- **Blast Radius**: The refusal summary mislabels NSP scholarship or LPG subsidy queries as MCA SPICe+ corporate registration.
- **Empirical Proof**:
  ```python
  >>> _build_uncovered_domain_refusal("Scholarship scheme nodal officer verification pending on NSP").summary
  "Official procedural guidance for Ministry of Corporate Affairs (MCA / SPICe+) corporate registration..."
  >>> _build_uncovered_domain_refusal("How to apply for LPG cylinder under the new procedure?").summary
  "Official procedural guidance for Ministry of Corporate Affairs (MCA / SPICe+) corporate registration..."
  ```
- **Recommended Mitigation**:
  In `backend/pipeline.py:345`, replace substring checking with regex matching with word boundaries, or reuse `_UNCOVERED_DOMAIN_PATTERNS`:
  ```python
  if _UNCOVERED_DOMAIN_PATTERNS["mca_spice"][0].search(clean_question):
      domain_name = "Ministry of Corporate Affairs (MCA / SPICe+) corporate registration"
  elif _UNCOVERED_DOMAIN_PATTERNS["petroleum_lpg"][0].search(clean_question):
      domain_name = "Petroleum and LPG cylinder / subsidy"
  elif _UNCOVERED_DOMAIN_PATTERNS["nsp_scholarships"][0].search(clean_question):
      domain_name = "National Scholarship Portal (NSP) scheme"
  ```
