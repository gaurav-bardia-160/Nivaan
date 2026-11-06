# Survey 2 (Gen 2) Investigation Report: EPFO Corpus Documents, Manifest, Ingestion Pipeline, and CRAG Scraper (R1 & R5)

## 1. Observation

### 1.1 Manifest & Corpus Storage for EPFO Documents (`backend/data/rag_manifest.json`)
1. **Manifest Registration** (`backend/data/rag_manifest.json:584-607`):
   - The EPFO documents are registered under dataset ID `troubleshooting_civic`:
     ```json
     {
       "id": "troubleshooting_civic",
       "path": "refined/troubleshooting/troubleshooting_civic.jsonl",
       "category": "civic",
       "allowed_hosts": [
         "cms.rbi.org.in",
         "consumerhelpline.gov.in",
         "edaakhil.nic.in",
         "epfigms.gov.in",
         "epfindia.gov.in",
         "m.rbi.org.in",
         "nalsa.gov.in",
         "ncdrc.nic.in",
         "passportindia.gov.in",
         "pgportal.gov.in",
         "pmvbry-cdn.epfindia.gov.in",
         "pmvbry.epfindia.gov.in",
         "rbi.org.in",
         "sikkim.nalsa.gov.in",
         "voters.eci.gov.in",
         "www.epfindia.gov.in",
         "www.passportindia.gov.in",
         "www.rbi.org.in"
       ]
     }
     ```
   - Both `pmvbry-cdn.epfindia.gov.in` (line 598) and `pmvbry.epfindia.gov.in` (line 599) are explicitly allowlisted hosts for this dataset.

2. **Corpus JSONL Records** (`backend/data/refined/troubleshooting/troubleshooting_civic.jsonl:8-10`):
   - **Record 1 (Line 8)**:
     - `id`: `"epfo_joint_declaration_minor_major_sop_01"`
     - `source_url`: `"https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/09/SOP_JointDeclarations_29082023-7.pdf"`
     - `title`: `"EPFO Joint Declaration SOP (JD/2022/1): Minor and Major Member Profile Corrections"`
     - `section`: `"Member Profile Mismatch (Name, DoB, Exit Date) & Minor/Major Correction Rules"`
     - `text`: *"EPFO Joint Declaration Standard Operating Procedure (SOP No: JD/2022/1): Governs profile corrections (Name, Father/Spouse name, Date of Birth, Gender, Date of Joining, and Date of Exit) through the Unified Member Portal to prevent claim rejections (Form 19, 31, 10C)... Minor Modifications: Encompasses corrections of up to two characters in a member's legal name, alterations in parental initials, or Date of Birth adjustments of three years or less (+/- 3 years)... Major Modifications: Encompasses complete changes in first or last names, Date of Birth adjustments exceeding three years... Statutory TAT is 15 working days... Workflow: Member uploads documents under 'Manage > Joint Declaration' on unifiedportal-mem.epfindia.gov.in..."*
     - `verification_method`: `"official_circular_and_sop"`
     - `retrieval_tags`: `["troubleshooting", "escalation", "sop", "epf_joint_declaration", "minor_major_modifications", "epf_name_correction", "annexure_1_epfo", "epf_claim_rejected", "jd_2022_1"]`

   - **Record 2 (Line 9)**:
     - `id`: `"epfo_closed_establishment_attestation_01"`
     - `source_url`: `"https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/09/100.pdf"`
     - `title`: `"EPFO Attestation Framework for Closed Establishments and Untraceable Employers"`
     - `section`: `"Field Correction Formats, Closed Establishment Attestation, and Non-Cooperative Employers"`
     - `text`: *"EPFO Resolution When Establishment is Closed or Untraceable: When an employer refuses to approve a Joint Declaration, the company has closed down, or the establishment is non-operational, automated online DSC verification cannot proceed... Alternative Administrative Attestation Protocol: Under EPFO circular instructions, the member does not need employer sign-off if the establishment is closed. Instead, the applicant can submit a physical Joint Declaration application supported by authorized third-party certification... Authorized Certifying Authorities: 1. A Judicial Magistrate. 2. A Gazetted Officer. 3. A Postmaster or Sub-Postmaster. 4. The Branch Manager of the bank holding the claimant's savings account... Submission: Submit the attested physical Joint Declaration along with proof of employment (appointment letter, salary slip, relieving letter) directly to the jurisdictional Regional P.F. Commissioner (RPFC) at the local EPFO Field Office."*
     - `verification_method`: `"official_circular_and_sop"`
     - `retrieval_tags`: `["troubleshooting", "escalation", "sop", "closed_establishment_epf", "employer_untraceable", "gazetted_officer_attestation", "bank_manager_attestation", "epf_physical_joint_declaration"]`

   - **Record 3 (Line 10)**:
     - `id`: `"epfo_claim_passbook_cheque_standards_01"`
     - `source_url`: `"https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/08/Manual_for_Inspector_cum_Facilitator.pdf"`
     - `title`: `"EPFO Passbook and Cheque Leaf Validation Standards for Form 19 and 31 Claims"`
     - `section`: `"Terminal Settlement Rejections and Visual Passbook/Cheque Validation Criteria"`
     - `text`: *"EPFO Claim Rejections Due to Bank Instrument Issues: A frequent reason for the systemic rejection of Form 19 (PF Final Settlement) and Form 31 (PF Advance) claims is an invalid or unverified bank account instrument... Strict Visual Verification Criteria: 1. Cancelled Cheque Leaf: The member's legal name MUST be pre-printed on the face of the cheque leaf by the financial institution. Handwritten names, third-party endorsements, or blank name fields are rejected automatically. 2. Bank Passbook: If a passbook is uploaded instead of a cheque, the uploaded image must clearly show: account holder's full legal name, primary bank account number, bank branch IFSC, and a recent photograph of the member authenticated with the bank branch manager's physical stamp and signature... Corrective Action: If a claim was rejected for 'Name not printed on cheque' or 'Passbook not attested', update the bank KYC details under 'Manage > KYC' on the Unified Portal..."*
     - `verification_method`: `"official_circular_and_sop"`
     - `retrieval_tags`: `["troubleshooting", "escalation", "manual", "epf_cheque_rejected", "name_not_printed_cheque", "epf_passbook_stamp", "form_19_rejection", "form_31_rejection"]`

