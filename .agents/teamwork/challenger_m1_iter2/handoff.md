# Adversarial Verification & Stress Test Report: Pipeless Catalog Noise Rejection & Procedural Preservation (M1 Iteration 2)

**Author**: `challenger_m1_iter2` (Empirical Challenger)  
**Task**: Adversarially challenge and verify pipeless document catalog rejection and preservation of legitimate procedural steps in `backend/web_search/fetcher.py`.  
**Verdict**: **`REQUEST_CHANGES`**  
**Overall Risk Assessment**: **HIGH** (False Positive Rejection of Legitimate Numbered & Lettered Civic Procedures)  
**Date**: 2026-11-04  

---

## Challenge Summary

While `worker_m1_iter2` successfully decoupled the pipeless document catalog regex in `backend/web_search/fetcher.py` and resolved the regression failure in `test_tier1_r5_pdf_directory_catalog_rejection`, our adversarial stress testing revealed a **critical false-positive defect** in the procedural preservation guard:

In `backend/web_search/fetcher.py` line 206:
```python
has_step_indicators = bool(re.search(r"\b(?:step\s*\d+|steps|[a-g][\.\)]|\d+[\.\)]\s+[A-Z])\b", lowered))
```
1. **Dead Code / Impossible Match on Lowercase Input**: The regex branch `\d+[\.\)]\s+[A-Z]` is executed against `lowered` (`lowered = text.lower()`). Because all uppercase ASCII letters were converted to lowercase, `[A-Z]` NEVER matches in `lowered` (0% match rate).
2. **Broken Punctuation Word Boundary**: In regex, `\b` asserts a boundary between a word character (`\w`) and non-word character (`\W`). The branch `[a-g][\.\)]\b` matches a punctuation symbol `.` or `)`. When followed by normal whitespace (`\s`, also `\W`), there is no word boundary between `\W` and `\W`. Thus, standard lettered steps (`a) `, `b. `) fail the trailing `\b` assertion.
3. **Severe End-to-End Blast Radius**: Because `has_step_indicators` evaluates to `False` for ALL standard numbered (`1.`, `2.`, `3.`) and lettered (`a)`, `b)`) procedural lists, ANY legitimate government procedural guide mentioning a downloadable form with file size (e.g., `"1. Download Form 29 (PDF, 50 KB) from the Parivahan portal."`) triggers the decoupled catalog detector:
   ```python
   if not has_step_indicators and re.search(r"\b(?:format\s*:\s*pdf|pdfsize|filesize|\d+(?:\.\d+)?\s*(?:kb|mb|gb)...", lowered):
       return True
   ```
   and is **erroneously rejected as boilerplate noise**. In the live CRAG synthesis pipeline (`synthesizer.py`), this causes `synthesize_from_web()` to abort synthesis completely, returning `DISCRIMINATOR_FAILURE_PHRASE` and 0 steps.
4. **Blind Spot in Existing Harness**: The existing tests in `tests/test_adversarial_m1_harness.py` (`test_false_positive_numbered_steps` and `test_false_positive_letter_steps`) passed only because their test strings artificially omitted file sizes, download parentheses, or noise words. In both existing test fixtures, `has_step_indicators` was actually returning `False`.

---

## 1. Observation

### 1.1 Existing Test Suite Baseline
Ran the existing test suites to establish baseline status:

1. **Adversarial Harness Baseline** (`tests/test_adversarial_m1_harness.py`):
```powershell
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_adversarial_m1_harness.py -v
```
Output:
`12 passed in 4.14s` (100% passing).

2. **Tier 1 Regression Baseline** (`tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5"`):
```powershell
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5" -v
```
Output:
`10 passed, 49 deselected in 1.75s` (100% passing).

### 1.2 Inspection of Implementation Code
In `backend/web_search/fetcher.py` (lines 197–221):
```python
197: def is_navigation_or_boilerplate_text(text: str) -> bool:
198:     """Detect whether extracted text is purely navigation boilerplate, tables, or catalogs."""
199:     if not text or len(text.strip()) < 40:
200:         return True
201: 
202:     lowered = text.lower()
203: 
204:     # Table & document catalog directory detection (Markdown tables, download matrices)
205:     pipe_count = text.count("|")
206:     has_step_indicators = bool(re.search(r"\b(?:step\s*\d+|steps|[a-g][\.\)]|\d+[\.\)]\s+[A-Z])\b", lowered))
207:     if pipe_count >= 2:
208:         # Markdown table separator e.g. |---| or |:---|
209:         if re.search(r"\|\s*[-:]{3,}\s*\|", text):
210:             return True
211:         # Multiple table column delimiters without numbered/lettered procedural steps
212:         if pipe_count >= 3 and not has_step_indicators:
213:             return True
214: 
215:     # Document catalog indicators (Format: PDF, file sizes, download matrices without procedural steps)
216:     if not has_step_indicators and re.search(
217:         r"\b(?:format\s*:\s*pdf|pdfsize|filesize|\d+(?:\.\d+)?\s*(?:kb|mb|gb)|size\s*:\s*\d+|download\s*\(|language\s*:\s*(?:english|hindi))\b",
218:         lowered,
219:     ):
220:         return True
```

