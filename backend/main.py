from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from backend.pipeline import run
from backend.schemas import Answer, AskRequest

app = FastAPI(
    title="GovBank Assistant API",
    version="0.2.0",
    description="Source-grounded assistant for government, banking, tax, and legal procedure guidance.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "govbank-assistant"}


@app.post("/api/ask", response_model=Answer)
def ask(request: AskRequest) -> Answer:
    try:
        return run(request)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The assistant could not process this request safely.") from exc


__all__ = ["app"]