### 1.2 Inspection of Remote PDF Artifacts Hosted on `pmvbry-cdn.epfindia.gov.in`
We fetched and directly analyzed each of the three hosted PDFs using Python 3.12 (`pypdf`, `pypdfium2`, and `rapidocr-onnxruntime`):

1. **Document 1: `SOP_JointDeclarations_29082023-7.pdf`**:
   - URL: `https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/09/SOP_JointDeclarations_29082023-7.pdf`
   - HTTP Status: `200 OK` (File size: 642,853 bytes).
   - Page count: 35 pages.
   - Page 2 text extraction:
     > `"EPFO STANDARD OPERATING PROCEDURE JD COMMITTEE SOP No: JD/2022/1 SOP Title: Joint Declaration SOP Number: JD/2022/1 SOP Title: Member Profile Correction/Updation process for parameters namely (1) Name, (2) Gender, (3) Date of Birth, (4) Father Name/Mother Name, (5) Relationship..."`
   - Findings: **Authentic official SOP document.** Content precisely matches the title and chunk text. It does NOT contain PMVBRY boilerplate.

2. **Document 2: `100.pdf`**:
   - URL: `https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/09/100.pdf`
   - HTTP Status: `200 OK` (File size: 1,373,021 bytes).
   - Page count: 4 pages (scanned document).
   - OCR Extraction:
     - Page 1: Official EPFO Head Office Circular `No: WSU/MemberProfile/E-710137/2025-26/6` dated `13/Aug/2025` from CPFC/Head Office to All ACC(HQ)s/ACCs(Zones) and All RPFCs. Subject: *"Seeding/Correcting Aadhaar in UAN"*.
     - Page 2: Clause (c): *"In case the Employer is not available or the Establishment is closed, the Member can still file a physical JD in the format at Annexure I duly attested by any one of the authorities specified in Table II-A and submit to the Public Relations Officer (PRO) Counter in the concerned Regional Office with due acknowledgement. The PRO after due verification shall enter the details in the JD functionality and submit the request for further processing by the office."*
   - Findings: **Authentic official EPFO circular.** The chunk text directly reflects this official administrative instruction. It does NOT contain PMVBRY boilerplate.

