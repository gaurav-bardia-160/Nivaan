from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from backend.config import APP_NAME, APP_VERSION, CAPABILITIES, CORS_ALLOW_ORIGINS
from backend.modules.ocr import OCRExtractionError, extract_text_from_upload
from backend.modules.retrieval import knowledge_stats
from backend.pipeline import run
from backend.schemas import Answer, AskRequest

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Source-grounded assistant for government, banking, tax, and legal procedure guidance.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "invalid_request",
            "message": "The request did not match the GovBank Assistant API contract.",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.get("/api/health")
def health() -> dict[str, object]:
    stats = knowledge_stats()
    return {
        "status": "ok",
        "service": "govbank-assistant",
        "version": APP_VERSION,
        "knowledge_entries": stats["total"],
        "verified_entries": stats["verified"],
        "unverified_entries": stats["unverified"],
        "capabilities_url": "/api/capabilities",
    }


@app.get("/api/capabilities")
def capabilities() -> dict[str, object]:
    stats = knowledge_stats()
    return {
        "service": "govbank-assistant",
        "version": APP_VERSION,
        "knowledge_entries": stats,
        **CAPABILITIES,
    }


@app.post("/api/ask", response_model=Answer)
def ask(request: AskRequest) -> Answer:
    try:
        return run(request)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The assistant could not process this request safely.") from exc


@app.post("/api/ask-file", response_model=Answer)
async def ask_file(
    file: UploadFile = File(...),
    question: str = Form("Explain this document"),
    language: str = Form("en"),
) -> Answer:
    """Accept a real uploaded supported file and process it without storing it.

    Supported now: text-like files and text-based PDFs. Scanned PDFs/images are
    deliberately not claimed yet. Unsupported file types return a clear error
    instead of falling back to fake extraction.
    """

    try:
        content = await file.read()
        extracted = extract_text_from_upload(file.filename, file.content_type, content)
        request = AskRequest(
            input_type="document",
            question=question or "Explain this document",
            document_text=extracted.text,
            language=language,
            file_attached=False,
        )
        return run(request)
    except OCRExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors())) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The uploaded file could not be processed safely.") from exc


__all__ = ["app"]
