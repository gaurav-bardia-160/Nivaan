from __future__ import annotations



from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from fastapi.exceptions import RequestValidationError

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse, StreamingResponse

from fastapi.encoders import jsonable_encoder

from pydantic import ValidationError



import json

import os

import time

from collections import defaultdict



from backend.config import APP_NAME, APP_VERSION, CAPABILITIES, CORS_ALLOW_ORIGINS

from backend.modules.bandit_policy import bandit_policy
from backend.modules.reward import reward_engine
from backend.modules.ocr import OCRExtractionError, extract_text_from_upload, _is_tesseract_available

from backend.modules.llm import local_llm_health

from backend.modules.memory import conversation_memory

from backend.modules.retrieval import knowledge_stats

from backend.pipeline import run, run_stream

from backend.rag.runtime import rag_health

from backend.schemas import Answer, AskRequest, FeedbackRequest



# Metrics state

_METRICS = {

    "start_time": time.time(),

    "total_requests": 0,

    "successful_requests": 0,

    "failed_requests": 0,

    "rag_queries": 0,

    "verified_hits": 0,

    "unsupported_refusals": 0,

}





class InMemoryRateLimiter:

    """Sliding-window rate limiter per client IP."""



    def __init__(self, max_requests: int = 120, window_seconds: int = 60):

        self.max_requests = max_requests

        self.window_seconds = window_seconds

        self._requests: dict[str, list[float]] = defaultdict(list)



    def is_allowed(self, client_ip: str) -> tuple[bool, int]:

        now = time.time()

        window_start = now - self.window_seconds

        reqs = [t for t in self._requests[client_ip] if t > window_start]

        self._requests[client_ip] = reqs

        if len(reqs) >= self.max_requests:

            retry_after = int(reqs[0] - window_start) + 1

            return False, retry_after

        self._requests[client_ip].append(now)

        return True, 0





_RATE_LIMITER = InMemoryRateLimiter(

    max_requests=int(os.getenv("RATE_LIMIT_RPM", "120")),

    window_seconds=60,

)





def _check_rate_limit(request: Request) -> None:

    if os.getenv("RATE_LIMIT_ENABLED", "true").lower() not in ("true", "1", "yes"):

        return

    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()

    allowed, retry_after = _RATE_LIMITER.is_allowed(client_ip)

    if not allowed:

        raise HTTPException(

            status_code=429,

            detail="Too Many Requests. Please wait before retrying.",

            headers={"Retry-After": str(retry_after)},

        )





def _check_auth(request: Request) -> None:

    required_key = os.getenv("API_KEY", "").strip()

    if not required_key:

        return

    api_key = request.headers.get("X-API-Key")

    auth_header = request.headers.get("Authorization", "")

    bearer_token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""

    if api_key != required_key and bearer_token != required_key:

        raise HTTPException(status_code=401, detail="Unauthorized. Invalid or missing API key.")



app = FastAPI(

    title=APP_NAME,

    version=APP_VERSION,

    description="Source-grounded assistant for government, banking, tax, and legal procedure guidance.",

)



app.add_middleware(

    CORSMiddleware,

    allow_origins=CORS_ALLOW_ORIGINS,

    allow_credentials=False,

    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],

    allow_headers=["*"],

)





@app.middleware("http")

async def add_private_network_access_header(request: Request, call_next):

    response = await call_next(request)

    response.headers["Access-Control-Allow-Private-Network"] = "true"

    return response





@app.exception_handler(RequestValidationError)

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:

    return JSONResponse(

        status_code=422,

        content={

            "error": "invalid_request",

            "message": "The request did not match the Nivaan API contract.",

            "details": jsonable_encoder(exc.errors()),

        },

    )





@app.get("/api/health")
def health() -> dict[str, object]:
    stats = knowledge_stats()
    return {
        "status": "ok",
        "service": "nivaan",
        "version": APP_VERSION,
        "knowledge_entries": stats["total"],
        "verified_entries": stats["verified"],
        "unverified_entries": stats["unverified"],
        "capabilities_url": "/api/capabilities",
        "rag": rag_health(),
    }





@app.get("/api/capabilities")

def capabilities() -> dict[str, object]:

    from backend.modules.translator import is_translation_enabled

    stats = knowledge_stats()

    translation_on = is_translation_enabled()

    ocr_on = _is_tesseract_available()

    base_caps = dict(CAPABILITIES)

    base_caps["supported_uploads"] = list(base_caps["supported_uploads"])

    base_caps["unsupported_uploads"] = list(base_caps["unsupported_uploads"])

    if ocr_on:

        base_caps["supported_uploads"].extend(["scanned .pdf", ".png", ".jpg", ".jpeg", ".webp"])

    else:

        base_caps["unsupported_uploads"].extend(["scanned PDFs", "images without Tesseract-OCR"])

    if translation_on:

        base_caps["answer_language_status"] = (

            "English answers only by default; automatic translation into Hindi and Gujarati is currently active."

        )

    return {

        "service": "nivaan",

        "version": APP_VERSION,

        "knowledge_entries": stats,

        "rag": rag_health(),

        "translation": {

            "enabled": translation_on,

            "supported_targets": ["hi", "gu"],

            "script_auto_detection": True,

            "natural_phrase_extraction": True,

            "civic_glossary": True,

        },

        "ocr": {"enabled": ocr_on, "engine": "tesseract" if ocr_on else None},

        "local_llm": local_llm_health(),

        "memory": conversation_memory.health(),
        "rl": {
            "bandit": bandit_policy.get_stats(),
            "rewards": reward_engine.get_stats(),
        },

        **base_caps,

    }





@app.get("/api/metrics")