### 1.3 Direct Python Regex Verification
Executed verification commands to test the individual regex branches against `lowered` strings:

```python
import re

lowered_num = "1. download form 29 (pdf, 50 kb) from the parivahan portal."
lowered_let = "a) download form 29 (pdf, 50 kb) from the parivahan portal."

pat = r"\b(?:step\s*\d+|steps|[a-g][\.\)]|\d+[\.\)]\s+[A-Z])\b"

print(bool(re.search(pat, lowered_num)))  # Returns: False
print(bool(re.search(pat, lowered_let)))  # Returns: False
print(re.search(r"\b\d+[\.\)]\s+[A-Z]\b", lowered_num))  # Returns: None (0 matches on lowercased text)
print(re.search(r"\b[a-g][\.\)]\b", lowered_let))        # Returns: None (\b fails between ')' and space)
```

### 1.4 Empirical Adversarial Stress Test Execution
Executed empirical challenge harness against `backend.web_search.fetcher` and `backend.web_search.synthesizer`:

```python
from backend.web_search.fetcher import is_navigation_or_boilerplate_text
from backend.web_search.synthesizer import synthesize_from_web, DISCRIMINATOR_FAILURE_PHRASE

# Scenario 1: Numbered procedure with PDF download mention
p1 = """How to apply for duplicate Driving Licence online:
1. Download Form 29 (PDF, 50 KB) from the Parivahan portal.
2. Fill out vehicle registration details.
3. Submit the completed form to the jurisdictional RTO.
4. Pay statutory application fee of Rs 200."""

assert is_navigation_or_boilerplate_text(p1) is False  # FAILS! Returns True

# Scenario 2: Lettered procedure with PDF download mention
p2 = """How to apply for duplicate Driving Licence online:
a) Download Form 29 (PDF, 50 KB) from the Parivahan portal.
b) Fill out vehicle registration details.
c) Submit the completed form to the jurisdictional RTO.
d) Pay statutory application fee of Rs 200."""

assert is_navigation_or_boilerplate_text(p2) is False  # FAILS! Returns True

# Scenario 3: End-to-end CRAG synthesis on Scenario 1
res = synthesize_from_web("How to apply for duplicate Driving Licence?", p1, "https://parivahan.gov.in/dl")
print(res.summary)
# Verbatim Output:
# "Live search failed to extract the procedural text from the official portal. Please visit the official portal directly at https://parivahan.gov.in/dl to view the statutory procedure."
# res.steps count: 0 (Expected: 4 steps)
```

---

## 2. Logic Chain

1. **Premise**: In Milestone 1 Iteration 2, `is_navigation_or_boilerplate_text()` decoupled document catalog detection from `pipe_count >= 2` so that pipeless catalog listings (e.g. `Format: PDFSize: 838.3 KB`) are rejected.
2. **Constraint & Requirement**: Legitimate procedural instructions mentioning downloadable forms and file sizes must NOT be classified as boilerplate.
3. **Observation 1.2 & 1.3**: The procedural protection relies entirely on `has_step_indicators`.
4. **Observation 1.3**:
   - `\d+[\.\)]\s+[A-Z]` can NEVER match on `lowered = text.lower()` because `lowered` contains no uppercase characters.
   - Even without case sensitivity, trailing `\b` requires a word boundary immediately after the first character of the next word, failing on any word with more than one character (e.g., `1. d` in `1. download` is followed by `o`, so there is no word boundary).
   - `[a-g][\.\)]\b` fails on `a) ` or `a. ` because `)` / `.` and the following space are both non-word characters (`\W`), where no `\b` exists.
5. **Deduction**: `has_step_indicators` returns `False` for **all** numbered procedures (`1. ...`, `2. ...`) and **all** lettered procedures (`a) ...`, `b) ...`).
6. **Observation 1.4**:
   - When legitimate civic instructions in standard numbered format (`1. Download Form 29 (PDF, 50 KB)`) are passed to `is_navigation_or_boilerplate_text()`, `has_step_indicators` evaluates to `False`.
   - The catalog detector `\d+(?:\.\d+)?\s*(?:kb|mb|gb)` matches `50 KB`.
   - The function incorrectly classifies the procedural text as boilerplate (`return True`).
