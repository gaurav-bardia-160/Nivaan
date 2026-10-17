from __future__ import annotations

import pytest
from backend.offline.refiner import (
    clean_markdown,
    compute_quality_score,
    detect_language,
    extract_section,
    extract_tags,
    split_into_sentences,
    chunk_document,
)


def test_clean_markdown_unescapes_html_and_removes_comment_artifacts():
    raw = (
        "## Policy &amp; Terms\n\n"
        "Here is the user&#39;s application guide. -->\n"
        "<!-- internal note -->\n"
        "Charges are Rs. 50/- including GST.\n"
    )
    cleaned = clean_markdown(raw, "pan")

    assert "&amp;" not in cleaned
    assert "&#39;" not in cleaned
    assert "&" in cleaned
    assert "'" in cleaned
    assert "-->" not in cleaned
    assert "internal note" not in cleaned
    assert "Charges are Rs. 50/-" in cleaned


def test_clean_markdown_strips_uidai_boilerplate_app_footer():
    raw = (
        "# Aadhaar Enrolment Guide\n\n"
        "To enrol for Aadhaar, visit an authorized Aadhaar Seva Kendra.\n"
        "Bring valid Proof of Identity and Proof of Address.\n\n"
        "### How to download the Aadhaar app?\n"
        "You can download the Aadhaar app on Android from Google Play Store.\n"
        "### UIDAI Head Office\n"
        "Bangla Sahib Road, New Delhi\n"
    )
    cleaned = clean_markdown(raw, "uidai")

    assert "Aadhaar Enrolment Guide" in cleaned
    assert "Proof of Identity" in cleaned
    assert "How to download the Aadhaar app" not in cleaned
    assert "UIDAI Head Office" not in cleaned


def test_clean_markdown_removes_markdown_image_links():
    raw = (
        "#[!](https://example.gov.in/logo.png) PAN Card Portal\n\n"
        "![Banner](https://example.gov.in/banner.jpg)\n\n"
        "Form 49A is for Indian citizens.\n"
    )
    cleaned = clean_markdown(raw, "pan")

    assert "[!]" not in cleaned
    assert "![Banner]" not in cleaned
    assert "Form 49A is for Indian citizens" in cleaned


def test_sentence_splitter_protects_currencies_and_abbreviations():
    text = (
        "Delivery fee is Rs. 8.26/- (inclusive of GST). "
        "Form No. 49A is verified by Dr. Sharma. "
        "Please visit the official portal for submission."
    )
    sentences = split_into_sentences(text)

    assert len(sentences) == 3
    assert sentences[0] == "Delivery fee is Rs. 8.26/- (inclusive of GST)."
    assert sentences[1] == "Form No. 49A is verified by Dr. Sharma."
    assert sentences[2] == "Please visit the official portal for submission."


def test_extract_section_removes_markdown_links_and_image_links():
    chunk_1 = "### [!](https://example.com/logo) Download e-PAN\n\nInstructions follow..."
    section_1 = extract_section(chunk_1, "Default Title")
    assert section_1 == "Download e-PAN"

    chunk_2 = "## [How to Update Mobile](https://example.com/update)\n\nSteps follow..."
    section_2 = extract_section(chunk_2, "Default Title")
    assert section_2 == "How to Update Mobile"

    chunk_3 = "Just paragraph text without any heading."
    section_3 = extract_section(chunk_3, "Fallback Title")
    assert section_3 == "Fallback Title"


def test_compute_quality_score_is_calibrated():
    high_quality_civic_text = (
        "## Documents Required for PAN Card\n\n"
        "Applicants must submit valid Proof of Identity, Proof of Address, and Proof of Date of Birth. "
        "For Indian citizens, Form 49A is applicable. The fee for physical PAN card dispatch within India is Rs. 107. "
        "Applicants can verify their PAN status online using the 15-digit acknowledgement number.\n\n"
        "- Voter ID or Passport can be used as Proof of Identity.\n"
        "- Electricity bill or Bank statement can be used as Proof of Address.\n"
        "- Birth certificate or Matriculation certificate can be used for Date of Birth.\n"
    )
    score_high = compute_quality_score(
        high_quality_civic_text,
        title="Documents for PAN",
        section="Documents Required",
        url="https://incometax.gov.in/help",
    )
    assert 0.85 <= score_high <= 0.98

    low_quality_noise = "click here submit reset enter captcha now choose option"
    score_low = compute_quality_score(
        low_quality_noise,
        title="Unknown",
        section="Unknown",
        url="https://example.com",
    )
    assert score_low < 0.70


def test_detect_language_identifies_scripts():
    en_text = "This is standard English civic procedure documentation."
    hi_text = "आधार कार्ड डाउनलोड करने के लिए आधिकारिक पोर्टल पर जाएं।"
    mixed_text = "PAN कार्ड डाउनलोड करने के लिए Acknowledgement Number दर्ज करें।"

    assert detect_language(en_text) == "en"
    assert detect_language(hi_text) == "hi"
    assert detect_language(mixed_text) == "mixed"


def test_chunk_document_respects_boundaries_and_min_words():
    doc = (
        "# Main Heading\n\n" + "This is a meaningful sentence with civic content. " * 30 +
        "\n\n## Sub Heading\n\n" + "Here is another section with details on authentication and verification. " * 25
    )
    chunks = chunk_document(doc, min_words=40)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.split()) >= 40


def test_extract_tags_covers_pan_and_uidai():
    pan_tags = extract_tags("Apply for new PAN card using Form 49A with e-KYC and AO code.", "pan")
    assert "pan" in pan_tags
    assert "form 49a" in pan_tags
    assert "kyc" in pan_tags
    assert "ao code" in pan_tags

    uidai_tags = extract_tags("Download e-Aadhaar and update biometric lock on PVC card.", "uidai")
    assert "aadhaar" in uidai_tags
    assert "download" in uidai_tags
    assert "biometric" in uidai_tags
    assert "lock" in uidai_tags
    assert "pvc" in uidai_tags