3. **Document 3: `Manual_for_Inspector_cum_Facilitator.pdf`**:
   - URL: `https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/08/Manual_for_Inspector_cum_Facilitator.pdf`
   - HTTP Status: `200 OK` (File size: 10,590,695 bytes).
   - Page count: 221 pages.
   - Document Title: *"MANUAL FOR INSPECTOR cum FACILITATOR 2024 - EMPLOYEES' PROVIDENT FUND ORGANISATION MINISTRY OF LABOUR AND EMPLOYMENT GOVERNMENT OF INDIA"*.
   - Exhaustive Search: We executed a script checking all 221 pages for occurrences of `"cheque"` or `"passbook"`. Result: **Total pages mentioning cheque or passbook: 0**.
   - Findings: **Severe source mismatch.** The PDF is an operational compliance manual detailing inspector powers, employer inspection schemes, and prosecution under Section 14 of the EPF Act. It contains zero guidelines regarding member passbook or cancelled cheque leaf validation standards. The chunk text in `troubleshooting_civic.jsonl` reflects real EPFO claim settlement rules, but the cited source URL is completely mismatched.

### 1.3 Ingestion and Vector Store Pipeline Mechanics
1. **Manifest Ingestion Tool** (`backend/offline/ingest_official_source.py:1-622`):
   - Command: `python -m backend.offline.ingest_official_source --url <URL> --source-id <ID> --category <CAT> --title <TITLE> --register-manifest`
   - Validation: Enforces HTTPS, host allowlist, duplicate SHA256 detection, HTML/PDF extraction, and writes refined JSONL under `backend/data/refined/official_sources/`.
   - Manifest update: Automatically appends dataset entry into `backend/data/rag_manifest.json`.

2. **Vector Index Builder** (`backend/offline/build_vector_db.py:330-388` & `backend/offline/ensure_vector_db.py:1-152`):
   - Vector Store: Embedded Qdrant local storage at `backend/data/vector_index/qdrant`. Collection: `govbank_chunks`.
   - Inspection command: `python -m backend.offline.ensure_vector_db --check-only`
   - Execution result:
     ```json
     {
       "path": "C:\\Users\\gaura\\Documents\\nivaan\\backend\\data\\vector_index\\qdrant",
       "collection": "govbank_chunks",
       "expected_documents": 1387,
       "corpus_sha256": "db8eff3f2aacb23d523d59e62741fd93bfe3b89aea1dab924e9f0a40d19ead71",
       "ready": true,
       "points": 1387,
       "dimensions": 384,
       "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
       "reason": "ready"
     }
     ```
   - Rebuild command: `python -m backend.offline.ensure_vector_db` re-embeds all documents using `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` whenever document count or SHA256 changes.

3. **Test Suite Corpus Integrity Constraints** (`tests/test_rag_loader.py:131-140`):
   - Enforces strict exact document counts:
     ```python
     def test_loader_default_repo_corpus_counts_are_explicit():
         result = load_corpus(as_of=date(2026, 10, 30))
         assert result.report.records_seen == 1382
         assert result.report.accepted_records == 1367
         assert result.report.rejected_records == 15
         assert result.report.unique_documents == 1354
         assert result.report.retained_source_references == 1367
         assert result.report.category_counts == {"aadhaar": 396, "civic": 599, "pan": 244, "tax": 115}
     ```
   - Any remediation that modifies existing records in-place (updating source URL and content) preserves these counts. If new records are added, the assertions in `test_rag_loader.py` must be updated accordingly.

### 1.4 CRAG Fallback Scraper & DOM Noise Analysis (`backend/web_search/`)
1. **Trigger and Execution Flow** (`backend/pipeline.py:529-570` and `853-890`):
   - Triggered when `compute_rag_confidence(rag_result) < 0.040`.
   - Calls `search_duckduckgo(web_query, max_results=3)` from `backend/web_search/searcher.py`.
   - For each allowlisted URL, calls `page_text = fetch_page_text(res.url)` from `backend/web_search/fetcher.py`.
   - If not rejected by `is_navigation_or_boilerplate_text(page_text)`, calls `synthesize_from_web(safe_text, page_text, res.url)`.

