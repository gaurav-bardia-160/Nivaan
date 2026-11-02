from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber

from backend.config import MAX_DOCUMENT_TEXT_LENGTH

MAX_UPLOAD_BYTES = 10_000_000  # 10 MB limit for mobile photos and scanned documents
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".text", ".md", ".csv"}
SUPPORTED_TEXT_CONTENT_PREFIXES = ("text/",)
SUPPORTED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

_RAPID_OCR_INSTANCE: Any = None
_RAPID_OCR_INITIALIZED: bool = False


def _get_rapid_ocr_engine() -> Any:
    """Return the cached RapidOCR engine or initialize it once."""
    global _RAPID_OCR_INSTANCE, _RAPID_OCR_INITIALIZED
    if _RAPID_OCR_INITIALIZED:
        return _RAPID_OCR_INSTANCE
    try:
        from rapidocr_onnxruntime import RapidOCR
        _RAPID_OCR_INSTANCE = RapidOCR()
    except Exception:
        _RAPID_OCR_INSTANCE = None
    _RAPID_OCR_INITIALIZED = True
    return _RAPID_OCR_INSTANCE


def is_ocr_available() -> bool:
    """Return True if any production OCR engine (RapidOCR or Tesseract) is available."""
    if _get_rapid_ocr_engine() is not None:
        return True
    return _has_tesseract_binary()


def _is_tesseract_available() -> bool:
    """Backwards-compatible alias for OCR readiness."""
    return is_ocr_available()


def _has_tesseract_binary() -> bool:
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


def get_ocr_engine_name() -> str | None:
    if _get_rapid_ocr_engine() is not None:
        return "rapidocr"
    if _has_tesseract_binary():
        return "tesseract"
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
    - scanned PDFs and images (.png, .jpg, .jpeg, .webp, .bmp, .tiff) via local RapidOCR/Tesseract
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
        if not is_ocr_available():
            raise OCRExtractionError(
                "Image OCR is not enabled on this host. Please install RapidOCR or Tesseract-OCR.",
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
        "Unsupported file format. Please upload an image (.png, .jpg, .webp), PDF (.pdf), or text file (.txt, .md, .csv).",
        status_code=415,
    )


def _extract_from_image(content_bytes: bytes) -> OCRExtractionResult:
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(content_bytes))

        # 1. Correct EXIF camera orientation (crucial for smartphone captures)
        try:
            img = ImageOps.exif_transpose(img) or img
        except Exception:
            pass

        # 2. Convert to RGB if palette, RGBA or other modes
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")

        # 3. Downscale if image is excessively large to keep response instant
        max_dim = 3000
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        raw_text = ""
        engine_used = get_ocr_engine_name() or "ocr"

        # 4. Try RapidOCR first (state of the art PaddleOCR v4 on ONNX)
        rapid_engine = _get_rapid_ocr_engine()
        if rapid_engine is not None:
            try:
                ocr_result, _ = rapid_engine(img)
                if ocr_result:
                    lines = [
                        line[1].strip()
                        for line in ocr_result
                        if line and len(line) >= 2 and line[1].strip() and (len(line) < 3 or line[2] >= 0.20)
                    ]
                    raw_text = "\n".join(lines)
            except Exception:
                raw_text = ""

        # 5. If RapidOCR yielded nothing, fall back to Tesseract if available
        if not raw_text.strip() and _has_tesseract_binary():
            try:
                import pytesseract
                tess_cmd = _get_tesseract_cmd()
                if tess_cmd:
                    pytesseract.pytesseract.tesseract_cmd = tess_cmd
                raw_text = pytesseract.image_to_string(img)
                engine_used = "tesseract"
            except Exception:
                pass

        cleaned = _clean_text(raw_text)
        _ensure_text_is_usable(cleaned)
        return OCRExtractionResult(
            text=cleaned,
            metadata={
                "type": "image_ocr",
                "engine": engine_used,
                "format": img.format or "image",
                "width": img.size[0],
                "height": img.size[1],
            },
        )
    except OCRExtractionError:
        raise
    except Exception as exc:
        raise OCRExtractionError(f"Image OCR processing failed: {exc}", status_code=400) from exc


def _ocr_pdf_pages(content_bytes: bytes, max_pages: int = 10) -> list[str]:
    fragments: list[str] = []
    images: list[Any] = []

    # Try pypdfium2 first for high-speed page rendering
    try:
        import pypdfium2
        doc = pypdfium2.PdfDocument(io.BytesIO(content_bytes))
        for page in doc[:max_pages]:
            pil_img = page.render(scale=2).to_pil()
            images.append(pil_img)
    except Exception:
        # Fall back to pdfplumber image conversion
        try:
            with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
                for page in pdf.pages[:max_pages]:
                    pil_img = page.to_image(resolution=150).original
                    images.append(pil_img)
        except Exception:
            pass

    rapid_engine = _get_rapid_ocr_engine()
    tess_available = _has_tesseract_binary()
    tess_cmd = _get_tesseract_cmd() if tess_available else None

    for idx, img in enumerate(images, start=1):
        page_text = ""
        # 1. Try RapidOCR
        if rapid_engine is not None:
            try:
                res, _ = rapid_engine(img)
                if res:
                    lines = [line[1].strip() for line in res if line and len(line) >= 2 and line[1].strip()]
                    page_text = "\n".join(lines)
            except Exception:
                page_text = ""

        # 2. Fall back to Tesseract
        if not page_text.strip() and tess_available:
            try:
                import pytesseract
                if tess_cmd:
                    pytesseract.pytesseract.tesseract_cmd = tess_cmd
                page_text = pytesseract.image_to_string(img)
            except Exception:
                pass

        if page_text.strip():
            fragments.append(f"--- Page {idx} ---\n{page_text.strip()}")

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
                    text_fragments.append(page_text.strip())
    except Exception as exc:
        raise OCRExtractionError(
            "The PDF could not be read. The file might be corrupted, encrypted, or password-protected.",
            status_code=400,
        ) from exc

    final_text = _clean_text("\n\n".join(text_fragments))

    # If digital text exists and is meaningful (>= 20 characters), return it
    if final_text and len(final_text.strip()) >= 20:
        _ensure_text_is_usable(final_text)
        return OCRExtractionResult(text=final_text, metadata={"type": "pdf", "pages": page_count})

    # Otherwise, attempt OCR on scanned pages
    if is_ocr_available():
        ocr_fragments = _ocr_pdf_pages(content_bytes, max_pages=10)
        if ocr_fragments:
            final_text = _clean_text("\n\n".join(ocr_fragments))

    if not final_text:
        raise OCRExtractionError(
            "No selectable text or readable OCR content was found in this PDF. Please upload a clear document.",
            status_code=415,
        )

    _ensure_text_is_usable(final_text)
    return OCRExtractionResult(text=final_text, metadata={"type": "scanned_pdf_ocr", "pages": page_count})


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


__all__ = [
    "OCRExtractionError",
    "OCRExtractionResult",
    "extract_text_from_upload",
    "is_ocr_available",
    "_is_tesseract_available",
    "get_ocr_engine_name",
    "IMAGE_EXTENSIONS",
]
