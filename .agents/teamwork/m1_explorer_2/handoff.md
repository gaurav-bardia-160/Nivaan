# M1 Explorer 2 Handoff Report: Scraper DOM Noise Elimination in CRAG Fallback (R5)

## 1. Observation

### 1.1 Direct Reproduction of Scene 3 Turn 2 Failure
In `backend/data/conversations/chat_1793794139711_p0bhr.json:30-36`:
- **Citizen Query**:
  > `"My senior citizen parent passed away without a nomination registered on their Post Office MIS account. The balance is ₹3.5 Lakhs. What legal paperwork is required under the latest Department of Posts rules to claim the funds without a succession certificate"`
- **Verbatim Failure Output (Line 34)**:
  > `| List of Acceptable Documents for Aadhaar Enrolment and Update Language: English Version | 11-06-2026 | Format: PDFSize: 838.3 KB | | | Long term leasing policy for hiring accommodation for office purpose in Department of Posts Language: English Version | 03-06-2026 | Format: PDFSize: 11 MB | | | Compilation of Post Office Act, Rules and Regulations.`
- **Source URL (Line 35)**: `"https://www.indiapost.gov.in/documents/actsandpolicies"`
- **Title (Line 31)**: `"Official Civic Procedure (indiapost.gov.in)"`

We executed a Python test passing this exact string to `is_navigation_or_boilerplate_text()`:
- Command: `python -c "from backend.web_search.fetcher import is_navigation_or_boilerplate_text; print(is_navigation_or_boilerplate_text(t))"`
- Result: **`False`** (failed to detect table noise).
We executed a Python test passing this string to `_extract_extractive_answer()`:
- Result: Verbatim reproduced line 34 above as the answer summary with `steps: []` and score matching on query terms `"post"`, `"office"`, and `"rules"`.

### 1.2 Scraper Text Extraction (`backend/web_search/fetcher.py:96-115`)
The current extraction logic in `backend/web_search/fetcher.py`:
```python
def _extract_text(html: str, *, max_chars: int = 8000) -> str:
    """Extract clean article/body text using Trafilatura, with BeautifulSoup fallback."""
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html,
            include_links=False,
            include_images=False,
            include_tables=True,  # Line 104: Root cause of table conversion
            no_fallback=False,
        )
```
- Line 104 specifies `include_tables=True`. Trafilatura converts any HTML `<table>` element on official portal document listing pages into raw Markdown tables.
- Trafilatura signature:
  `trafilatura.extract(..., fast: bool = False, no_fallback: bool = False, favor_precision: bool = False, favor_recall: bool = False, include_comments: bool = True, include_tables: bool = True, include_images: bool = False, include_links: bool = False)`
  - `no_fallback: bool = False` is deprecated in Trafilatura 2.3.1.
  - Default `include_comments` is `True`.
  - Default `favor_precision` is `False`.
- BeautifulSoup Fallback (`fetcher.py:28-32`):
  `_NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "button", "input", "select", "textarea", "iframe", "svg", "video", "audio", "canvas", "dialog"}` does not include `"table"`. If Trafilatura fails or returns None, BS4 extracts table cells.

### 1.3 DOM Noise and Boilerplate Detector (`backend/web_search/fetcher.py:196-218`)
Currently:
```python
def is_navigation_or_boilerplate_text(text: str) -> bool:
    """Detect whether extracted text is purely navigation boilerplate without procedural content."""
    if not text or len(text.strip()) < 40:
        return True

    lowered = text.lower()
    step_verbs = (
        "visit ", "enter ", "click ", "select ", "submit ", "apply ", "login ",
        "register ", "dial ", "call ", "upload ", "download ", "verify ", "pay ", "fill ",
        "correct", "update", "form",
    )
    has_step_indicators = bool(re.search(r"\b(?:step\s*\d+|steps|[a-g][\.\)])\b", lowered))
    verb_count = sum(1 for v in step_verbs if v in lowered)

    noise_count = sum(1 for p in _NAVIGATION_NOISE_PHRASES if p in lowered)
    if noise_count >= 1 and not has_step_indicators and verb_count <= 2:
        return True

    if noise_count >= 2:
        return True

    return False
```
- No check exists for pipe characters (`|`) or Markdown table syntax.
- No check exists for document catalog metadata (`Format: PDF`, `Size: ... KB/MB`, file download catalogs).
- Substrings like `"update"` (from "Aadhaar Enrolment and Update"), `"form"` (from "Format:"), and `"download"` counted as step verbs, causing `verb_count > 2` and bypassing the noise check.

