from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pdfplumber
import pytesseract
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

class OCRExtractionError(Exception):
    """Raised when text extraction from a file fails."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code

@dataclass
class OCRExtractionResult:
    """Stores the extracted text and metadata from the document."""
    text: str
    metadata: dict[str, str | int]

def extract_text_from_upload(filename: str, content_type: str, content_bytes: bytes) -> OCRExtractionResult:
    """
    Extracts text from an uploaded document (PDF, Image, or Plain Text).
    
    Args:
        filename (str): The name of the uploaded file.
        content_type (str): The MIME type of the uploaded file.
        content_bytes (bytes): The raw bytes of the file.
        
    Returns:
        OCRExtractionResult: A dataclass containing the extracted text and metadata.
        
    Raises:
        OCRExtractionError: If the file type is unsupported or extraction fails.
    """
    if not content_bytes:
        raise OCRExtractionError("The uploaded file is empty.", status_code=400)

    content_type = content_type.lower()
    
    # 1. Plain Text Fallback
    if content_type.startswith("text/") or filename.lower().endswith((".txt", ".md", ".csv")):
        try:
            text = content_bytes.decode("utf-8")
            return OCRExtractionResult(text=text.strip(), metadata={"type": "text"})
        except UnicodeDecodeError as exc:
            logger.error("Failed to decode text file: %s", exc)
            raise OCRExtractionError("Failed to decode text file. Ensure it is UTF-8 encoded.", status_code=400) from exc

    # 2. PDF Processing
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return _extract_from_pdf(content_bytes)

    # 3. Image Processing (OCR via Tesseract)
    if content_type.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
        return _extract_from_image(content_bytes)

    # Unsupported format
    raise OCRExtractionError(
        f"Unsupported file type: {content_type}. Please upload a PDF, Image, or Text file.", 
        status_code=415
    )

def _extract_from_pdf(content_bytes: bytes) -> OCRExtractionResult:
    text_fragments = []
    page_count = 0
    try:
        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_fragments.append(page_text)
                    
        final_text = "\n\n".join(text_fragments).strip()
        
        if not final_text:
            logger.warning("No parseable text found in PDF. It might be a scanned image requiring full OCR.")
            # Note: For scanned PDFs, advanced implementations convert PDF pages to images and run pytesseract.
            
        return OCRExtractionResult(
            text=final_text, 
            metadata={"type": "pdf", "pages": page_count}
        )
    except Exception as exc:
        logger.exception("PDF parsing failed.")
        raise OCRExtractionError("Failed to read the PDF. The file might be corrupted or password-protected.", status_code=400) from exc

def _extract_from_image(content_bytes: bytes) -> OCRExtractionResult:
    try:
        image = Image.open(io.BytesIO(content_bytes))
        
        # Professional Pre-processing: Convert to Grayscale to improve OCR accuracy
        image = image.convert('L')
        
        text = pytesseract.image_to_string(image)
        return OCRExtractionResult(
            text=text.strip(),
            metadata={"type": "image", "format": image.format or "unknown"}
        )
    except UnidentifiedImageError as exc:
        logger.error("Unidentified image format: %s", exc)
        raise OCRExtractionError("The uploaded file does not appear to be a valid image.", status_code=400) from exc
    except pytesseract.TesseractNotFoundError as exc:
        logger.error("Tesseract is not installed on the system.")
        raise OCRExtractionError("Server OCR configuration error: Tesseract is missing.", status_code=500) from exc
    except Exception as exc:
        logger.exception("OCR processing failed.")
        raise OCRExtractionError("Failed to extract text from the image using OCR. Please ensure the image is clear.", status_code=500) from exc
