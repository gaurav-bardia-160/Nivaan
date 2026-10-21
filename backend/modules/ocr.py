from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from backend.config import MAX_DOCUMENT_TEXT_LENGTH

MAX_UPLOAD_BYTES = 2_000_000
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".text", ".md", ".csv"}
SUPPORTED_TEXT_CONTENT_PREFIXES = ("text/",)
SUPPORTED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}


def _is_tesseract_available() -> bool:
    custom_path = os.getenv("TESSERACT_PATH", "")
    if custom_path and os.path.exists(custom_path):
        return True
    if shutil.which("tesseract"):
        return True
    for p in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.exists(p):
            return True
    return False


def _get_tesseract_cmd() -> str | None:
    custom_path = os.getenv("TESSERACT_PATH", "")
    if custom_path and os.path.exists(custom_path):
        return custom_path
    cmd = shutil.which("tesseract")
    if cmd:
        return cmd
    for p in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.exists(p):
            return p
    return None


class OCRExtractionError(Exception):
    """Raised when uploaded file text extraction cannot be completed safely."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class OCRExtractionResult:
    """Extracted text and basic metadata from an uploaded file."""

    text: str
    metadata: dict[str, str | int]


def extract_text_from_upload(filename: str | None, content_type: str | None, content_bytes: bytes) -> OCRExtractionResult:
    """Extract text from a supported upload without storing it on disk.

    Supported:
    - text-like files (.txt, .md, .csv)
    - text-based PDFs with selectable text
    - scanned PDFs and images (.png, .jpg, .webp) when Tesseract-OCR is available
    """

    safe_filename = filename or "uploaded-file"
    safe_content_type = (content_type or "").lower()
    suffix = Path(safe_filename).suffix.lower()

    if not content_bytes:
        raise OCRExtractionError("The uploaded file is empty.", status_code=400)

    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise OCRExtractionError(
            f"The uploaded file is too large. The current limit is {MAX_UPLOAD_BYTES // 1_000_000} MB.",
            status_code=413,
        )

    if suffix in IMAGE_EXTENSIONS or safe_content_type.startswith("image/"):
        if not _is_tesseract_available():
            raise OCRExtractionError(
                "Image OCR is not enabled on this host. Please install Tesseract-OCR or upload a text file / selectable PDF.",
                status_code=415,
            )
        return _extract_from_image(content_bytes)

    if suffix == ".pdf" or safe_content_type in SUPPORTED_PDF_CONTENT_TYPES:
        return _extract_from_pdf(content_bytes)

    if suffix in SUPPORTED_TEXT_EXTENSIONS or safe_content_type.startswith(SUPPORTED_TEXT_CONTENT_PREFIXES):
        text = _decode_text(content_bytes)
        text = _clean_text(text)
        _ensure_text_is_usable(text)
        return OCRExtractionResult(text=text, metadata={"type": "text"})

    raise OCRExtractionError(
        "Only readable text files and text-based PDFs are supported in this build. Image OCR is planned later.",
        status_code=415,
    )


def _extract_from_image(content_bytes: bytes) -> OCRExtractionResult:
    try:
        from PIL import Image
        import pytesseract

        tess_cmd = _get_tesseract_cmd()
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd

        img = Image.open(io.BytesIO(content_bytes))
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        raw_text = pytesseract.image_to_string(img)
        cleaned = _clean_text(raw_text)
        _ensure_text_is_usable(cleaned)
        return OCRExtractionResult(text=cleaned, metadata={"type": "image_ocr", "format": img.format or "image"})
    except OCRExtractionError:
        raise
    except Exception as exc:
        raise OCRExtractionError(f"Image OCR processing failed: {exc}", status_code=400) from exc


def _ocr_pdf_pages(content_bytes: bytes) -> list[str]:
    fragments: list[str] = []
    try:
        from PIL import Image
        import pytesseract

        tess_cmd = _get_tesseract_cmd()
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd

        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            for page in pdf.pages[:5]:  # limit to first 5 pages for responsiveness
                img = page.to_image(resolution=150).original
                text = pytesseract.image_to_string(img)
                if text.strip():
                    fragments.append(text.strip())
    except Exception:
        pass
    return fragments


def _extract_from_pdf(content_bytes: bytes) -> OCRExtractionResult:
    text_fragments: list[str] = []
    page_count = 0
    try:
        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_fragments.append(page_text)
    except Exception as exc:
        raise OCRExtractionError(
            "The PDF could not be read. The file might be corrupted, encrypted, or password-protected.",
            status_code=400,
        ) from exc

    final_text = _clean_text("\n\n".join(text_fragments))
    if not final_text:
        if _is_tesseract_available():
            ocr_fragments = _ocr_pdf_pages(content_bytes)
            if ocr_fragments:
                final_text = _clean_text("\n\n".join(ocr_fragments))

        if not final_text:
            raise OCRExtractionError(
                "No selectable text was found in this PDF. Scanned PDFs need OCR, which is planned later.",
                status_code=415,
            )

    _ensure_text_is_usable(final_text)
    return OCRExtractionResult(text=final_text, metadata={"type": "pdf", "pages": page_count})


def _decode_text(content_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise OCRExtractionError("Failed to decode text file. Use UTF-8 text or paste the content.", status_code=415)


def _clean_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _ensure_text_is_usable(text: str) -> None:
    if not text:
        raise OCRExtractionError("No readable text was found in the uploaded file.", status_code=400)
    if len(text) > MAX_DOCUMENT_TEXT_LENGTH:
        raise OCRExtractionError(
            f"The extracted text is too long. Keep it under {MAX_DOCUMENT_TEXT_LENGTH} characters.",
            status_code=413,
        )


__all__ = ["OCRExtractionError", "OCRExtractionResult", "extract_text_from_upload", "_is_tesseract_available"]