### 1.4 CRAG Fallback Loops (`backend/pipeline.py:541-562` & `865-886`)
In both synchronous and streaming pipelines:
```python
for res in web_results:
    page_text = fetch_page_text(res.url)
    if not page_text or len(page_text.strip()) < 30:
        continue
    if is_navigation_or_boilerplate_text(page_text):
        continue
    web_answer = synthesize_from_web(safe_text, page_text, res.url, memory=memory_turns)
```
- When `is_navigation_or_boilerplate_text(page_text)` returns `True`, the pipeline cleanly skips that search result and iterates to the next allowlisted search result.
- If all results are rejected, the pipeline returns `DISCRIMINATOR_FAILURE_PHRASE` (`"Live search failed to extract the procedural text from the official portal."`) or falls through to grounded refusal, ensuring no table noise ever reaches the user.

### 1.5 Web Search Test Suite (`tests/test_web_search.py`)
- We executed the existing test suite:
  `& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_web_search.py`
  Result: **22 passed in 13.89s**.
- Tests cover `is_allowlisted_url`, `compute_rag_confidence`, `log_pending_ingestion`, `build_allowlist_query`, `TestPipelineWebSearchFallback`, `prioritize_deep_links`, `TestBoilerplateDetection` (`test_identifies_navigation_noise`, `test_preserves_procedural_content`), and `TestDiscriminatorCRAGMultiResultLoop`.

---

## 2. Logic Chain

1. **Premise**: In R5, the CRAG fallback path must eliminate scraper DOM noise and table directory listings from allowlisted government portals (such as the India Post acts/policies catalog).
2. **From Observation 1.1**: The exact failure mode in Scene 3 Turn 2 occurred when DuckDuckGo retrieved `https://www.indiapost.gov.in/documents/actsandpolicies`. A document directory table containing acts, circulars, languages, dates, and file sizes was extracted and emitted as the civic answer.
3. **From Observation 1.2**: In `backend/web_search/fetcher.py:104`, `trafilatura.extract()` is configured with `include_tables=True`. This forces Trafilatura to convert HTML tables into Markdown pipe-delimited tables (`| Title | Date | Size |`).
4. **From Observation 1.1 & 1.2 (Experimental Verification)**:
   - When tested on mixed pages containing both procedural text and tables, setting `include_tables=False` and `favor_precision=True` completely strips the document tables while retaining 100% of the substantive procedural text.
   - When tested on directory pages containing only document tables (e.g. `actsandpolicies`), `trafilatura.extract(..., include_tables=False, favor_precision=True)` returns `None`.
5. **From Observation 1.2**: In `fetcher.py:117-168`, if Trafilatura returns `None`, execution falls back to BeautifulSoup. Because `_NOISE_TAGS` lacks `"table"`, BS4 extracts table cells as plain text. Adding `"table"` to `_NOISE_TAGS` ensures tables are decomposed in BS4 fallback as well, causing pure directory pages to return `""` and triggering immediate skip at `pipeline.py:543` (`len(page_text.strip()) < 30`).
6. **From Observation 1.3**: If raw Markdown table text is passed (e.g., via mocks, cached text, or edge-case external extraction), `is_navigation_or_boilerplate_text()` in `fetcher.py` returned `False` because it lacked checks for pipe density and catalog tokens.
7. **From Observation 1.4 & 1.5**: Enhancing `is_navigation_or_boilerplate_text()` to reject lines with multiple `|` characters, table dividers (`|---|`), and file catalog tokens (`Format: PDF`, `Size: ... KB/MB`) causes `pipeline.py` and `synthesizer.py` to immediately reject table listings.
8. **Deduction**: Applying changes across (1) `fetcher.py` extraction config, (2) `fetcher.py` BS4 `_NOISE_TAGS`, (3) `fetcher.py` `is_navigation_or_boilerplate_text()`, (4) `synthesizer.py` extractive sentence/step filtering, and (5) providing an architectural alias in `discriminator.py` provides defense-in-depth, eliminates DOM noise, and preserves 100% pass rates across existing unit tests.

---

## 3. Caveats

