"""Empirical Adversarial Challenge Suite for Milestone 1 (R1 & R5).

Executed by challenger_m1_1 to independently stress-test DOM noise elimination,
table suppression, and boilerplate discrimination.
"""
import pytest
from bs4 import BeautifulSoup
from backend.web_search.fetcher import _extract_text, is_navigation_or_boilerplate_text
from backend.web_search.synthesizer import (
    synthesize_from_web,
    DISCRIMINATOR_FAILURE_PHRASE,
    _extract_extractive_answer,
    _select_focused_passages,
)


class TestNestedAndAdversarialTables:
    def test_pure_nested_table_is_completely_suppressed(self):
        """Adversarial Challenge: Deeply nested tables with colspan/rowspan."""
        html = """
        <html><body><main>
        <table border="1">
          <tr><th colspan="3">Ministry Document Archive</th></tr>
          <tr>
            <td rowspan="2">General Circulars</td>
            <td>
              <table>
                <tr><th>Sub-Act</th><th>Year</th></tr>
                <tr><td>Post Office Savings Bank Act</td><td>1873</td></tr>
                <tr><td>Government Savings Certificates Act</td><td>1959</td></tr>
              </table>
            </td>
            <td>Download PDF (2.5 MB)</td>
          </tr>
          <tr>
            <td>Another Nested Table</td>
            <td>Download PDF (10 MB)</td>
          </tr>
        </table>
        </main></body></html>
        """
        extracted = _extract_text(html)
        # Should be empty or considered boilerplate
        assert not extracted or is_navigation_or_boilerplate_text(extracted)
        assert "Post Office Savings Bank Act" not in extracted
        assert "|" not in extracted

    def test_malformed_unclosed_table_tags(self):
        """Adversarial Challenge: Malformed HTML with unclosed table cells and rows."""
        malformed_html = """
        <html><body><main>
        <table>
          <tr><th>Document<th>Date<th>Size
          <tr><td>Aadhaar Update SOP<td>12-05-2026<td>2.4MB
          <tr><td>Passport Manual<td>15-06-2026<td>5.1MB
        </table>
        </main></body></html>
        """
        extracted = _extract_text(malformed_html)
        assert not extracted or is_navigation_or_boilerplate_text(extracted)
        assert "|" not in extracted

    def test_mixed_procedural_page_with_nested_table(self):
        """Adversarial Challenge: Mixed page where procedural narrative must survive while table is stripped."""
        mixed_html = """
        <html><body><main>
        <h1>EPFO Joint Declaration Submission SOP</h1>
        <p>Step 1: Log in to the Member Interface of Unified Portal using UAN and password.</p>
        <p>Step 2: Go to Manage menu and click on Joint Declaration option.</p>
        <p>Step 3: Select Member ID and enter correct details as per Aadhaar.</p>
        <table>
          <tr><th>Correction Field</th><th>Permissible Supporting Documents</th><th>Max Size</th></tr>
          <tr><td>Father Name</td><td>Passport, Ration Card, Birth Certificate</td><td>2 MB</td></tr>
          <tr><td>Date of Birth</td><td>Birth Certificate, Passport, Marksheet</td><td>2 MB</td></tr>
        </table>
        <p>Step 4: Upload self-attested copies of supporting documents in PDF format.</p>
        <p>Step 5: Submit the request to the employer for online approval and digital signature.</p>
        </main></body></html>
        """
        extracted = _extract_text(mixed_html)
        assert "Step 1" in extracted
        assert "Step 5" in extracted
        assert "Correction Field" not in extracted
        assert "Permissible Supporting" not in extracted
        assert not is_navigation_or_boilerplate_text(extracted)

        # Ensure synthesizer extracts clean procedural steps
        ans = synthesize_from_web("How to submit EPFO Joint Declaration?", extracted, "https://www.epfindia.gov.in/sop")
        assert DISCRIMINATOR_FAILURE_PHRASE not in ans.summary
        assert len(ans.steps) >= 3
        # Ensure no table markup or leaked columns in steps
        for st in ans.steps:
            assert "|" not in st.detail
            assert "Correction Field" not in st.detail


