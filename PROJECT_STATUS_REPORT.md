# GovBank Assistant: Current Status, Gaps, and Production Build Plan

Generated after full repo audit.

## 1. Honest current status

GovBank Assistant is no longer just a skeleton. It now has:

- A working FastAPI backend.
- A working typed-question `/api/ask` path.
- Strict Pydantic contracts.
- Starter retrieval over a small knowledge base.
- Server-side sensitive data masking for text inputs.
- A real frontend UI with HTML, CSS, and JavaScript.
- A sample answer that validates against the backend `Answer` schema.
- Automated backend tests.

Latest validated backend test result:

```text
41 passed
```

Current overall readiness:

| Area | Rating | Reason |
|---|---:|---|
| Concept strength | 8.5/10 | Real communication problem, strong social usefulness |
| Backend foundation | 8.6/10 | API, schemas, retrieval, masking, risk flagging, text upload, and tests work |
| Frontend UI | 6/10 | Real UI exists, but upload and live edge handling are incomplete |
| Knowledge/data quality | 4/10 | Only 3 entries, all still marked unverified |
| Document upload workflow | 4.5/10 | Real `.txt` upload works through backend. PDF/image OCR still not built |
| Production readiness | 3.5/10 | Missing deployment/security/config/observability and full workflows |
| Demo readiness | 6.5/10 | Typed question demo can work, document upload demo is not reliable yet |

## 2. What is working now

### Backend

Working:

- `GET /api/health`
- `POST /api/ask`
- Request validation through `AskRequest`
- Structured `Answer` output
- Knowledge base schema validation
- Retrieval for PAN, ITR basics, and loan agreement topics
- Unsupported question refusal instead of guessing
- Server-side masking for:
  - Aadhaar
  - PAN
  - phone
  - email
  - IFSC
  - bank account number patterns
- Health metadata:
  - version
  - total knowledge entries
  - verified/unverified counts
- JSON validation error response

Validated by automated tests:

- Knowledge base shape
- Retrieval hits
- Unsupported retrieval misses
- API health
- API ask
- API invalid input rejection
- Document text masking
- File-only upload rejection until OCR exists

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
- fallback mock responses
- structured answer rendering:
  - summary
  - documents
  - steps
  - warnings
  - source
  - disclaimer
  - masked items

Static file size evidence:

```text
frontend/index.html: 164 lines
frontend/app.js: 761 lines
frontend/style.css: 936 lines
frontend/sample_answer.json: valid against backend Answer schema
```

## 3. Major gaps blocking a truly useful product

### Gap 1: PDF/image documents are not actually processed end-to-end

Current state:

- Frontend lets users select files.
- For text files, frontend reads text into `attachedFile.textContent`.
- But `sendMessage()` does not send `document_text` to the backend.
- It only sends `file_attached: true`.
- Backend correctly rejects file-only upload because OCR is not implemented.
- Frontend then falls back to mock answers.

Impact:

- Text document upload now has a real backend path through `/api/ask-file`.
- PDF/image upload is not a valid OCR workflow yet.

Required fix:

- Frontend should send `document_text` for text files.
- Backend should accept actual multipart upload for PDF/image later.
- OCR module should extract text safely.

### Gap 2: OCR module is placeholder

Current file:

```text
backend/modules/ocr.py
```

Status:

- Placeholder only.

Required useful version:

- Accept uploaded file bytes.
- Support `.txt` first.
- Support text PDFs next with `pdfplumber` or `pypdf`.
- Support images later with Tesseract or a vision API.
- Enforce file size and file type limits.
- Never persist uploads unless explicitly configured.

### Gap 3: Flagger is placeholder

Current file:

```text
backend/modules/flagger.py
```

Status:

- Placeholder only.

Required useful version:

Detect and explain:

- late payment penalty
- prepayment/foreclosure charges
- strict deadlines
- auto-renewal clauses
- hidden/add-on fees
- legal response windows

Output should use backend `Warning` shape.

### Gap 4: Knowledge base is too small and unverified

Current data:

- PAN card guide
- ITR basics guide
- loan agreement guide

All are marked:

```json
"status": "unverified"
```

Impact:

- System correctly reports low confidence.
- Cannot claim official accuracy yet.

Required production path:

- Add 8 to 12 high-quality entries.
- Verify each with official sources.
- Store source name, URL, and last verified date.
- Keep volatile facts generic unless checked live.

Priority entries:

1. PAN card application
2. PAN correction/update
3. ITR filing basics
4. Bank account opening/KYC
5. Loan agreement explanation
6. Loan prepayment/foreclosure explanation
7. Cheque bounce notice basics
8. Legal notice response basics
9. Government scheme eligibility explainer
10. Aadhaar update guidance

### Gap 5: Frontend privacy wording is too strong

Current UI says things like:

```text
Privacy-by-Design
Aadhaar, PAN, phone & accounts masked before processing.
```

Reality:

- Masking currently happens in backend after request reaches server.
- Client-side masking is not implemented.

Required fix:

- Either implement client-side masking before network request, or soften wording.
- Correct wording for now:

```text
Sensitive values are masked by the backend before retrieval and explanation.
Do not upload real confidential documents during demo.
```

### Gap 6: Translation and voice modules are placeholders

Current file:

```text
backend/modules/translate_voice.py
```

Status:

- Placeholder only.

Current frontend language dropdown translates UI labels only.
It does not translate backend answers.

Required:

