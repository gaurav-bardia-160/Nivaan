# Challenger M1-1 Verification & Adversarial Stress Report (R1 & R5)

**Verdict**: `REQUEST_CHANGES`

---

## Challenge Summary

**Overall risk assessment**: **HIGH** (Regression test suite broken in CRAG boilerplate detection)

While the HTML table suppression via `trafilatura.extract(..., include_tables=False)` and BeautifulSoup noise tag handling is robust across complex nested and malformed tables, a defect was identified in `backend/web_search/fetcher.py`: the document catalog regex in `is_navigation_or_boilerplate_text()` is nested inside `if pipe_count >= 2:`. Any download catalog or document listing extracted without markdown pipes (such as plain text catalogs, span-based listings, or unpiped extracts) completely bypasses boilerplate detection and is falsely returned as valid civic text, causing `test_tier1_r5_pdf_directory_catalog_rejection` in `tests/test_scenes_1_to_3_regression.py` to FAIL.

---

## 1. Observation

### 1.1 Regression Failure in Existing Test Suite
Running the Tier 1 R5 regression suite:
```powershell
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_scenes_1_to_3_regression.py -k "test_tier1_r5" -v
```
**Verbatim Output**:
```
tests/test_scenes_1_to_3_regression.py::test_tier1_r5_trafilatura_extraction_tables_disabled PASSED [ 20%]
tests/test_scenes_1_to_3_regression.py::test_tier1_r5_markdown_table_rejection PASSED [ 40%]
tests/test_scenes_1_to_3_regression.py::test_tier1_r5_pdf_directory_catalog_rejection FAILED [ 60%]
tests/test_scenes_1_to_3_regression.py::test_tier1_r5_clean_prose_retained PASSED [ 80%]
tests/test_scenes_1_to_3_regression.py::test_tier1_r5_table_only_page_yields_empty_or_refusal PASSED [100%]

================================== FAILURES ===================================
________________ test_tier1_r5_pdf_directory_catalog_rejection ________________

    def test_tier1_r5_pdf_directory_catalog_rejection():
        """Verify is_navigation_or_boilerplate_text rejects PDF directory catalog text."""
        catalog_text = (
            "List of Acceptable Documents for Aadhaar Enrolment Language: English Version 11-06-2026 "
            "Format: PDFSize: 838.3 KB Compilation of Post Office Act Rules and Regulations"
        )
>       assert is_navigation_or_boilerplate_text(catalog_text) is True, (
            "is_navigation_or_boilerplate_text must return True for download directory catalog blocks"
        )
E       AssertionError: is_navigation_or_boilerplate_text must return True for download directory catalog blocks
E       assert False is True
E        +  where False = is_navigation_or_boilerplate_text('List of Acceptable Documents for Aadhaar Enrolment Language: English Version 11-06-2026 Format: PDFSize: 838.3 KB Compilation of Post Office Act Rules and Regulations')

tests\test_scenes_1_to_3_regression.py:498: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_scenes_1_to_3_regression.py::test_tier1_r5_pdf_directory_catalog_rejection
================= 1 failed, 4 passed, 54 deselected in 5.46s ==================
```

### 1.2 Root Cause in Implementation Code
In `backend/web_search/fetcher.py` (lines 205–216):
```python
    # Table & document catalog directory detection (Markdown tables, download matrices)
    pipe_count = text.count("|")
    has_step_indicators = bool(re.search(r"\b(?:step\s*\d+|steps|[a-g][\.\)]|\d+[\.\)]\s+[A-Z])\b", lowered))
    if pipe_count >= 2:
        # Markdown table separator e.g. |---| or |:---|
        if re.search(r"\|\s*[-:]{3,}\s*\|", text):
            return True
        # Document catalog indicators (Format: PDF, file sizes, download matrices)
        if re.search(r"\b(?:format\s*:\s*pdf|pdfsize|filesize|\d+(?:\.\d+)?\s*(?:kb|mb|gb)|size\s*:\s*\d+|download\s*\(|language\s*:\s*(?:english|hindi))\b", lowered):
            return True
        # Multiple table column delimiters without numbered/lettered procedural steps
        if pipe_count >= 3 and not has_step_indicators:
            return True
```
Because the document catalog check is indented under `if pipe_count >= 2:`, any text with `pipe_count < 2` (such as `catalog_text` with 0 pipes) skips this check entirely and reaches line 233, returning `False`.

### 1.3 Empirical Adversarial Stress Suite Results
We constructed and executed `tests/test_adversarial_m1_harness.py`:
```powershell
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_adversarial_m1_harness.py -v
```
**Results**:
- `TestNestedAndAdversarialTables::test_pure_nested_table_is_completely_suppressed`: **PASSED** (Nested tables and `colspan`/`rowspan` stripped).
- `TestNestedAndAdversarialTables::test_malformed_unclosed_table_tags`: **PASSED** (Malformed `<table>` without closing tags handled safely).
- `TestNestedAndAdversarialTables::test_mixed_procedural_page_with_nested_table`: **PASSED** (Narrative Steps 1–5 preserved, inner table stripped, synthesizer produced 5 clean steps without pipes).
- `TestBoilerplateDiscriminatorEdgeCases::test_catalog_without_pipes`: **FAILED** (`is_navigation_or_boilerplate_text()` returned `False`).
- `TestBoilerplateDiscriminatorEdgeCases::test_catalog_with_file_size_and_language`: **FAILED** (`is_navigation_or_boilerplate_text()` returned `False`).
- `TestBoilerplateDiscriminatorEdgeCases::test_false_positive_single_pipe_in_portal_title`: **PASSED** (Single pipe in title not rejected).
- `TestBoilerplateDiscriminatorEdgeCases::test_false_positive_two_pipes_in_document_list`: **PASSED** (Valid document choices with 2 pipes not rejected).
- `TestBoilerplateDiscriminatorEdgeCases::test_false_positive_numbered_steps`: **PASSED** (Numbered steps not rejected).
- `TestBoilerplateDiscriminatorEdgeCases::test_false_positive_letter_steps`: **PASSED** (Lettered steps not rejected).
- `TestBoilerplateDiscriminatorEdgeCases::test_markdown_table_variations`: **PASSED** (Standard, aligned, spaced markdown tables rejected).
- `TestSynthesizerInternalFilters::test_extractive_answer_filters_table_lines`: **PASSED** (Table rows omitted from extractive steps).
- `TestSynthesizerInternalFilters::test_select_focused_passages_omits_table_lines`: **PASSED** (Table rows omitted from LLM prompt excerpt).