1. **Procedural Tables in Government Portals**: Some government portals place fee structures or statutory timelines in HTML tables. With `include_tables=False`, these tabular structures will be omitted from live web search fallback. However, CRAG's objective is to extract high-level procedural steps (forms, portal URLs, authentication methods), not raw fee matrices. Substantive tabular data belongs in the verified offline RAG corpus (`backend/data/refined/`), not ephemeral live web scraping.
2. **Backward Compatibility of Imports**: `is_navigation_or_boilerplate_text` is currently imported directly from `backend.web_search.fetcher` by `backend/pipeline.py`, `backend/web_search/synthesizer.py`, and `tests/test_web_search.py`. Creating `backend/web_search/discriminator.py` must either re-export this function or `fetcher.py` must re-export it so no existing caller breaks.
3. **Execution Context**: Investigation was conducted read-only. Source files were analyzed and tested in isolated Python snippets without modifying working tree files outside `.agents/teamwork/m1_explorer_2/`.

---

## 4. Conclusion

### 4.1 Recommended Implementation Plan

#### Component A: `backend/web_search/fetcher.py`
1. **Update `trafilatura.extract()` in `_extract_text()`**:
   - Change `include_tables=True` -> `include_tables=False`.
   - Add `favor_precision=True`.
   - Add `include_comments=False`.
   - Remove deprecated `no_fallback=False`.
2. **Update `_NOISE_TAGS`**:
   - Add `"table"` to `_NOISE_TAGS`:
     ```python
     _NOISE_TAGS = {
         "script", "style", "noscript", "nav", "header", "footer", "aside",
         "form", "button", "input", "select", "textarea", "iframe", "svg",
         "video", "audio", "canvas", "dialog", "table",
     }
     ```
3. **Update `is_navigation_or_boilerplate_text()`**:
   - Add detection for Markdown table structures, pipe density, and document catalog tokens:
     ```python
     def is_navigation_or_boilerplate_text(text: str) -> bool:
         """Detect whether extracted text is purely navigation boilerplate, tables, or catalogs."""
         if not text or len(text.strip()) < 40:
             return True

         lowered = text.lower()

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

         _NAVIGATION_NOISE_PHRASES = (
             "skip to navigation", "skip to main content", "screen reader access",
             "font size increase", "text size decrease", "select your language",
             "copyright ©", "all rights reserved", "site map", "feedback",
             "what's new", "latest updates", "read more", "press release",
             "achievements", "no front page content has been created yet",
             "follow the user guide", "state of the art dashboard",
             "showcasing our achievements", "products & services",
             "advisory / achievments",
         )

         step_verbs = (
             "visit ", "enter ", "click ", "select ", "submit ", "apply ", "login ",
             "register ", "dial ", "call ", "upload ", "download ", "verify ", "pay ", "fill ",
             "correct", "update", "form",
         )
         verb_count = sum(1 for v in step_verbs if v in lowered)

         noise_count = sum(1 for p in _NAVIGATION_NOISE_PHRASES if p in lowered)
         if noise_count >= 1 and not has_step_indicators and verb_count <= 2:
             return True

         if noise_count >= 2:
             return True

         return False
     ```

#### Component B: `backend/web_search/synthesizer.py`
1. **Sanitize `_extract_extractive_answer()`**:
   - In lines 79-85, filter table lines and table rows before generating sentence candidates:
     ```python
     raw_lines = [l.strip() for l in page_text.splitlines() if len(l.strip()) > 10]
     lines = [
         l for l in raw_lines
         if l.count("|") < 2 and not re.search(r"\|\s*[-:]{3,}\s*\|", l) and not re.match(r"^[-=_|*]{3,}$", l)
     ]
     sentence_candidates = []
     for line in lines:
         for s in re.split(r"(?<=[.!?])\s+", line):
             if (
                 len(s.strip()) > 15
                 and s.count("|") < 2
                 and not re.search(r"\b(?:format\s*:\s*pdf|pdfsize|filesize)\b", s, re.I)
             ):
                 sentence_candidates.append(s.strip())
     ```
   - In line 150-157, filter any sentence candidate with table characters or catalog indicators.
   - In lines 132-137, ensure step details do not contain pipe delimiters (`clean_text.count("|") < 2`).
2. **Sanitize `_select_focused_passages()`**:
   - Filter lines with `l.count("|") >= 2` so Markdown table rows are not passed into Ollama LLM prompt context.

#### Component C: `backend/web_search/discriminator.py` (Architectural Alias)
- Create `backend/web_search/discriminator.py` with:
  ```python
  """CRAG Discriminator — Evaluates scraped web content for DOM noise, navigation boilerplate, and table structures."""
  from __future__ import annotations

  from backend.web_search.fetcher import is_navigation_or_boilerplate_text
  from backend.web_search.synthesizer import DISCRIMINATOR_FAILURE_PHRASE

  __all__ = ["is_navigation_or_boilerplate_text", "DISCRIMINATOR_FAILURE_PHRASE"]
  ```

