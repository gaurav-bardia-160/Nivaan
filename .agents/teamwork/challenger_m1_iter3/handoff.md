# Adversarial Verification & Stress Test Report: Milestone 1 Iteration 3

**Author**: `challenger_m1_iter3` (Empirical Challenger)  
**Task**: Independently challenge, stress-test, and verify Milestone 1 Iteration 3 implementation (EPFO corpus integrity, trafilatura scraper DOM noise filtering, pipeless catalog detection, and procedural step preservation).  
**Verdict**: **`APPROVE`**  
**Overall Risk Assessment**: **LOW** (All iteration 2 false-positive defects cleanly resolved; 100% test pass rate across 86 automated tests and 16 adversarial boundary scenarios).  
**Date**: 2026-11-04  

---

## 1. Observation

### 1.1 Direct Inspection of Implementation Code
In `backend/web_search/fetcher.py` (lines 205–233):
```python
    # Table & document catalog directory detection (Markdown tables, download matrices)
    pipe_count = text.count("|")
    has_step_indicators = bool(
        re.search(
            r"(?:\b(?:step\s*\d+|steps)\b|(?:\b\d+[\.\)]|\b[a-g][\.\)])(?:\s+|$))",
            lowered,
        )
    )
    if pipe_count >= 2:
        # Markdown table separator e.g. |---| or |:---|
        if re.search(r"\|\s*[-:]{3,}\s*\|", text):
            return True
        # Multiple table column delimiters without numbered/lettered procedural steps
        if pipe_count >= 3 and not has_step_indicators:
            return True

    step_verbs = (
        "visit ", "enter ", "click ", "select ", "submit ", "apply ", "login ",
        "register ", "dial ", "call ", "upload ", "download ", "verify ", "pay ", "fill ",
        "correct", "update", "form ",
    )
    verb_count = sum(1 for v in step_verbs if v in lowered)

    # Document catalog indicators (Format: PDF, file sizes, download matrices without procedural steps)
    if not has_step_indicators and verb_count <= 2 and re.search(
        r"\b(?:format\s*:\s*pdf|pdfsize|filesize|\d+(?:\.\d+)?\s*(?:kb|mb|gb)|size\s*:\s*\d+|download\s*\(|language\s*:\s*(?:english|hindi))\b",
        lowered,
    ):
        return True
```
- The dead code uppercase pattern `[A-Z]` has been removed.
- Punctuation word boundary failure has been fixed by matching whitespace or string end `(?:\s+|$)` rather than a trailing `\b` after `[\.\)]`.
- Action verb density guard `verb_count <= 2` is evaluated before catalog rejection, preventing procedural prose with form file size constraints from being misclassified as catalog noise.

### 1.2 Automated Test Suite Execution (Python 3.12)
Executed the 3 required test suites and verified 100% passing results:

1. **Tier 1 Regression Suite (R1 & R5)**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
   ```
   **Verbatim Result**: `10 passed, 49 deselected in 2.01s` (Exit Code 0).
   - `test_tier1_r1_epfo_manifest_allowlist` PASSED
   - `test_tier1_r1_epfo_joint_declaration_sop_authenticity` PASSED
   - `test_tier1_r1_epfo_closed_establishment_attestation_authenticity` PASSED
   - `test_tier1_r1_epfo_passbook_cheque_standards_source_validity` PASSED
   - `test_tier1_r1_epfo_no_pmvbry_boilerplate` PASSED
   - `test_tier1_r5_trafilatura_extraction_tables_disabled` PASSED
   - `test_tier1_r5_markdown_table_rejection` PASSED
   - `test_tier1_r5_pdf_directory_catalog_rejection` PASSED
   - `test_tier1_r5_clean_prose_retained` PASSED
   - `test_tier1_r5_table_only_page_yields_empty_or_refusal` PASSED

2. **Unit Test Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v
   ```
   **Verbatim Result**: `42 passed in 25.89s` (Exit Code 0).