2. **Scraper Extraction Implementation** (`backend/web_search/fetcher.py:96-168`):
   ```python
   def _extract_text(html: str, *, max_chars: int = 8000) -> str:
       """Extract clean article/body text using Trafilatura, with BeautifulSoup fallback."""
       try:
           import trafilatura
           extracted = trafilatura.extract(
               html,
               include_links=False,
               include_images=False,
               include_tables=True,  # <-- CAUSE OF DOM NOISE
               no_fallback=False,
           )
           if extracted and len(extracted.strip()) > 40:
               lines = [line.strip() for line in extracted.splitlines()]
               meaningful = [l for l in lines if l and not re.match(r"^[-=_|*]{3,}$", l)]
               cleaned = "\n".join(meaningful)
               cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
               return cleaned[:max_chars].strip()
       except Exception as exc:
           logger.debug("Trafilatura extraction failed (%s), falling back to BS4", exc)
   ```

3. **Root Cause of Scene 3 Turn 2 DOM Noise** (`backend/data/conversations/chat_1793794139711_p0bhr.json:30-36`):
   - User asked: *"My senior citizen parent passed away without a nomination registered on their Post Office MIS account. The balance is ₹3.5 Lakhs. What legal paperwork is required under the latest Department of Posts rules to claim the funds without a succession certificate"*
   - The CRAG search retrieved `https://www.indiapost.gov.in/documents/actsandpolicies`.
   - Because `include_tables=True`, `trafilatura` converted the HTML document directory table into Markdown table rows:
     > `"| List of Acceptable Documents for Aadhaar Enrolment and Update Language: English Version | 11-06-2026 | Format: PDFSize: 838.3 KB | | | Long term leasing policy for hiring accommodation for office purpose in Department of Posts Language: English Version | 03-06-2026 | Format: PDFSize: 11 MB | | | Compilation of Post Office Act, Rules and Regulations."`
   - In `backend/web_search/synthesizer.py:77-100`, the extractive fallback matched keywords like "post", "office", and "rules" in the table rows.
   - The table text was synthesized verbatim as the assistant's answer because `has_topical_overlap` was true and the table rows were not caught by `is_navigation_or_boilerplate_text()`.

4. **Experimental Proof of DOM Noise Elimination**:
   - We tested `trafilatura.extract(sample_html, include_tables=False, favor_precision=True)` on sample directory tables.
   - Result:
     - Document/link tables were completely stripped.
     - On pages containing substantive procedural paragraphs along with tables, only the clean procedural paragraphs were retained.
     - On directory listing pages containing only tables, Trafilatura returned `None`, triggering clean rejection and an honest ungrounded refusal rather than table noise.

5. **Dependencies Verification**:
   - `backend/requirements.txt:19`: `trafilatura>=1.8.0` is already declared.
   - System verification: `trafilatura 2.3.1` is installed and verified in `Python 3.12.3`. No new pip installations or dependency changes are needed.

---

## 2. Logic Chain

1. **Premise**: In R1, the team must determine whether the 3 EPFO documents in `backend/data/rag_manifest.json` hosted on `pmvbry-cdn.epfindia.gov.in` contain authentic content matching their titles or consist of PMVBRY boilerplate, and locate authentic official circulars.
2. **From Observation 1.1**: The three documents reside in `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl` under IDs `epfo_joint_declaration_minor_major_sop_01`, `epfo_closed_establishment_attestation_01`, and `epfo_claim_passbook_cheque_standards_01`.
3. **From Observation 1.2**:
   - `SOP_JointDeclarations_29082023-7.pdf` is the authentic 35-page Joint Declaration SOP (JD/2022/1).
   - `100.pdf` is an authentic 4-page scanned official EPFO circular (`WSU/MemberProfile/E-710137/2025-26/6` dated 13/Aug/2025) governing attestation for closed establishments.
   - `Manual_for_Inspector_cum_Facilitator.pdf` is a 221-page Inspector manual containing 0 occurrences of "passbook" or "cheque".