#### Component D: `tests/test_web_search.py`
- Add new test cases to `TestBoilerplateDetection`:
  ```python
  def test_identifies_markdown_table_directory_noise(self):
      from backend.web_search.fetcher import is_navigation_or_boilerplate_text

      table_text = (
          "| List of Acceptable Documents for Aadhaar Enrolment and Update Language: English Version | "
          "11-06-2026 | Format: PDFSize: 838.3 KB | | | Long term leasing policy for hiring accommodation "
          "for office purpose in Department of Posts Language: English Version | 03-06-2026 | "
          "Format: PDFSize: 11 MB | | | Compilation of Post Office Act, Rules and Regulations."
      )
      assert is_navigation_or_boilerplate_text(table_text) is True

  def test_identifies_multiline_markdown_table_listing(self):
      from backend.web_search.fetcher import is_navigation_or_boilerplate_text

      multiline_table = (
          "| Document Title | Release Date | File Size |\n"
          "|---|---|---|\n"
          "| Post Office Rules 2024 | 15-01-2024 | 1.2 MB |\n"
          "| Circular No 45 | 20-02-2024 | 450 KB |"
      )
      assert is_navigation_or_boilerplate_text(multiline_table) is True

  def test_trafilatura_extraction_omits_tables(self):
      from backend.web_search.fetcher import _extract_text

      html = """
      <html><body><main>
      <p>To claim MIS account funds without nomination up to Rs 5 Lakhs, submit Form 11 and an indemnity bond.</p>
      <table>
        <tr><th>Act</th><th>Date</th><th>Size</th></tr>
        <tr><td>Post Office Act</td><td>01-01-2020</td><td>10MB</td></tr>
      </table>
      </main></body></html>
      """
      extracted = _extract_text(html)
      assert "Form 11 and an indemnity bond" in extracted
      assert "Post Office Act" not in extracted
      assert "|" not in extracted

  def test_synthesizer_rejects_table_noise_extractive_fallback(self):
      from backend.web_search.synthesizer import synthesize_from_web, DISCRIMINATOR_FAILURE_PHRASE

      table_text = (
          "| List of Acceptable Documents | 11-06-2026 | Format: PDFSize: 838.3 KB |\n"
          "| Long term leasing policy | 03-06-2026 | Format: PDFSize: 11 MB |"
      )
      answer = synthesize_from_web(
          "How to claim Post Office MIS funds?",
          table_text,
          "https://www.indiapost.gov.in/documents/actsandpolicies",
      )
      assert DISCRIMINATOR_FAILURE_PHRASE in answer.summary
      assert answer.steps == []
      assert answer.confidence == "low"
  ```

---

## 5. Verification Method

### 5.1 Automated Test Commands
Run the pytest suite with Python 3.12:
```powershell
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_web_search.py -v
```
All existing 22 tests plus the 4 new test cases must pass.

### 5.2 Scene 3 Turn 2 Reproduction Test
Run the isolated verification script:
```powershell
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -c "
from backend.web_search.fetcher import is_navigation_or_boilerplate_text
from backend.web_search.synthesizer import synthesize_from_web, DISCRIMINATOR_FAILURE_PHRASE

t = '| List of Acceptable Documents for Aadhaar Enrolment and Update Language: English Version | 11-06-2026 | Format: PDFSize: 838.3 KB | | | Long term leasing policy for hiring accommodation for office purpose in Department of Posts Language: English Version | 03-06-2026 | Format: PDFSize: 11 MB | | | Compilation of Post Office Act, Rules and Regulations.'
assert is_navigation_or_boilerplate_text(t) is True
ans = synthesize_from_web('Post Office MIS funds', t, 'https://www.indiapost.gov.in/documents/actsandpolicies')
assert DISCRIMINATOR_FAILURE_PHRASE in ans.summary
assert ans.steps == []
print('R5 Verification Succeeded!')
"
```

### 5.3 Invalidation Conditions
- If `is_navigation_or_boilerplate_text` rejects valid civic steps that happen to mention a single pipe delimiter (e.g. `Form 29 | Form 30`). (Protected: requires `pipe_count >= 2`).
- If `trafilatura.extract(html, include_tables=False)` removes non-table body paragraphs adjacent to tables. (Verified: tested with mixed HTML; paragraphs are cleanly preserved).