- Start with deterministic no-op for English.
- Add optional Hindi/Gujarati answer translation later.
- Do not claim full multilingual answer support until this is real.

### Gap 7: Agent/tools/offline pipeline are placeholders

Placeholder files:

```text
backend/modules/agent.py
backend/modules/tools.py
backend/offline/crawl.py
backend/offline/clean_chunk.py
backend/offline/structure.py
backend/offline/verify.py
backend/offline/build_index.py
```

For the current conclave demo, these are optional.
Do not build full crawler first.
Build user workflow first.

### Gap 8: Documentation is outdated

`README.md`, `PROJECT_AGENT_BRIEF.txt`, and `PROJECT_STRUCTURE.txt` still say the project is a skeleton or not runnable.

Reality has changed.

Required:

- Update README with real run instructions.
- Add current status.
- Add what works and what does not.
- Add demo script.
- Add privacy warning.

## 4. Production-level build strategy

Do not try to build everything at once.
Build the project in precise, testable slices.

### Phase A: Make current text workflow solid

Goal:

Typed question from frontend to backend works reliably.

Tasks:

1. Ensure frontend request matches backend schema.
2. Ensure error messages show in UI instead of silent mock fallback.
3. Keep mock fallback only behind a visible label.
4. Add frontend integration test plan.
5. Update README run instructions.

Acceptance checks:

- Frontend served locally returns 200.
- Backend `/api/health` returns 200.
- Typing PAN query returns real backend PAN answer.
- Unsupported query displays safe refusal.
- UI shows source and disclaimer.

### Phase B: Make document text workflow real

Goal:

Pasted document text or `.txt` upload works end-to-end.

Tasks:

1. Frontend sends `document_text` when a text file is attached.
2. Backend accepts document text.
3. Backend masks sensitive data.
4. Backend retrieves matching guide.
5. Backend returns masked item list.
6. UI displays masked items clearly.

Acceptance checks:

- Upload fake `.txt` loan agreement.
- PAN/phone are not echoed in summary.
- Answer title is loan agreement guide.
- Masked items show PAN and phone.

### Phase C: Add real flagger

Goal:

The system identifies risk points in document text.

Tasks:

1. Implement `flagger.py` rule-based scanner.
2. Add patterns for penalty, deadline, foreclosure, auto-renewal, hidden fees.
3. Add flagger output into pipeline warnings.
4. Add tests with fake loan/legal notice text.

Acceptance checks:

- Fake loan text with prepayment charge returns warning.
- Fake notice with `within 15 days` returns deadline warning.
- No invented legal advice.

### Phase D: Add safe OCR/file handling

Goal:

Support real file upload in backend.

Tasks:

1. Add multipart endpoint or extend `/api/ask` carefully.
2. Add upload size/type limits.
3. Add `.txt` support first.
4. Add PDF text extraction.
5. Add image OCR only after PDF works.
6. Do not store uploads.

Acceptance checks:

- Unsupported file type rejected.
- Oversized file rejected.
- Fake PDF text extracted.
- Extracted text goes through privacy masking before retrieval/explanation.

### Phase E: Expand and verify knowledge base

Goal:

Make answers genuinely useful.

Tasks:

1. Add 8 to 12 entries.
2. Verify sources manually.
3. Mark verified only after checking.
4. Add tests for each guide.
5. Avoid hardcoding volatile fees unless recently verified.

Acceptance checks:

- Every entry has source URL and date.
- Retrieval tests cover each guide.
- Unsupported topics refuse to guess.

### Phase F: Translation and voice

Goal:

Support accessible output.

Tasks:

1. Translate answer fields, not URLs/dates.
2. Add Hindi/Gujarati carefully.
3. Add browser TTS or backend gTTS optional.
4. Label machine translation clearly.

Acceptance checks:

- English answer remains unchanged.
- Hindi/Gujarati output preserves official terms like PAN, ITR, RBI.
- Source URL and date remain unchanged.

### Phase G: Demo and deployment polish

Goal:

Conclave-ready demo.

Tasks:

1. Add demo dataset and fake docs.
2. Add one-click start instructions.
3. Add deployment notes.
4. Add user test evidence.
5. Record backup demo video.

Acceptance checks:

- Fresh clone can run backend and frontend.
- Demo script works without real personal data.
- User can complete a PAN query and loan document example.

## 5. Immediate next build recommendation

The next best coding step is not OCR yet.

The next best step is:

```text
Phase A + Phase B
```

Why:

- It connects what already exists.
- It makes the app genuinely useful for typed questions and pasted/text documents.
- It avoids pretending PDF/image upload works before OCR exists.
- It makes frontend and backend behave honestly together.

Immediate tasks:

1. Update frontend to send `document_text` for text files.
2. Show API validation errors in the UI instead of silently falling back.
3. Clearly label fallback mock mode.
4. Update README and project brief to current truth.
5. Add tests for text document flow.

## 6. Harsh truth

This is a valid and useful project idea.
It can become strong.
But it is not production-ready yet.

The biggest danger is overclaiming:

- Do not claim real OCR upload until it exists.
- Do not claim client-side privacy until it exists.
- Do not claim verified official accuracy until entries are verified.
- Do not claim full multilingual answer support until backend translation exists.

The correct positioning right now:

```text
GovBank Assistant currently supports source-grounded typed questions and pasted document text through a tested backend foundation. The next phase is making document text upload, risk flagging, and verified knowledge expansion production-grade.
```