3. **Milestone 1 Adversarial & Vector Bleed Suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m1_harness.py tests/test_adversarial_m1_2_epfo_vector.py -v
   ```
   **Verbatim Result**: `34 passed in 20.30s` (Exit Code 0).
   - 15 adversarial table & boilerplate discriminator tests passed.
   - 19 vector database integrity, document authenticity, and cross-domain bleed tests passed.

4. **Vector Database Status**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db --check-only
   ```
   **Verbatim Result**:
   ```json
   {
     "path": "C:\\Users\\gaura\\Documents\\nivaan\\backend\\data\\vector_index\\qdrant",
     "collection": "govbank_chunks",
     "expected_documents": 1387,
     "corpus_sha256": "5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6",
     "ready": true,
     "points": 1387,
     "dimensions": 384,
     "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
     "reason": "ready"
   }
   ```
   (Exit Code 0).

### 1.3 Empirical Re-Test of Iteration 2 Failure Scenarios
Directly executed all 6 attack scenarios that failed in iteration 2 against `is_navigation_or_boilerplate_text()` and `synthesize_from_web()`:

| Scenario | Input Snippet | Expected | Actual | Status |
|---|---|---|---|:---:|
| Numbered steps with file size | `1. Download Form 29 (PDF, 50 KB)... 2. Fill...` | `is_noise == False` | `False` | **PASS** |
| Lettered steps with file size | `a) Download Form 29 (PDF, 50 KB)... b) Fill...` | `is_noise == False` | `False` | **PASS** |
| Uppercase lettered steps with file size | `A. Download Form 1 (PDF, 100 KB)... B. Enter...` | `is_noise == False` | `False` | **PASS** |
| Numbered steps with checklist pipes | `Aadhaar \| Passport \| Voter ID \| DL \n 1. Visit...` | `is_noise == False` | `False` | **PASS** |
| Procedural prose with file size limits | `To apply for duplicate RC, visit Parivahan portal. Upload Aadhaar (scanned file size: 200 KB). Submit form and pay fee.` | `is_noise == False` | `False` | **PASS** |
| Pipeless catalog directory listing (Tier 1 R5) | `List of Acceptable Documents... Format: PDFSize: 838.3 KB` | `is_noise == True` | `True` | **PASS** |
| Catalog with download links and file sizes | `Circulars Archive: Download (PDF, 2 MB) \| Language: English` | `is_noise == True` | `True` | **PASS** |
| End-to-end CRAG synthesis on numbered DL guide | `synthesize_from_web('How to apply?', p1, 'https://parivahan.gov.in/dl')` | `len(steps) >= 3`, no refusal | `steps=3, refusal=False` | **PASS** |

### 1.4 Additional Adversarial Boundary Stress Test Matrix
Executed a standalone 16-case adversarial boundary matrix:
- Numbered with file size in MB (`2.5 MB`): `False` (PASS)
- Lettered with file size in KB (`150 KB`): `False` (PASS)
- Uppercase parenthesized `A)` with file size (`80 KB`): `False` (PASS)
- Multi-digit steps (`10.`, `11.`, `12.`): `False` (PASS)
- `Step 1:` prefix with file size: `False` (PASS)
- Procedural prose with action verb density > 2: `False` (PASS)
- Checklist with 2 pipes: `False` (PASS)
- Checklist with 4 pipes: `False` (PASS)
- Pure pipeless document catalog: `True` (PASS)
- Multi-item download catalog: `True` (PASS)
- Markdown table directory: `True` (PASS)
- Short text (< 40 chars): `True` (PASS)
- Empty text: `True` (PASS)
- Pure navigation noise without steps: `True` (PASS)
- Single noise phrase + valid numbered steps: `False` (PASS)
- Single noise phrase + procedural prose: `False` (PASS)

---

## 2. Logic Chain