### 1.4 Verification of Other Milestone 1 Elements
1. **R1 EPFO Corpus Authenticity**:
   - `tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1"`: 5 passed (100%).
   - `troubleshooting_civic.jsonl` Line 10 (`epfo_claim_passbook_cheque_standards_01`): Authenticated official circular `WSU_IssueOfBKG_49885_16.pdf` on `www.epfindia.gov.in`.
   - Records 8 and 9 contain verified SOP content matching titles.
2. **Qdrant Vector Database**:
   - `python -m backend.offline.ensure_vector_db --check-only`: `ready: true`, `points: 1387`, `corpus_sha256: 5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6`.
3. **Milestone 1 Core Unit Tests**:
   - `pytest tests/test_web_search.py tests/test_rag_loader.py tests/test_build_vector_db.py`: 38 passed.

---

## 2. Logic Chain

1. **Observation 1.1 & 1.2**: In `tests/test_scenes_1_to_3_regression.py`, `test_tier1_r5_pdf_directory_catalog_rejection` tests:
   ```python
   catalog_text = (
       "List of Acceptable Documents for Aadhaar Enrolment Language: English Version 11-06-2026 "
       "Format: PDFSize: 838.3 KB Compilation of Post Office Act Rules and Regulations"
   )
   assert is_navigation_or_boilerplate_text(catalog_text) is True
   ```
2. In `backend/web_search/fetcher.py`, line 207 guards document catalog detection behind `if pipe_count >= 2:`.
3. `catalog_text` contains 0 `|` characters (`pipe_count == 0`), which evaluates `pipe_count >= 2` to `False`.
4. As a result, the document catalog regular expression (`format\s*:\s*pdf|pdfsize|filesize...`) is never evaluated.
5. Because `catalog_text` also lacks navigation noise phrases like "skip to navigation", `noise_count` is 0.
6. The function falls through to line 233 and returns `False` instead of `True`.
7. This causes an `AssertionError` in `test_tier1_r5_pdf_directory_catalog_rejection` and allows unpiped document catalog noise to pass into CRAG synthesis.
8. Therefore, the implementation in `backend/web_search/fetcher.py` fails acceptance criteria for R5 and must be remediated.

---

## 3. Caveats

1. **FastEmbed CPU Runtime**: Full vector database rebuild takes ~14 minutes; verification was performed using `--check-only`, which validated point count (1387) and SHA256 checksum in ~1 second.
2. **Review-Only Constraint**: In accordance with the Teamwork constraint ("Review-only — do NOT modify implementation code"), challenger did not edit `backend/web_search/fetcher.py`. The required fix is documented below for worker remediation.

---

## 4. Conclusion & Required Mitigation

**Verdict**: `REQUEST_CHANGES`

### Required Fix in `backend/web_search/fetcher.py`
Decouple document catalog detection from `pipe_count >= 2`. When a text lacks procedural step indicators (`has_step_indicators is False`), any document catalog indicators (`format: pdf`, `pdfsize`, `filesize`, `\d+ (?:kb|mb|gb)`, `download (`, etc.) must immediately classify the text as boilerplate:

```python
    # Table detection via markdown table separators or high pipe density
    if pipe_count >= 2:
        if re.search(r"\|\s*[-:]{3,}\s*\|", text):
            return True
        if pipe_count >= 3 and not has_step_indicators:
            return True

    # Document catalog indicators without procedural steps (regardless of pipes)
    if not has_step_indicators and re.search(
        r"\b(?:format\s*:\s*pdf|pdfsize|filesize|\d+(?:\.\d+)?\s*(?:kb|mb|gb)|size\s*:\s*\d+|download\s*\(|language\s*:\s*(?:english|hindi))\b",
        lowered,
    ):
        return True
```

This fix preserves legitimate procedural steps that mention file downloads (because `has_step_indicators` will be `True`), while correctly rejecting document directory listings whether formatted with or without markdown pipes.

---

## 5. Verification Method

To verify the failure and subsequent fix:

1. **Run the failing regression test**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_scenes_1_to_3_regression.py -k "test_tier1_r5_pdf_directory_catalog_rejection" -v
   ```
   *Current Result*: FAILED (`assert False is True`).
   *Expected Post-Fix*: PASSED.

2. **Run the adversarial challenge suite**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_adversarial_m1_harness.py -v
   ```
   *Current Result*: 10 passed, 2 failed.
   *Expected Post-Fix*: 12 passed, 0 failed.

3. **Run all Tier 1 R5 regression tests**:
   ```powershell
   & "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_scenes_1_to_3_regression.py -k "test_tier1_r5" -v
   ```
   *Expected Post-Fix*: 5 passed, 0 failed.
