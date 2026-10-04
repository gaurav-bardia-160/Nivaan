# GovBank Assistant: Current Status, Gaps, and Production Build Plan

Updated after the module simplification refactor.

## 1. Honest current status

GovBank Assistant is a runnable partial project, not just a skeleton. It now has:

- FastAPI backend with `/api/health`, `/api/ask`, and `/api/ask-file`.
- Strict Pydantic request and answer contracts.
- Starter retrieval over a small knowledge base.
- Server-side sensitive data masking.
- Rule-based document risk flagging.
- Text upload and text-based PDF upload handling with no disk storage.
- Honest rejection for scanned PDFs/images until OCR is implemented.
- Frontend chat UI connected to the backend.
- Consolidated backend modules: `guardrails.py`, `agent.py`, and `offline/data_builder.py`.
- Automated backend tests.

Latest validated backend test result:

```text
44 passed
```

Current overall readiness:

| Area | Rating | Reason |
|---|---:|---|
| Concept strength | 8.5/10 | Real communication problem, strong social usefulness |
| Backend foundation | 8.9/10 | API, schemas, retrieval, guardrails, routing, text/PDF upload, and tests work |
| Frontend UI | 6/10 | Real UI exists, but answer translation, stronger upload states, and polish remain |
| Knowledge/data quality | 4/10 | Only 3 entries, all still marked unverified |
| Document upload workflow | 5.8/10 | `.txt` and text-based PDF uploads work. Scanned PDF/image OCR still not built |
| Production readiness | 4/10 | Better structure now, but still missing deployment/security/observability/full data verification |
| Demo readiness | 7/10 | Typed questions and text/PDF document demos can work if demo files are selected carefully |

## 2. What is working now

### Backend

Working:

- `GET /api/health`
- `POST /api/ask`
- `POST /api/ask-file`
- Request validation through `AskRequest`
- Structured `Answer` output
- Retrieval for PAN, ITR basics, and loan agreement topics
- Unsupported question refusal instead of guessing
- Server-side masking for Aadhaar, PAN, phone, email, IFSC, and bank account number patterns
- Rule-based warnings for deadlines, penalties, prepayment/foreclosure, auto-renewal, extra fees, and legal notices
- Text file upload extraction
- Text-based PDF extraction with `pypdf`
- Scanned PDF/image rejection with clear error messages
- Offline data builder skeleton for sources, cleaning, chunking, unverified drafts, and verified knowledge-base build

Validated by automated tests:

- Knowledge base shape
- Retrieval hits and misses
- Agent routing
- Guardrail masking
- Risk flagging
- API health
- API ask
- API file upload for text files
- API file upload for text-based PDFs
- PDF failure modes
- Invalid input rejection
- Offline data builder draft flow

### Frontend

Working or present:

- Chat-style UI
- Sidebar
- language dropdown UI
- theme toggle
- quick prompt cards
- file/camera picker UI
- backend health check
- live backend request path for typed questions
- live upload path for backend file endpoint
- fallback mock responses when backend is offline
- structured answer rendering: summary, documents, steps, warnings, source, disclaimer, and masked items

Known frontend limitations:

- Language dropdown translates UI labels only, not backend answers.
- File UX still needs stronger loading/error states.
- Camera/image upload appears in UI, but backend intentionally rejects images until OCR is implemented.

## 3. Current simplified backend structure

Preferred modules for new work:

```text
backend/modules/agent.py        request routing and clarification decision
backend/modules/guardrails.py   privacy masking and risk flagging
backend/modules/retrieval.py    knowledge-base search
backend/modules/explainer.py    deterministic answer building
backend/modules/ocr.py          text and text-based PDF extraction
backend/offline/data_builder.py offline data preparation pipeline
```

Compatibility wrappers kept for older imports:

```text
backend/modules/privacy.py
backend/modules/flagger.py
backend/modules/router.py
```

The old split offline placeholder files were removed and replaced with:

```text
backend/offline/data_builder.py
```

## 4. Major gaps blocking a truly useful product

### Gap 1: Scanned PDF/image OCR is still not implemented

Current state:

- `.txt` upload works.
- Text-based PDF upload works.
- Scanned PDFs and images are rejected honestly.

Required fix:

- Add OCR only after accuracy and privacy tests are ready.
- Use either local OCR such as Tesseract/PaddleOCR or a carefully disclosed cloud OCR mode.
- Keep no-storage behavior.

### Gap 2: Knowledge base is too small and unverified

Current data:

- PAN card guide
- ITR basics guide
- loan agreement guide

All are marked `unverified`, so confidence is correctly low.

Required production path:

- Add 8 to 12 high-quality entries.
- Verify each with official sources.
- Store source URL and last verified date.
- Keep volatile facts generic unless checked live.

Priority entries:

1. PAN correction/update
2. Bank account opening/KYC
3. Loan prepayment/foreclosure explanation
4. Cheque bounce notice basics
5. Legal notice response basics
6. Government scheme eligibility explainer
7. Aadhaar update guidance
8. Consumer complaint procedure

### Gap 3: Translation and voice are not real yet

Current state:

- Frontend language dropdown changes UI labels only.
- Backend answers are not translated.
- `translate_voice.py` is still a placeholder.

Required fix:

- Start with deterministic English no-op.
- Add optional Hindi/Gujarati translation later.
- Do not claim multilingual answer support until backend answer translation exists.

### Gap 4: Client-side privacy masking is not implemented

Current state:

- Masking happens in backend after the request reaches the server.
- This is useful, but not true on-device privacy.

Required fix:

- Either add client-side masking before network upload, or keep UI wording conservative.
- Current wording should remain honest: backend masks before retrieval and explanation.

### Gap 5: Official-source updater is not built

Current state:

- Offline `data_builder.py` can load local raw source files, clean, chunk, and create unverified drafts.
- It does not crawl live websites or auto-update official facts.

Required fix:

- Add allow-listed official URLs.
- Fetch pages only when terms allow.
- Mark all AI-structured output as unverified.
- Require human approval before updating `knowledge_base.json`.

## 5. Recommended next build order

1. Expand and manually verify the knowledge base.
2. Add 5 to 8 realistic fake sample documents for demos and tests.
3. Add client-side masking or strengthen privacy wording further.
4. Add backend translation no-op plus explicit unsupported-language behavior.
5. Add scanned OCR only when ready to test privacy and accuracy.
6. Add official-source update checker with human approval.
7. Add deployment hardening: env config, CORS restrictions, request limits, logs without sensitive data, and CI.

## 6. Safe demo plan right now

Good demo paths:

- Typed question: “How do I apply for a PAN card?”
- Typed question: “What should I check in a loan agreement?”
- `.txt` document upload with fake PAN and penalty/deadline text.
- Text-based PDF upload with fake PAN and penalty/deadline text.

Avoid claiming:

- Full legal/tax/financial advice.
- Officially verified answers.
- Image/scanned PDF OCR.
- Client-side/on-device privacy.
- Real multilingual answer translation.

## 7. Short status summary

The project is now a solid applied-AI prototype with a clean backend structure and tested core workflows. The next biggest value is not more architecture. It is verified data, better sample documents, and honest privacy/translation/OCR improvements.
