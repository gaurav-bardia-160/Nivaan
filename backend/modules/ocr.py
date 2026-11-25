from __future__ import annotations

import io
import logging
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber

from backend.config import MAX_DOCUMENT_TEXT_LENGTH

logger = logging.getLogger("nivaan.ocr")

MAX_UPLOAD_BYTES = 15_000_000  # 15 MB limit for mobile photos and scanned documents
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".text", ".md", ".csv", ".log", ".json"}
SUPPORTED_TEXT_CONTENT_PREFIXES = ("text/",)
SUPPORTED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".tiff", ".tif", ".webp"}
DOCX_EXTENSIONS = {".docx"}
DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_RAPID_OCR_INSTANCE: Any = None
_RAPID_OCR_INITIALIZED: bool = False


def _get_rapid_ocr_engine() -> Any:
    """Return the cached RapidOCR engine or initialize it once."""
    global _RAPID_OCR_INSTANCE, _RAPID_OCR_INITIALIZED
    if _RAPID_OCR_INITIALIZED:
        return _RAPID_OCR_INSTANCE
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR  # type: ignore[no-redef]
        _RAPID_OCR_INSTANCE = RapidOCR()
    except Exception as exc:
        logger.warning("RapidOCR initialization failed: %s", exc)
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
    return _get_tesseract_cmd() is not None


def _get_tesseract_cmd() -> str | None:
    custom_path = os.getenv("TESSERACT_PATH", "").strip()
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
    metadata: dict[str, str | int | bool]


def extract_text_from_upload(
    filename: str | None,
    content_type: str | None,
    content_bytes: bytes,
) -> OCRExtractionResult:
    """Extract text from a supported upload in memory without writing to disk."""
    safe_filename = filename or "uploaded-file"
    safe_content_type = (content_type or "").lower().strip()
    suffix = Path(safe_filename).suffix.lower()

    if not content_bytes:
        raise OCRExtractionError("The uploaded file is empty.", status_code=400)

    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise OCRExtractionError(
            f"The uploaded file is too large. Keep uploads under {MAX_UPLOAD_BYTES // 1_000_000} MB.",
            status_code=413,
        )

    if suffix in IMAGE_EXTENSIONS or safe_content_type.startswith("image/"):
        if not is_ocr_available():
            raise OCRExtractionError(
                "Image OCR is not installed in this Python environment. Run: pip install rapidocr-onnxruntime onnxruntime pillow",
                status_code=415,
            )
        return _extract_from_image(content_bytes)

    if suffix == ".pdf" or safe_content_type in SUPPORTED_PDF_CONTENT_TYPES:
        return _extract_from_pdf(content_bytes)

    if suffix in DOCX_EXTENSIONS or safe_content_type in DOCX_CONTENT_TYPES:
        return _extract_from_docx(content_bytes)

    if suffix in SUPPORTED_TEXT_EXTENSIONS or safe_content_type.startswith(SUPPORTED_TEXT_CONTENT_PREFIXES):
        text = _decode_text(content_bytes)
        text = _clean_text(text)
        text, truncated = _normalize_and_validate_text(text)
        return OCRExtractionResult(text=text, metadata={"type": "text", "truncated": truncated})

    raise OCRExtractionError(
        "Unsupported file format. Upload an image (.png, .jpg, .webp), PDF (.pdf), Word doc (.docx), or text file (.txt, .md, .csv).",
        status_code=415,
    )


def _run_ocr_on_pil_image(img: Any) -> tuple[str, str]:
    """Run RapidOCR (with Tesseract fallback) on a normalized PIL image."""
    raw_text = ""
    engine_used = get_ocr_engine_name() or "ocr"

    # Convert PIL image to RGB PNG bytes so every version of RapidOCR accepts it cleanly
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    png_bytes = png_buf.getvalue()

    rapid_engine = _get_rapid_ocr_engine()
    if rapid_engine is not None:
        try:
            ocr_result, _ = rapid_engine(png_bytes)
            if ocr_result:
                lines = [
                    str(line[1]).strip()
                    for line in ocr_result
                    if line
                    and len(line) >= 2
                    and str(line[1]).strip()
                    and (len(line) < 3 or float(line[2]) >= 0.15)
                ]
                raw_text = "\n".join(lines)
                engine_used = "rapidocr"
        except Exception as exc:
            logger.exception("RapidOCR failed during image inference: %s", exc)
            raw_text = ""

    if not raw_text.strip() and _has_tesseract_binary():
        try:
            import pytesseract

            tess_cmd = _get_tesseract_cmd()
            if tess_cmd:
                pytesseract.pytesseract.tesseract_cmd = tess_cmd
            raw_text = pytesseract.image_to_string(img)
            engine_used = "tesseract"
        except Exception as exc:
            logger.exception("Tesseract OCR failed during image inference: %s", exc)

    return raw_text, engine_used


