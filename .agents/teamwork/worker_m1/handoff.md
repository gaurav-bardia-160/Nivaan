# Milestone 1 Implementation Handoff Report: Corpus Integrity & Scraper Cleanup (R1 & R5)

## 1. Observation

### 1.1 Target Modifications Executed
1. **Corpus Source & Tag Remediation (R1)**:
   - Target: `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl` (Line 10, Record ID: `epfo_claim_passbook_cheque_standards_01`).
   - Replaced invalid Inspector Compliance Manual URL:
     `"https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/08/Manual_for_Inspector_cum_Facilitator.pdf"`
     with authentic official circular URL:
     `"https://www.epfindia.gov.in/site_docs/PDFs/Circulars/Y2024-2025/WSU_IssueOfBKG_49885_16.pdf"`
   - Updated tags: Replaced `"manual"` with `"sop"`, added `"epf_claim_rejected"` and `"epf_bank_kyc"`.
   - Result: Matches allowlist in `backend/data/rag_manifest.json` (`www.epfindia.gov.in` is allowlisted under `troubleshooting_civic`).

2. **Test Suite Reconciliation (R1)**:
   - `tests/test_rag_loader.py` lines 134 & 136:
     - Updated `records_seen` from 1382 to 1415.
     - Updated `rejected_records` from 15 to 48 (reflecting 33 records from 11 official source datasets with November 2026 dates rejected under historical benchmark `as_of=date(2026, 10, 30)`).
   - `tests/test_build_vector_db.py` lines 168, 171, 173, 174:
     - Updated `total_documents`, `points`, and `index_metadata.documents` from 1354 to 1387.
     - Updated `categories["civic"]` from 599 to 632.

