from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from backend.config import APP_NAME, APP_VERSION, CORS_ALLOW_ORIGINS
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
    }


@app.post("/api/ask", response_model=Answer)
def ask(request: AskRequest) -> Answer:
    try:
        return run(request)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The assistant could not process this request safely.") from exc


__all__ = ["app"]