7. **End-to-End Consequence**: In CRAG fallback synthesis, `synthesizer.py` checks `if is_navigation_or_boilerplate_text(raw_text):` and completely refuses to synthesize answers, returning 0 steps and `DISCRIMINATOR_FAILURE_PHRASE`.
8. **Conclusion**: This is a critical false-positive bug that invalidates the preservation of legitimate procedural steps. Changes must be requested before Milestone 1 can be approved.

---

## 3. Challenges

### [Critical] Challenge 1: Regex Syntax Defect in `has_step_indicators` Causes False Positive Rejection of Numbered and Lettered Procedures

- **Assumption challenged**: The assumption that `has_step_indicators` preserves legitimate numbered (`1.`, `2.`) and lettered (`a)`, `b)`) procedural instructions containing downloadable files and sizes.
- **Attack scenario**: A user queries for a procedure whose official portal page lists numbered steps containing form downloads, e.g.:
  ```
  Procedure to obtain Duplicate Driving Licence:
  1. Download Form 29 (PDF, 50 KB) from the Parivahan portal.
  2. Fill out vehicle registration and applicant details.
  3. Submit to RTO.
  ```
- **Blast radius**: The page is discarded as boilerplate noise. The user receives a blank failure refusal ("Live search failed to extract the procedural text from the official portal...") despite the official portal possessing the complete procedural answer.
- **Root Cause**:
  `r"\b(?:step\s*\d+|steps|[a-g][\.\)]|\d+[\.\)]\s+[A-Z])\b"`
  - `[A-Z]` tested on `lowered` (0 matches).
  - Trailing `\b` after punctuation `[\.\)]` fails on whitespace.
- **Mitigation**:
  Replace `has_step_indicators` regex in `backend/web_search/fetcher.py` with a pattern that correctly detects numbered and lettered step indicators without trailing boundary failure on punctuation or case mismatch:
  ```python
  has_step_indicators = bool(
      re.search(
          r"(?:\b(?:step\s*\d+|steps)\b|(?:\b\d+[\.\)]|\b[a-g][\.\)])(?:\s+|$))",
          lowered,
      )
  )
  ```

### [High] Challenge 2: Numbered Procedures with Checklist Pipes Trigger Table Noise Discriminator

- **Assumption challenged**: Multi-pipe detection at line 212 (`pipe_count >= 3 and not has_step_indicators`) only triggers on unformatted tabular data.
- **Attack scenario**: Civic instructions commonly feature document checklists separated by pipes:
  ```
  Required Documents: Aadhaar Card | Passport | Voter ID | Driving Licence
  1. Visit the portal and submit the online application.
  2. Verify Aadhaar OTP.
  3. Pay the statutory fee online.
  ```
- **Blast radius**: Because `has_step_indicators` evaluates to `False` on numbered steps `1. ...`, `pipe_count >= 3` triggers `return True`, discarding valid procedural guides.
- **Mitigation**: Fixing `has_step_indicators` as described in Challenge 1 ensures `not has_step_indicators` evaluates to `False`, allowing valid procedures with inline checklists to survive.

### [Medium] Challenge 3: Test Suite Blind Spot in `test_adversarial_m1_harness.py`

- **Assumption challenged**: The 12/12 passing status of `tests/test_adversarial_m1_harness.py` proves that numbered and lettered steps are protected.
- **Attack scenario**: `test_false_positive_numbered_steps` and `test_false_positive_letter_steps` used test fixtures that contained zero catalog tokens, zero noise words, and `< 3` pipes. In both fixtures, `has_step_indicators` was returning `False`, but the test passed purely because the string reached the final `return False` by luck.
- **Blast radius**: Future regressions in step preservation will go unnoticed unless test fixtures explicitly include document downloads and file sizes within numbered and lettered steps.
- **Mitigation**: Add test assertions in `tests/test_adversarial_m1_harness.py` that specifically verify numbered (`1. ... (PDF, 50 KB)`) and lettered (`a) ... (PDF, 50 KB)`) procedures survive.

---

## 4. Stress Test Results

