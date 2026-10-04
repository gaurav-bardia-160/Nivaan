from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from backend.config import MAX_DOCUMENT_TEXT_LENGTH

MAX_UPLOAD_BYTES = 2_000_000
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".text", ".md", ".csv"}
SUPPORTED_TEXT_CONTENT_PREFIXES = ("text/",)
SUPPORTED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}


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

    Supported now:
    - text-like files
    - text-based PDFs with selectable text

    Not supported yet:
    - scanned PDFs
    - image OCR
    - encrypted/corrupted PDFs
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
        raise OCRExtractionError(
            "Image OCR is not enabled in this build. Upload a text file, a text-based PDF, or paste the text.",
            status_code=415,
        )

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


def _extract_from_pdf(content_bytes: bytes) -> OCRExtractionResult:
    text_fragments: list[str] = []
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


__all__ = ["OCRExtractionError", "OCRExtractionResult", "extract_text_from_upload"]