class TestBoilerplateDiscriminatorEdgeCases:
    def test_catalog_without_pipes(self):
        """Adversarial Challenge: PDF directory catalog listing without markdown pipes."""
        catalog_text = (
            "List of Acceptable Documents for Aadhaar Enrolment Language: English Version 11-06-2026 "
            "Format: PDFSize: 838.3 KB Compilation of Post Office Act Rules and Regulations"
        )
        # This checks the regression bug found in test_tier1_r5_pdf_directory_catalog_rejection
        is_noise = is_navigation_or_boilerplate_text(catalog_text)
        assert is_noise is True, "Catalog listing without pipes must be detected as boilerplate"

    def test_catalog_with_file_size_and_language(self):
        """Adversarial Challenge: Catalog lines with file size and download indicator."""
        catalog_text_2 = (
            "Recruitment Notification 2026 Language: English Date: 12-08-2026 "
            "File size: 450 KB Download (PDF) Archive Document Index"
        )
        assert is_navigation_or_boilerplate_text(catalog_text_2) is True

    def test_false_positive_single_pipe_in_portal_title(self):
        """Adversarial Challenge: Legitimate portal heading with a pipe must NOT be rejected."""
        valid_civic = (
            "Parivahan Sewa | Ministry of Road Transport and Highways\n"
            "Step 1: Go to the Parivahan portal and select Driving Licence Services.\n"
            "Step 2: Enter Application Number and Date of Birth to track your DL dispatch.\n"
            "Step 3: Note the India Post tracking consignment number for delivery updates."
        )
        assert is_navigation_or_boilerplate_text(valid_civic) is False

    def test_false_positive_two_pipes_in_document_list(self):
        """Adversarial Challenge: Legitimate procedural text with 2 pipe delimiters."""
        valid_civic_2 = (
            "Document Requirements: Aadhaar Card | Passport | Voter ID\n"
            "Step 1: Bring any one of the valid photo identification documents to the counter.\n"
            "Step 2: Pay the statutory fee of Rs 200 at the fee counter.\n"
            "Step 3: Collect your biometric acknowledgment slip."
        )
        assert is_navigation_or_boilerplate_text(valid_civic_2) is False

    def test_false_positive_numbered_steps(self):
        """Adversarial Challenge: Legitimate procedure with numbered steps."""
        valid_numbered = (
            "To correct name mismatch on vehicle registration certificate:\n"
            "1. Visit the jurisdictional RTO with Form 29 and Form 30.\n"
            "2. Submit original Registration Certificate (RC) along with pencil print of chassis.\n"
            "3. Pay the prescribed fee and receive official acknowledgment receipt."
        )
        assert is_navigation_or_boilerplate_text(valid_numbered) is False

    def test_false_positive_letter_steps(self):
        """Adversarial Challenge: Legitimate procedure with lettered steps."""
        valid_lettered = (
            "Procedure to update mobile number in Aadhaar database:\n"
            "a) Locate the nearest Aadhaar Seva Kendra or designated Post Office.\n"
            "b) Fill the Aadhaar correction form available at the center.\n"
            "c) Complete biometric fingerprint verification with the operator.\n"
            "d) Collect the update request number (URN) for online tracking."
        )
        assert is_navigation_or_boilerplate_text(valid_lettered) is False

    def test_numbered_steps_with_file_size(self):
        """Adversarial Challenge: Numbered steps referencing downloadable forms and file size."""
        numbered_with_size = (
            "1. Download Form 29 (PDF, 50 KB) from the portal.\n"
            "2. Fill out details.\n"
            "3. Submit to RTO."
        )
        assert is_navigation_or_boilerplate_text(numbered_with_size) is False

    def test_lettered_steps_with_file_size(self):
        """Adversarial Challenge: Lettered steps referencing downloadable forms and file size."""
        lettered_with_size = (
            "a) Download Form 29 (PDF, 50 KB)\n"
            "b) Fill out details"
        )
        assert is_navigation_or_boilerplate_text(lettered_with_size) is False

    def test_procedural_prose_with_file_size_limits(self):
        """Adversarial Challenge: Procedural prose with file size limits and high action verb density."""
        prose_with_size = (
            "To apply for duplicate RC, visit Parivahan portal. "
            "Upload your Aadhaar card and police complaint (scanned file size: 200 KB). "
            "Submit the form and pay fee."
        )
        assert is_navigation_or_boilerplate_text(prose_with_size) is False

    def test_markdown_table_variations(self):
        """Adversarial Challenge: Diverse markdown table formatting."""
        # Standard markdown table
        t1 = "| Form | Purpose | Fee |\n|---|---|---|\n| Form 20 | Motor Vehicle Registration | Rs 600 |"
        assert is_navigation_or_boilerplate_text(t1) is True

        # Markdown table with spaces in separator
        t2 = "| Form | Purpose |\n| --- | --- |\n| Form 1 | Fitness |"
        assert is_navigation_or_boilerplate_text(t2) is True

        # Markdown table with alignment colons
        t3 = "| SNo | Act | Year |\n|:---|:---:|---:|\n| 1 | Post Act | 1898 |"
        assert is_navigation_or_boilerplate_text(t3) is True

        # Inline pipe row with PDF metadata
        t4 = "| Act Title | Date: 12-04-2026 | Format: PDFSize: 1.2 MB |"
        assert is_navigation_or_boilerplate_text(t4) is True


class TestSynthesizerInternalFilters:
    def test_extractive_answer_filters_table_lines(self):
        """Verify _extract_extractive_answer strips markdown table rows and PDF catalog sentences."""
        text = (
            "Step 1: File your application on the portal.\n"
            "| SNo | Form Name | Download Link |\n"
            "| 1 | Form 10 | Format: PDFSize: 200 KB |\n"
            "Step 2: Upload the required identity proof."
        )
        summary, steps, docs = _extract_extractive_answer(text, "How to apply?")
        for s in steps:
            assert "|" not in s["title"]
            assert "|" not in s["detail"]
            assert "PDFSize" not in s["detail"]

    def test_select_focused_passages_omits_table_lines(self):
        """Verify _select_focused_passages excludes table lines from LLM prompt excerpt."""
        text = (
            "Citizen procedure for passport re-issue under normal category.\n"
            "Step 1: Register on the Passport Seva Online Portal.\n"
            "| Column 1 | Column 2 | Column 3 |\n"
            "|---|---|---|\n"
            "| Row 1 | Row 2 | Row 3 |\n"
            "Step 2: Pay the passport fee online and schedule appointment."
        )
        focused = _select_focused_passages(text, "passport fee")
        assert "| Column 1 |" not in focused
        assert "|---|---|" not in focused