3. **Vector Database Rebuild (R1)**:
   - Executed `backend.offline.ensure_vector_db`.
   - Embedded 1387 canonical documents using FastEmbed `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions).
   - Rebuilt Qdrant embedded collection `govbank_chunks`.
   - Re-verified via `python -m backend.offline.ensure_vector_db --check-only`:
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

4. **Scraper Extraction & Boilerplate Detection (R5)**:
   - In `backend/web_search/fetcher.py`:
     - Configured `trafilatura.extract(html, include_links=False, include_images=False, include_tables=False, favor_precision=True, include_comments=False)` in `_extract_text()`, stripping HTML tables while preserving narrative procedural paragraphs.
     - Added `"table"` to `_NOISE_TAGS` for BeautifulSoup fallback, ensuring tables are decomposed even if Trafilatura returns None.
     - Enhanced `is_navigation_or_boilerplate_text()` with checks for pipe density (`pipe_count >= 2`), markdown table syntax (`|---|`), and document catalog patterns (`format: pdf`, `pdfsize`, `filesize`, `\d+ (?:kb|mb|gb)`, `download (`).
   - In `backend/web_search/synthesizer.py`:
     - Filtered candidate lines with `line.count("|") >= 2` or markdown table separators in `_extract_extractive_answer()`.
     - Excluded table patterns from extractive sentence candidates and step titles/details.
     - Filtered table lines in `_select_focused_passages()` so markdown table rows are omitted from LLM synthesis context.
   - In `backend/web_search/discriminator.py`:
     - Created module re-exporting `is_navigation_or_boilerplate_text` and `DISCRIMINATOR_FAILURE_PHRASE`.
   - In `tests/test_web_search.py`:
     - Added 4 behavior unit tests to `TestBoilerplateDetection`:
       * `test_identifies_markdown_table_directory_noise`: Verifies Scene 3 Turn 2 verbatim table row rejection.
       * `test_identifies_multiline_markdown_table_listing`: Verifies multiline table rejection.
       * `test_trafilatura_extraction_omits_tables`: Verifies HTML table stripping with mixed paragraph retention.
       * `test_synthesizer_rejects_table_noise_extractive_fallback`: Verifies synthesizer returns `DISCRIMINATOR_FAILURE_PHRASE` and empty steps on table text.

### 1.2 Verbatim Test Results
1. **R1 Regression Tests** (`tests/test_scenes_1_to_3_regression.py`):
   ```
   tests/test_scenes_1_to_3_regression.py::test_tier1_r1_epfo_manifest_allowlist PASSED [ 20%]
   tests/test_scenes_1_to_3_regression.py::test_tier1_r1_epfo_joint_declaration_sop_authenticity PASSED [ 40%]
   tests/test_scenes_1_to_3_regression.py::test_tier1_r1_epfo_closed_establishment_attestation_authenticity PASSED [ 60%]
   tests/test_scenes_1_to_3_regression.py::test_tier1_r1_epfo_passbook_cheque_standards_source_validity PASSED [ 80%]
   tests/test_scenes_1_to_3_regression.py::test_tier1_r1_epfo_no_pmvbry_boilerplate PASSED [100%]
   ====================== 5 passed, 54 deselected in 2.12s =======================
   ```

2. **Milestone 1 Combined Test Suite** (`tests/test_web_search.py`, `tests/test_rag_loader.py`, `tests/test_build_vector_db.py`):
   ```
   ============================= 38 passed in 54.34s =============================
   ```
   (26 passed in `test_web_search.py`, 7 passed in `test_rag_loader.py`, 5 passed in `test_build_vector_db.py`).

3. **Vector Readiness Tests** (`tests/test_vector_readiness.py`):
   ```
   ============================== 5 passed in 2.50s ==============================
   ```

4. **Scene 3 Turn 2 Exact Reproduction Check**:
   ```
   R5 Verification Succeeded!
   ```

5. **Adversarial & Directive Compliance**:
   ```
   Adversarial Challenge 1 (Pure Table Extraction): PASSED
   Adversarial Challenge 3 (Mixed Content Extraction): PASSED
   Zero predefined responses check: PASSED
   ```

---

## 2. Logic Chain

1. **R1 Remediation Logic**:
   - Upstream finding: Record `epfo_claim_passbook_cheque_standards_01` cited `Manual_for_Inspector_cum_Facilitator.pdf`, a 221-page inspector compliance guide with 0 mentions of passbooks or cheques.
   - Analysis proved the text accurately describes official EPFO claim settlement rules. Replacing the URL in-place with authentic circular `WSU_IssueOfBKG_49885_16.pdf` on `www.epfindia.gov.in` directly cures the source mismatch without altering document schema or count.
   - Updating the tags to replace `"manual"` with `"sop"`, `"epf_claim_rejected"`, and `"epf_bank_kyc"` prevents cross-domain retrieval bleed on generic queries.
   - Because 11 official source datasets (33 records) were added to `rag_manifest.json`, the explicit counts in `test_rag_loader.py` (when `as_of=2026-10-30`) required reconciling `records_seen: 1415` and `rejected_records: 48` (as future dated records relative to benchmark date).
   - Embedding all 1387 documents via `ensure_vector_db` updated `corpus_sha256` to `5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6` and synchronized Qdrant storage with 1387 points.

2. **R5 Scraper DOM Noise Elimination Logic**:
   - In Scene 3 Turn 2, DuckDuckGo returned the India Post Acts and Policies directory page (`/documents/actsandpolicies`). Because `trafilatura.extract()` had `include_tables=True`, the table rows were parsed into markdown pipe tables and extracted verbatim as civic answers.
   - By configuring `include_tables=False` and `favor_precision=True` in `trafilatura.extract()`, pure directory tables return `None`, while mixed pages retain narrative paragraphs and omit table markup.
   - Adding `"table"` to BeautifulSoup `_NOISE_TAGS` ensures fallback extraction decomposes `<table>` nodes if Trafilatura returns None.
   - Enhancing `is_navigation_or_boilerplate_text()` to detect pipe density, markdown table separators (`|---|`), and document catalog metadata ensures that any table content reaching the discriminator triggers rejection, causing the CRAG multi-result loop to evaluate the next hit or return `DISCRIMINATOR_FAILURE_PHRASE`.
   - Filtering table rows in `synthesizer.py` prevents tabular noise from polluting extractive answer candidates or LLM prompt context.

---

## 3. Caveats

1. **FastEmbed CPU Runtime**: Embedding 1387 records with multilingual MiniLM-L12 on CPU took approximately 14 minutes during full rebuild. Once built, `--check-only` validates checksum and point count in ~1 second.
2. **HTML Table Omission Trade-off**: Web pages that format sequential procedure steps entirely inside HTML table cells will have those cells omitted during live CRAG fallback. Official government workflows are mandated to be registered in canonical refined JSONL files, so CRAG is reserved for narrative web extraction.
3. **Historical Benchmark vs Current Date**: `test_rag_loader.py` evaluates under historical date `2026-10-30` (reporting 48 rejected future records, 1367 accepted, 1354 unique), whereas `load_corpus()` without date evaluates at current date (reporting 15 rejected, 1400 accepted, 1387 unique). Both paths are fully tested and passing.

---

## 4. Conclusion

Milestone 1 implementation is completely finished and fully verified:
- `troubleshooting_civic.jsonl` has verified authentic circular URL and tight retrieval tags.
- Vector database `govbank_chunks` is completely rebuilt and operational with 1387 points and matching SHA256.
- `fetcher.py` and `synthesizer.py` cleanly eliminate table DOM noise.
- `discriminator.py` module is created and functional.
- All 38 unit tests, 5 Tier 1 R1 regression tests, Scene 3 Turn 2 reproduction, and adversarial checks pass with 0 failures.
- No predefined responses, pre-canned answers, or hardcoded cheating was introduced.

---

## 5. Verification Method

To independently verify the implementation, execute the following commands in powershell:

```powershell
# 1. Verify Qdrant Vector Store readiness and point count
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db --check-only
# Expected: {"ready": true, "points": 1387, "dimensions": 384, "reason": "ready"}

# 2. Run Tier 1 R1 regression tests
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_scenes_1_to_3_regression.py -k "test_tier1_r1" -v
# Expected: 5 passed, 0 failed

# 3. Run Milestone 1 unit test targets
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_web_search.py tests\test_rag_loader.py tests\test_build_vector_db.py -v
# Expected: 38 passed, 0 failed

# 4. Run Scene 3 Turn 2 reproduction verification
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

# 5. Invalidation Conditions
# - If `ensure_vector_db --check-only` returns `ready: false`.
# - If any test in `test_web_search.py`, `test_rag_loader.py`, or `test_build_vector_db.py` fails.
# - If `tests\test_scenes_1_to_3_regression.py -k "test_tier1_r1"` fails.
```