1. **Premise**: In Milestone 1 Iteration 2, pipeless document catalog rejection caused an unintended side effect: legitimate numbered (`1.`) and lettered (`a)`) procedural guides mentioning downloadable files and file sizes were incorrectly flagged as boilerplate noise due to regex matching `[A-Z]` on lowercase text and trailing `\b` failure on punctuation.
2. **Verification of Remediation (Observation 1.1)**:
   - In `backend/web_search/fetcher.py`, `has_step_indicators` now uses:
     `r"(?:\b(?:step\s*\d+|steps)\b|(?:\b\d+[\.\)]|\b[a-g][\.\)])(?:\s+|$))"`.
   - Matching against `lowered` succeeds on all numbered steps (`1.`, `2.`, `10.`, `1)`) and lettered steps (`a)`, `b.`, `A)`, `B.`).
   - The addition of `verb_count = sum(1 for v in step_verbs if v in lowered)` and the `verb_count <= 2` guard ensures that even un-numbered procedural prose containing file size constraints (e.g. upload limits) is preserved because genuine procedural paragraphs contain multiple distinct action verbs (`visit`, `upload`, `submit`, `pay`, `form`).
   - Pipeless document catalogs lack procedural verbs (`verb_count <= 2`) and lack step indicators (`has_step_indicators == False`), matching catalog tokens (`Format: PDF`, `pdfsize`, `filesize`, `KB/MB`) and correctly returning `True` (noise).
3. **Evidence of Resolution (Observations 1.2, 1.3, 1.4)**:
   - All 86 automated regression, unit, and adversarial tests pass on Python 3.12 without failure.
   - All 6 failure scenarios from iteration 2 pass empirically.
   - All 16 adversarial boundary cases pass with exact expected classification.
   - In CRAG fallback synthesis, genuine government procedural guides generate extracted procedural steps (`len(steps) >= 3`) with zero refusal phrases, while catalog listings cleanly trigger the discriminator refusal without hallucinated steps.
4. **Deduction & Assessment**:
   Milestone 1's dual objectives — R1 (authentic EPFO corpus with verified circulars and Qdrant vector index) and R5 (`trafilatura` scraper DOM noise elimination and robust catalog/table discrimination without collateral damage to legitimate civic instructions) — are fully achieved and verified.

---

## 3. Caveats

- **No Caveats**: All test assertions were verified empirically via standalone executions and automated pytest runs on Python 3.12. The findings are 100% reproducible and stable.

---

## 4. Conclusion

**Verdict: `APPROVE`**

Milestone 1 is complete, resilient, and ready for integration into the main pipeline. The implementation in `backend/web_search/fetcher.py` cleanly decouples catalog detection from procedural step structures, eliminating DOM noise without false-positive suppression of civic procedural instructions.

---

## 5. Verification Method

To independently reproduce and verify this assessment:

```powershell
# 1. Tier 1 Regression Suite (10 passed)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v

# 2. Web Search & Loader Unit Test Suite (42 passed)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py -v

# 3. Milestone 1 Adversarial & Vector Bleed Suite (34 passed)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m1_harness.py tests/test_adversarial_m1_2_epfo_vector.py -v

# 4. Vector Database Readiness Check (ready: true, points: 1387)
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db --check-only

# 5. Standalone Empirical Check of Procedural Preservation & Catalog Rejection
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.web_search.fetcher import is_navigation_or_boilerplate_text; p = '1. Download Form 29 (PDF, 50 KB)\n2. Fill details\n3. Submit to RTO'; c = 'List of Documents Language: English Format: PDFSize: 838.3 KB'; assert not is_navigation_or_boilerplate_text(p); assert is_navigation_or_boilerplate_text(c); print('Preservation & Catalog Rejection Verified!')"
```

**Invalidation Conditions**:
The verdict `APPROVE` would be invalidated if:
- `is_navigation_or_boilerplate_text()` returns `True` for legitimate numbered or lettered procedures mentioning form downloads or file sizes.
- `is_navigation_or_boilerplate_text()` returns `False` for pipeless document catalog listings (`Format: PDFSize: 838.3 KB`).
- Any of the 86 automated tests fail.
- Vector database point count deviates from 1387 canonical safe corpus documents.
