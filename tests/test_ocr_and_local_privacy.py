from __future__ import annotations

import io
from PIL import Image, ImageDraw
import pytest
from fastapi.testclient import TestClient

import backend.config
from backend.main import app
from backend.modules.guardrails import mask_text
from backend.modules.memory import conversation_memory
from backend.modules.ocr import (
    MAX_UPLOAD_BYTES,
    OCRExtractionError,
    extract_text_from_upload,
    get_ocr_engine_name,
    is_ocr_available,
)
from backend.pipeline import run
from backend.schemas import AskRequest

client = TestClient(app)


def _build_test_image(text_lines: list[str], img_format: str = "PNG") -> bytes:
    img = Image.new("RGB", (650, 60 * len(text_lines) + 40), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 20
    for line in text_lines:
        draw.text((20, y), line, fill=(0, 0, 0))
        y += 50
    buf = io.BytesIO()
    img.save(buf, format=img_format)
    return buf.getvalue()


def test_ocr_is_available_and_reports_rapidocr():
    assert is_ocr_available() is True
    engine = get_ocr_engine_name()
    assert engine in ("rapidocr", "tesseract")


def test_extract_text_from_image_png():
    img_bytes = _build_test_image(["INCOME TAX NOTICE U/S 143(1)", "PAN: ABCDE1234F REF: 2026849201"])
    result = extract_text_from_upload("notice.png", "image/png", img_bytes)

    assert result.metadata["type"] == "image_ocr"
    assert result.metadata["engine"] in ("rapidocr", "tesseract")
    assert "NOTICE" in result.text or "INCOME" in result.text or "143" in result.text


def test_extract_text_from_image_jpg():
    img_bytes = _build_test_image(["PASSPORT APPLICATION FORM 49A", "STATE BANK OF INDIA IFSC SBIN0001234"], img_format="JPEG")
    result = extract_text_from_upload("doc.jpg", "image/jpeg", img_bytes)

    assert result.metadata["type"] == "image_ocr"
    assert "PASSPORT" in result.text or "APPLICATION" in result.text or "BANK" in result.text


def test_extract_text_from_scanned_pdf():
    # Render an image as a 1-page PDF without font streams (pure scanned image PDF)
    img = Image.new("RGB", (500, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), "LOAN AGREEMENT PREPAYMENT CHARGE", fill=(0, 0, 0))
    draw.text((20, 80), "LATE PAYMENT PENALTY CLAUSE", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    pdf_bytes = buf.getvalue()

    result = extract_text_from_upload("scanned_agreement.pdf", "application/pdf", pdf_bytes)
    assert result.metadata["type"] in ("scanned_pdf_ocr", "pdf")
    assert "AGREEMENT" in result.text or "PAYMENT" in result.text or "PENALTY" in result.text or "LOAN" in result.text


def test_extract_text_rejects_empty_and_oversize():
    with pytest.raises(OCRExtractionError) as exc_info:
        extract_text_from_upload("empty.png", "image/png", b"")
    assert exc_info.value.status_code == 400

    huge_bytes = b"x" * (MAX_UPLOAD_BYTES + 1)
    with pytest.raises(OCRExtractionError) as exc_info:
        extract_text_from_upload("huge.png", "image/png", huge_bytes)
    assert exc_info.value.status_code == 413


def test_local_ai_no_masking_when_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_PII_MASKING", "false")
    backend.config.ENABLE_PII_MASKING = False

    raw_input = "My PAN is ABCDE1234F, account no 123456789012, and IFSC is SBIN0001234."
    res = mask_text(raw_input)

    # In local AI mode, raw numbers are preserved with full fidelity
    assert res.text == raw_input
    assert res.masked_items == []


def test_local_ai_pipeline_preserves_raw_identifiers(monkeypatch):
    monkeypatch.setenv("ENABLE_PII_MASKING", "false")
    backend.config.ENABLE_PII_MASKING = False
    conversation_memory.clear("unmasked-test")

    ans = run(
        AskRequest(
            input_type="question",
            question="My PAN is ABCDE1234F. How do I apply for a PAN card?",
            conversation_id="unmasked-test",
        )
    )

    assert "pan" in ans.title.lower()
    assert ans.masked_items == []

    turns = conversation_memory.recent("unmasked-test")
    assert turns
    assert "ABCDE1234F" in turns[0].user_text
    assert "[PAN]" not in turns[0].user_text


def test_capabilities_endpoint_reports_ocr_enabled():
    res = client.get("/api/capabilities")
    assert res.status_code == 200
    payload = res.json()
    assert payload["ocr"]["enabled"] is True
    assert payload["ocr"]["engine"] in ("rapidocr", "tesseract")
    assert ".png" in payload["supported_uploads"]
    assert ".jpg" in payload["supported_uploads"]


def test_ask_file_endpoint_with_image_upload():
    img_bytes = _build_test_image(["Loan agreement terms for prepayment and late payment fee."])
    response = client.post(
        "/api/ask-file",
        data={"question": "Explain this loan agreement", "language": "en"},
        files={"file": ("loan_notice.png", img_bytes, "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Understand a loan agreement"