def _extract_from_image(content_bytes: bytes) -> OCRExtractionResult:
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(content_bytes))
        img_format = img.format or "image"

        # 1. Fix EXIF camera rotation from smartphone photos
        try:
            img = ImageOps.exif_transpose(img) or img
        except Exception:
            pass

        # 2. Convert palette/RGBA/CMYK images to standard RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 3. Resize oversized smartphone photos while keeping text crisp
        max_dim = 2600
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        raw_text, engine_used = _run_ocr_on_pil_image(img)

        # 4. Retry with high-contrast grayscale if first pass found no text (faint scans)
        if not raw_text.strip():
            enhanced_img = ImageOps.autocontrast(img.convert("L")).convert("RGB")
            raw_text, engine_used = _run_ocr_on_pil_image(enhanced_img)

        cleaned = _clean_text(raw_text)
        cleaned, truncated = _normalize_and_validate_text(cleaned)
        return OCRExtractionResult(
            text=cleaned,
            metadata={
                "type": "image_ocr",
                "engine": engine_used,
                "format": img_format,
                "width": img.size[0],
                "height": img.size[1],
                "truncated": truncated,
            },
        )
    except OCRExtractionError:
        raise
    except Exception as exc:
        logger.exception("Image OCR processing failed")
        raise OCRExtractionError(f"Image OCR processing failed: {exc}", status_code=400) from exc


def _render_pdf_pages_to_images(content_bytes: bytes, max_pages: int = 10) -> list[Any]:
    images: list[Any] = []

    # 1. Primary renderer: pypdfium2 (fast, zero external system binaries needed on Windows)
    try:
        import pypdfium2

        doc = pypdfium2.PdfDocument(io.BytesIO(content_bytes))
        for page in doc[:max_pages]:
            pil_img = page.render(scale=2.0).to_pil()
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            images.append(pil_img)
        if images:
            return images
    except Exception as exc:
        logger.warning("pypdfium2 PDF rendering unavailable or failed: %s", exc)

    # 2. Secondary renderer: PyMuPDF (fitz) if installed
    try:
        import fitz  # type: ignore[import-not-found]

        doc = fitz.open(stream=content_bytes, filetype="pdf")
        for page in doc[:max_pages]:
            pix = page.get_pixmap(dpi=180)
            from PIL import Image

            pil_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(pil_img)
        if images:
            return images
    except Exception as exc:
        logger.warning("PyMuPDF PDF rendering unavailable or failed: %s", exc)

    # 3. Tertiary renderer: pdfplumber (requires Wand/ImageMagick on Windows)
    try:
        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                pil_img = page.to_image(resolution=150).original
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                images.append(pil_img)
    except Exception as exc:
        logger.warning("pdfplumber image rendering unavailable or failed: %s", exc)

    return images


def _ocr_pdf_pages(content_bytes: bytes, max_pages: int = 10) -> list[str]:
    images = _render_pdf_pages_to_images(content_bytes, max_pages=max_pages)
    if not images:
        raise OCRExtractionError(
            "Scanned PDF renderer is missing. Install pypdfium2 (`pip install pypdfium2`) to OCR scanned PDFs.",
            status_code=415,
        )

    fragments: list[str] = []
    for idx, img in enumerate(images, start=1):
        page_text, _ = _run_ocr_on_pil_image(img)
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
            "The PDF could not be read. It may be corrupted or password-protected.",
            status_code=400,
        ) from exc

    final_text = _clean_text("\n\n".join(text_fragments))

    # Return selectable digital text directly if present
    if final_text and len(final_text.strip()) >= 20:
        final_text, truncated = _normalize_and_validate_text(final_text)
        return OCRExtractionResult(
            text=final_text,
            metadata={"type": "pdf", "pages": page_count, "truncated": truncated},
        )

    # Otherwise OCR scanned PDF pages
    if not is_ocr_available():
        raise OCRExtractionError(
            "This PDF has no selectable text and OCR is not enabled. Install `rapidocr-onnxruntime` and `pypdfium2`.",
            status_code=415,
        )

    ocr_fragments = _ocr_pdf_pages(content_bytes, max_pages=10)
    final_text = _clean_text("\n\n".join(ocr_fragments))

    if not final_text:
        raise OCRExtractionError(
            "No readable text was detected in this scanned PDF. Please upload a clearer scan or photo.",
            status_code=415,
        )

    final_text, truncated = _normalize_and_validate_text(final_text)
    return OCRExtractionResult(
        text=final_text,
        metadata={
            "type": "scanned_pdf_ocr",
            "engine": get_ocr_engine_name() or "ocr",
            "pages": page_count,
            "truncated": truncated,
        },
    )


def _extract_from_docx(content_bytes: bytes) -> OCRExtractionResult:
    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        paragraphs: list[str] = []
        for elem in root.iter():
            if elem.tag.endswith("}p"):
                texts = [t.text for t in elem.iter() if t.tag.endswith("}t") and t.text]
                if texts:
                    paragraphs.append("".join(texts))
        cleaned = _clean_text("\n".join(paragraphs))
        cleaned, truncated = _normalize_and_validate_text(cleaned)
        return OCRExtractionResult(text=cleaned, metadata={"type": "docx", "truncated": truncated})
    except OCRExtractionError:
        raise
    except Exception as exc:
        raise OCRExtractionError(f"Could not read DOCX file: {exc}", status_code=400) from exc


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


def _normalize_and_validate_text(text: str) -> tuple[str, bool]:
    if not text:
        raise OCRExtractionError("No readable text was found in the uploaded file.", status_code=400)
    if len(text) > MAX_DOCUMENT_TEXT_LENGTH:
        return text[:MAX_DOCUMENT_TEXT_LENGTH].rstrip(), True
    return text, False


__all__ = [
    "OCRExtractionError",
    "OCRExtractionResult",
    "extract_text_from_upload",
    "is_ocr_available",
    "_is_tesseract_available",
    "get_ocr_engine_name",
    "IMAGE_EXTENSIONS",
]