def metrics() -> dict[str, object]:

    now = time.time()

    uptime = round(now - _METRICS["start_time"], 2)

    return {

        "status": "healthy",

        "uptime_seconds": uptime,

        "total_requests": _METRICS["total_requests"],

        "successful_requests": _METRICS["successful_requests"],

        "failed_requests": _METRICS["failed_requests"],

        "rag_queries": _METRICS["rag_queries"],

        "verified_hits": _METRICS["verified_hits"],

        "unsupported_refusals": _METRICS["unsupported_refusals"],

        "rate_limiter": {

            "tracked_clients": len(_RATE_LIMITER._requests),

            "rpm_limit": _RATE_LIMITER.max_requests,

        },

        "ocr_available": _is_tesseract_available(),

        "local_llm": local_llm_health(),

        "memory": conversation_memory.health(),
        "rl": {
            "bandit": bandit_policy.get_stats(),
            "rewards": reward_engine.get_stats(),
        },

    }





@app.delete("/api/conversations/{conversation_id}")

def clear_conversation(conversation_id: str, req: Request) -> dict[str, object]:

    _check_auth(req)

    _check_rate_limit(req)

    if not conversation_id or len(conversation_id) > 120:

        raise HTTPException(status_code=422, detail="Invalid conversation id.")

    conversation_memory.clear(conversation_id)

    return {"status": "cleared", "conversation_id": conversation_id}





@app.post("/api/ask", response_model=Answer)

def ask(request: AskRequest, req: Request) -> Answer:

    _check_auth(req)

    _check_rate_limit(req)

    _METRICS["total_requests"] += 1

    try:

        ans = run(request)

        _METRICS["successful_requests"] += 1

        if ans.title == "No verified guide found":

            _METRICS["unsupported_refusals"] += 1

        elif ans.citations:

            _METRICS["rag_queries"] += 1

        else:

            _METRICS["verified_hits"] += 1

        return ans

    except ValidationError as exc:

        _METRICS["failed_requests"] += 1

        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    except Exception as exc:
        import traceback; traceback.print_exc()

        _METRICS["failed_requests"] += 1

        raise HTTPException(status_code=500, detail="The assistant could not process this request safely.") from exc


@app.post("/api/ask/stream")
def ask_stream(request: AskRequest, req: Request):
    _check_auth(req)
    _check_rate_limit(req)
    _METRICS["total_requests"] += 1

    def event_generator():
        try:
            for item in run_stream(request):
                event_name = item.get("event", "message")
                data_str = json.dumps(item.get("data", {}))
                yield f"event: {event_name}\ndata: {data_str}\n\n"
            _METRICS["successful_requests"] += 1
        except Exception as e:
            import traceback; traceback.print_exc()
            _METRICS["failed_requests"] += 1
            err_data = json.dumps({"message": f"An error occurred during streaming generation: {str(e)}"})
            yield f"event: error\ndata: {err_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )





@app.post("/api/ask-file", response_model=Answer)

async def ask_file(

    req: Request,

    file: UploadFile = File(...),

    question: str = Form("Explain this document"),

    language: str = Form("en"),

    conversation_id: str | None = Form(None),

    previous_entry_id: str | None = Form(None),

    context_topic: str | None = Form(None),

) -> Answer:

    """Accept a real uploaded supported file and process it without storing it.



    Supported now: text-like files, text-based PDFs, and images/scanned PDFs when OCR is available.

    Unsupported file types return a clear error instead of falling back to fake extraction.

    """

    _check_auth(req)

    _check_rate_limit(req)

    _METRICS["total_requests"] += 1



    try:

        content = await file.read()

        extracted = extract_text_from_upload(file.filename, file.content_type, content)

        request = AskRequest(

            input_type="document",

            question=question or "Explain this document",

            document_text=extracted.text,

            language=language,

            conversation_id=conversation_id,

            previous_entry_id=previous_entry_id,

            context_topic=context_topic,

            file_attached=False,

        )

        ans = run(request)

        _METRICS["successful_requests"] += 1

        return ans

    except OCRExtractionError as exc:

        _METRICS["failed_requests"] += 1

        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    except ValidationError as exc:

        _METRICS["failed_requests"] += 1

        raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors())) from exc

    except Exception as exc:

        _METRICS["failed_requests"] += 1

        raise HTTPException(status_code=500, detail="The uploaded file could not be processed safely.") from exc





@app.post("/api/feedback")
def submit_feedback(feedback: FeedbackRequest, req: Request) -> dict[str, object]:
    """Capture citizen feedback and update online Contextual Bandit and reward models."""
    _check_auth(req)
    _check_rate_limit(req)

    # 1. Retrieve or infer the bandit action taken for this query
    action = bandit_policy.get_action(feedback.conversation_id, feedback.query)
    if not action:
        action = bandit_policy.select_action(feedback.query)

    # 2. Compute multi-criteria reward score
    breakdown = reward_engine.compute_reward(
        query=feedback.query,
        feedback=feedback,
    )

    # 3. Update the LinUCB online policy weights
    bandit_policy.update(action, breakdown.total_reward)

    # 4. Log telemetry record for offline DPO preference dataset curation
    reward_engine.log_feedback(feedback, breakdown)

    return {
        "status": "success",
        "reward": breakdown.total_reward,
        "breakdown": breakdown.to_dict(),
        "applied_arm": action.name,
    }


@app.get("/api/rl-status")
def get_rl_status(req: Request) -> dict[str, object]:
    """Inspect real-time Reinforcement Learning metrics, bandit arms, and reward statistics."""
    _check_auth(req)
    return {
        "status": "healthy",
        "bandit": bandit_policy.get_stats(),
        "rewards": reward_engine.get_stats(),
    }


__all__ = ["app"]