| # | Scenario Description | Input Snippet | Expected Behavior | Actual Behavior | Result |
|---|----------------------|---------------|-------------------|-----------------|:------:|
| 1 | Pipeless document catalog listing (Tier 1 R5) | `List of Acceptable Documents... Format: PDFSize: 838.3 KB` | `is_noise == True` | `is_noise == True` | **PASS** |
| 2 | Procedure with `Step 1:` prefix + PDF (50 KB) | `Step 1: Download Form 29 (PDF, 50 KB)... Step 2:...` | `is_noise == False` | `is_noise == False` | **PASS** |
| 3 | Procedure with numbered `1.` prefix + PDF (50 KB) | `1. Download Form 29 (PDF, 50 KB)... 2. Fill details...` | `is_noise == False` | `is_noise == True` | **FAIL** |
| 4 | Procedure with lettered `a)` prefix + PDF (50 KB) | `a) Download Form 29 (PDF, 50 KB)... b) Fill details...` | `is_noise == False` | `is_noise == True` | **FAIL** |
| 5 | Procedure with numbered `1.` + 3 checklist pipes | `Aadhaar \| Passport \| Voter ID \| DL \n 1. Visit...` | `is_noise == False` | `is_noise == True` | **FAIL** |
| 6 | Procedure with numbered `1.` + 1 noise word | `1. Visit portal 2. Submit form \n For feedback contact...` | `is_noise == False` | `is_noise == True` | **FAIL** |
| 7 | End-to-end CRAG synthesis on numbered DL guide | `synthesize_from_web(..., p1, ...)` | `len(steps) >= 3` | `len(steps) == 0, refusal` | **FAIL** |
| 8 | Markdown table directory listing | `\| Form \| Purpose \| Fee \|\n\|---\|---\|---\|` | `is_noise == True` | `is_noise == True` | **PASS** |
| 9 | Pure nested HTML tables | `<table><tr><td><table>...</table></td></tr></table>` | Stripped to empty/noise | Stripped to empty/noise | **PASS** |
| 10 | Mixed HTML page with table + narrative | `Step 1... <table>...</table> Step 4...` | Steps preserved, table stripped | Steps preserved, table stripped | **PASS** |

---

## 5. Unchallenged Areas

- **EPFO Corpus Authenticity (R1)**: Thoroughly evaluated and approved in iteration 1 (`challenger_m1_2` report); Qdrant vector database remains sound with 1387 vectors and verified checksums.
- **Trafilatura extraction flags**: `include_tables=False` and `favor_precision=True` verified intact in `backend/web_search/fetcher.py`.

---

## 6. Caveats

- **No Caveats**: The defect was reproduced deterministically using standalone Python executions and the project test harness. The findings are 100% reproducible.

---

## 7. Conclusion

**Final Verdict: `REQUEST_CHANGES`**

Milestone 1 cannot be approved in its current state. While pipeless catalog rejection is functioning, it currently causes **collateral damage by rejecting legitimate procedural guides** formatted with standard numbering (`1.`, `2.`) or lettering (`a)`, `b)`) whenever those guides reference forms, PDFs, or file sizes.

### Action Items for Worker:
1. In `backend/web_search/fetcher.py` line 206, update `has_step_indicators` to:
   ```python
   has_step_indicators = bool(
       re.search(
           r"(?:\b(?:step\s*\d+|steps)\b|(?:\b\d+[\.\)]|\b[a-g][\.\)])(?:\s+|$))",
           lowered,
       )
   )
   ```
2. In `tests/test_adversarial_m1_harness.py`, add explicit test cases ensuring that numbered and lettered procedural guides containing file downloads (e.g. `"1. Download Form 29 (PDF, 50 KB)"` and `"a) Download Form 29 (PDF, 50 KB)"`) return `is_navigation_or_boilerplate_text() is False`.
3. Verify that all 12 existing adversarial tests + new adversarial tests + Tier 1 regression suite pass 100%.

---

## 8. Verification Method

To independently reproduce this failure and verify the defect, run the following commands in powershell:

```powershell
# 1. Run empirical reproduction demonstrating false positive rejection
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.web_search.fetcher import is_navigation_or_boilerplate_text; t = 'How to apply for DL:\n1. Download Form 29 (PDF, 50 KB) from the portal.\n2. Fill out vehicle registration details.\n3. Submit to RTO.'; print('Is noise (False expected, True returned):', is_navigation_or_boilerplate_text(t))"

# 2. Run empirical reproduction demonstrating CRAG synthesis refusal
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.web_search.synthesizer import synthesize_from_web, DISCRIMINATOR_FAILURE_PHRASE; t = 'How to apply for DL:\n1. Download Form 29 (PDF, 50 KB) from the portal.\n2. Fill out details.\n3. Submit to RTO.'; res = synthesize_from_web('How to apply?', t, 'https://parivahan.gov.in/dl'); print('Refusal returned:', DISCRIMINATOR_FAILURE_PHRASE in res.summary, 'Steps count:', len(res.steps))"

# Invalidation Conditions:
# The verdict REQUEST_CHANGES stands unless:
# - 'is_navigation_or_boilerplate_text(t)' returns False for numbered steps with '(PDF, 50 KB)'.
# - 'is_navigation_or_boilerplate_text(t)' returns False for lettered steps with '(PDF, 50 KB)'.
# - synthesize_from_web() successfully extracts steps from numbered procedural text without refusal.
# - Pipeless catalog listings continue to return True.
```
