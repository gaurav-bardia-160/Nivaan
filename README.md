# GovBank Assistant

GovBank Assistant is a web app that helps users understand government, banking, tax, and legal procedures in plain language. It is designed around the communication gap between official institutions and citizens.

## Current status

The project is partially working, not fully production-ready yet.

Working now:

- FastAPI backend with `/api/health`, `/api/ask`, and `/api/ask-file`
- Strict Pydantic request/answer contracts
- Starter knowledge base with PAN, ITR basics, and loan agreement entries
- Retrieval over the starter knowledge base
- Safe refusal for unsupported questions
- Server-side masking for common sensitive values in text inputs
- Frontend chat UI with HTML, CSS, and JavaScript
- Typed question flow from frontend to backend
- Text-document flow when readable text is sent as `document_text`
- Real `.txt` and text-based PDF upload flow through `/api/ask-file`, with no disk storage and clear rejection for scanned PDFs/images
- Rule-based risk flagging for deadlines, penalties, prepayment/foreclosure, auto-renewal, extra charges, and legal notices
- Backend tests

Important limitations:

- Scanned PDF/image OCR upload is not implemented yet. The app now processes selectable-text PDFs and rejects scanned/image files honestly instead of pretending OCR works.
- Knowledge base entries are currently marked `unverified` until manually checked against live official sources.
- Translation/voice is not implemented for backend answers yet.
- Client-side privacy masking is not implemented yet. Current masking happens in the backend.
- This is an explanation helper, not legal, tax, financial, or government advice.

## Run locally

From the project root:

```bash
cd /Users/admin/govbank-assistant
python3 -m pip install -r backend/requirements.txt
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd /Users/admin/govbank-assistant
python3 -m http.server 5500 --directory frontend
```

Open:

```text
http://127.0.0.1:5500/
```

## Test

```bash
cd /Users/admin/govbank-assistant
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
```

Expected current result:

```text
43 passed
```

## Project structure

```text
backend/
  main.py                 FastAPI app
  pipeline.py             request workflow
  schemas.py              shared data contracts
  config.py               backend constants
  data/knowledge_base.json
  modules/
    retrieval.py          local knowledge retrieval
    privacy.py            server-side text masking
    router.py             request classification
    explainer.py          deterministic answer generation
    ocr.py                safe text and text-based PDF extraction, scanned/image OCR rejected for now
    flagger.py            rule-based risky clause and deadline warnings
    translate_voice.py    placeholder
frontend/
  index.html
  app.js
  style.css
  sample_answer.json
tests/
  test_a.py
  test_api.py
  test_b.py
PROJECT_STATUS_REPORT.md
```

## Next production build priorities

1. Make text-file upload send `document_text` to the backend reliably.
2. Show backend validation errors honestly in the UI instead of pretending OCR exists.
3. Implement `flagger.py` for penalties, deadlines, prepayment clauses, and risky terms.
4. Add safe backend file upload and OCR, starting with `.txt`, then text PDFs, then images.
5. Expand and manually verify the knowledge base.
6. Add translation only after core English flow is stable.

See `PROJECT_STATUS_REPORT.md` for the full audit and phased roadmap.