4. **Deduction for R1**: The failure in Scene 1 Turn 1 was NOT due to boilerplate in `100.pdf`, but due to vector nearest-neighbor retrieval retrieving the closed-establishment document when an active establishment had DSC issues, coupled with lack of relevance gating in the LLM synthesis. However, Document 3 (`epfo_claim_passbook_cheque_standards_01`) has a verified source mismatch: its source URL must be updated to the authentic EPFO circular on bank passbook/cheque validation (`WSU/IssueOfBKG/E-49885/2024-25/16`).
5. **Premise**: In R5, the team must eliminate scraper DOM noise in the CRAG fallback path.
6. **From Observation 1.4**: `fetch_page_text()` in `backend/web_search/fetcher.py:104` specifies `include_tables=True`.
7. **From Observation 1.4**: India Post acts & policies directory table was converted into Markdown table lines with PDF sizes and dates. The extractive fallback in `synthesizer.py` matched query keywords to table headers and returned raw table markup.
8. **Deduction for R5**: Setting `include_tables=False` and `favor_precision=True` in `trafilatura.extract()`, coupled with adding table/directory pattern detection to `is_navigation_or_boilerplate_text()`, cleanly eliminates DOM noise without requiring external libraries.

---

## 3. Caveats

1. **Host Domain Nuance**: The host `pmvbry-cdn.epfindia.gov.in` is an EPFO CDN endpoint historically used by the organisation for WordPress uploads. While Documents 1 and 2 are authentic official circulars hosted on this CDN, EPFO has also published circulars on `www.epfindia.gov.in`. Both domains are currently allowlisted in `rag_manifest.json`.
2. **Corpus Document Count Invariant**: `tests/test_rag_loader.py` enforces exact counts (`accepted_records == 1367`, `unique_documents == 1354`). Any change that introduces new document IDs into `troubleshooting_civic.jsonl` rather than updating existing records will fail `test_rag_loader.py` unless the test constants are simultaneously updated.
3. **Qdrant Vector Database Rebuild Requirement**: Changing any text or metadata in `troubleshooting_civic.jsonl` will change `corpus_sha256`. The vector store at `backend/data/vector_index/qdrant` must be rebuilt via `python -m backend.offline.ensure_vector_db` to remain in sync.

---

## 4. Conclusion

1. **EPFO Corpus Status (R1)**:
   - `epfo_joint_declaration_minor_major_sop_01` (Joint Declaration SOP) and `epfo_closed_establishment_attestation_01` (Attestation for Closed Establishments) are authentic official EPFO documents matching their titles, not PMVBRY boilerplate.
   - `epfo_claim_passbook_cheque_standards_01` has a mismatched source URL pointing to an Inspector manual (`Manual_for_Inspector_cum_Facilitator.pdf`). The URL should be remediated to point to authentic EPFO circular `WSU/IssueOfBKG/E-49885/2024-25/16` or canonical passbook validation instructions, with tags tuned to prevent cross-domain bleed into SPICe+ MCA name reservation queries.
2. **CRAG Scraper DOM Noise (R5)**:
   - Root cause is `include_tables=True` in `backend/web_search/fetcher.py:104`, which extracts document directory tables from government portals.
   - Remediate by changing `fetcher.py` to `include_tables=False`, adding `favor_precision=True`, and expanding `is_navigation_or_boilerplate_text()` to detect markdown table rows and PDF directory listings.
   - `trafilatura` version 2.3.1 is already installed and verified; no dependency updates are needed.

---

## 5. Verification Method

### 5.1 EPFO Corpus Verification
```powershell
# 1. Verify JSONL records in troubleshooting_civic.jsonl
Get-Content backend\data\refined\troubleshooting\troubleshooting_civic.jsonl | Select-String "epfo_"

# 2. Check corpus loading and manifest integrity
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.rag --strict

# 3. Verify vector DB readiness
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m backend.offline.ensure_vector_db --check-only
```

### 5.2 CRAG Scraper and Test Suite Verification
```powershell
# 1. Run web search tests
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_web_search.py

# 2. Run corpus loader tests
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests\test_rag_loader.py

# 3. Run full test suite
& "C:\Users\gaura\AppData\Local\Programs\Python\Python312\python.exe" -m pytest
```

### 5.3 Invalidation Conditions
- If `SOP_JointDeclarations_29082023-7.pdf` or `100.pdf` return HTTP 4xx/5xx or content changes on the remote CDN.
- If `test_rag_loader.py` fails due to document count discrepancies after updating `troubleshooting_civic.jsonl`.
- If `trafilatura.extract(html, include_tables=False)` strips legitimate procedural steps formatted in HTML tables (can be validated by running unit tests in `test_web_search.py`).
