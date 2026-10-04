from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from backend.config import MAX_DOCUMENT_TEXT_LENGTH

MAX_UPLOAD_BYTES = 2_000_000
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".text", ".md", ".csv"}
SUPPORTED_TEXT_CONTENT_PREFIXES = ("text/",)
SUPPORTED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


class OCRExtractionError(ValueError):
    """Raised when an uploaded file cannot be safely converted to text."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ExtractedText:
    text: str
    source_type: str
    filename: str


def extract_text_from_upload(filename: str | None, content_type: str | None, data: bytes) -> ExtractedText:
    """Extract text from an uploaded file without storing it on disk.

    Current production-safe slice supports text-like files and text-based PDFs
    that contain selectable text. Scanned PDFs and image OCR are intentionally
    rejected with a clear message until OCR dependencies and tests are added.
    This prevents pretending to support confidential document OCR before it is
    safe and validated.
    """

    safe_filename = filename or "uploaded-file"
    if not data:
        raise OCRExtractionError("The uploaded file is empty.")

    if len(data) > MAX_UPLOAD_BYTES:
        raise OCRExtractionError(
            f"The uploaded file is too large. The current limit is {MAX_UPLOAD_BYTES // 1_000_000} MB.",
            status_code=413,
        )

    suffix = Path(safe_filename).suffix.lower()
    normalized_content_type = (content_type or "").lower()
    is_pdf_file = suffix == ".pdf" or normalized_content_type in SUPPORTED_PDF_CONTENT_TYPES
    is_text_file = suffix in SUPPORTED_TEXT_EXTENSIONS or normalized_content_type.startswith(
        SUPPORTED_TEXT_CONTENT_PREFIXES
    )

    if is_pdf_file:
        text = _extract_pdf_text(data)
        source_type = "pdf"
    elif is_text_file:
        text = _decode_text(data)
        source_type = "text"
    else:
        raise OCRExtractionError(
            "Only readable text files and text-based PDFs are supported in this build. Image OCR is planned next, "
            "so paste the document text or upload a .txt file for now.",
            status_code=415,
        )

    text = _clean_text(text)

    if not text:
        raise OCRExtractionError("No readable text was found in the uploaded file.")

    if len(text) > MAX_DOCUMENT_TEXT_LENGTH:
        raise OCRExtractionError(
            f"The extracted text is too long. Keep it under {MAX_DOCUMENT_TEXT_LENGTH} characters.",
            status_code=413,
        )

    return ExtractedText(text=text, source_type=source_type, filename=safe_filename)


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise OCRExtractionError("The PDF could not be read. Upload a valid text-based PDF or paste the text.") from exc

    if reader.is_encrypted:
        raise OCRExtractionError("Encrypted PDFs are not supported. Remove the password or paste the text.", status_code=415)

    pages_text: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text.strip():
            pages_text.append(page_text)

    extracted = "\n".join(pages_text).strip()
    if not extracted:
        raise OCRExtractionError(
            "No selectable text was found in this PDF. Scanned PDFs and images need OCR, which is planned next.",
            status_code=415,
        )
    return extracted


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise OCRExtractionError("The file encoding is not readable as text.", status_code=415)


def _clean_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    non_empty = [line for line in lines if line]
    return "\n".join(non_empty).strip()


__all__ = ["ExtractedText", "OCRExtractionError", "extract_text_from_upload"]
