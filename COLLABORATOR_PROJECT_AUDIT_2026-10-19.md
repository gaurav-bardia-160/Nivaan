# GovBank Assistant: Complete Collaborator Status and Technical Audit

**Audit date:** October 19, 2026  
**Audited branch:** `main`  
**Audited commit:** `a7b20bf69e1fdcb16b023bb6934a7167ae7f590a`  
**Repository:** `Gaurav-Bardia-160/govbank-assistant`  
**Audit method:** complete repository scan, commit comparison, static checks, automated tests, real API requests, upload tests, corpus validation, and headless-browser acceptance testing.

---

## 1. Executive summary

GovBank Assistant is now a **strong applied-AI prototype** for explaining Indian government, tax, banking, and legal procedures. It is no longer only a static chatbot demonstration. The repository contains:

- a FastAPI backend with strict request and response contracts;
- a curated, verified-guide-first answering path;
- a feature-flagged hybrid RAG pipeline using BM25, multilingual embeddings, and Qdrant;
- source citations and explicit factual-verification status;
- privacy masking before retrieval and explanation;
- Hindi and Gujarati language detection and optional answer translation;
- text and text-based PDF upload support;
- risk and deadline detection for uploaded documents;
- a styled frontend with editable prompts and persistent local chat sessions;
- offline corpus refinement and vector-index building tools;
- 91 automated tests.

### Overall assessment

| Area | Rating | Current state |
|---|---:|---|
| Conclave/demo readiness | **8.5/10** | Strong and demonstrable |
| Backend engineering | **8.2/10** | Modular, tested, and safety-oriented |
| Frontend experience | **8.0/10** | Polished and persistent, with privacy/context weaknesses |
| RAG architecture | **8.0/10** | Hybrid and multilingual, but corpus facts remain unverified |
| Data readiness | **6.5/10** | Structurally usable, not factually certified |
| Privacy readiness | **6.5/10** | Backend masking works, but raw prompts persist in localStorage |
| Production readiness | **5.5/10** | Important security, deployment, verification, and reliability work remains |
| Estimated implementation completion | **about 80% for the intended prototype** | Core workflows exist; production hardening remains |

**Verdict:** The project is valuable and technically credible for the AI Conclave. It should not yet be presented as production-ready or as a replacement for official portals or professionals.

---

## 2. Changes introduced by the latest collaborator commits

The local repository was five commits behind and was fast-forwarded to the current remote `main`. The new work contains approximately **1,557 additions and 268 deletions across 16 files**.

### `16e616d`: unified vector DB builder and RAG improvements

Added or changed:

- `backend/offline/build_vector_db.py`
- verified-knowledge-first routing refinements;
- cleaner RAG passage and citation rendering;
- vector-store close support;
- vector builder tests.

Positive impact:

- provides a reusable tool for recursively ingesting refined JSON and JSONL data;
- embeds all discovered civic domains into one Qdrant collection;
- improves title and markdown cleanup;
- improves primary-passage selection for RAG answers.

Main concern:

- this new builder does not reuse the canonical safety loader and therefore accepts records that the canonical loader rejects. More detail is provided in the critical issues section.

### `5c639b7`: regional-language translation layer

Added:

- `backend/modules/translator.py`;
- script-based Hindi/Gujarati detection;
- optional answer translation behind `TRANSLATION_ENABLED`;
- protected-token handling for URLs, form codes, and masked PII;
- translation tests;
- `deep-translator` dependency.

Positive impact:

- backend answers can now be translated rather than only displaying a limitation warning;
- language can be detected from the text itself;
- translated output retains source URLs and confidence metadata.

Main concern:

- translation depends on an external MyMemory service and therefore introduces network availability, latency, privacy-policy, and quality risks.

### `3023bf8`: natural-language language selection and transliteration improvements

Added:

- recognition of phrases such as “in Hindi” and “in Gujarati”;
- cleaning of language instructions before retrieval;
- more Aadhaar keyword variants;
- improved use of translated/normalized search text.

Positive impact:

- users no longer require a language dropdown;
- natural language instructions can control output language;
- routing is less likely to be confused by the language request itself.

### `aaaa37b`: civic translation glossary

Added high-precision Hindi and Gujarati translations for official terms such as:

- proof of identity;
- proof of address;
- proof of date of birth;
- PAN and Aadhaar terminology;
- bank account and KYC terminology;
- common safety messages.

Positive impact:

- reduces mistranslation of important civic terminology;
- improves consistency for common documents and warnings.

### `a7b20bf`: persistent and editable frontend conversations

Added:

- chat sessions in browser `localStorage`;
- recent-inquiry history;
- editable user prompts;
- resubmission after editing;
- restored conversations after page reload;
- extensive CSS improvements;
- removal of the language dropdown.

Positive impact:

- the frontend feels much closer to a real assistant;
- chats survive reloads;
- users can correct and resend prompts;
- the browser acceptance workflow passed without JavaScript errors.

Main concerns:

- raw user prompts are persisted before privacy masking;
- the displayed history is not genuine backend conversational memory.

---

## 3. Current architecture

### Online request flow

```text
Frontend input or file
        ↓
FastAPI /api/ask or /api/ask-file
        ↓
Pydantic validation
        ↓
Server-side PII masking
        ↓
Language intent extraction and query normalization
        ↓
Deterministic routing and verified knowledge lookup
        ↓
If verified guide matches: structured verified answer
Otherwise, if supported PAN/Aadhaar topic: hybrid RAG retrieval
Otherwise: safe refusal
        ↓
Risk and deadline warnings for document inputs
        ↓
Optional Hindi/Gujarati translation
        ↓
Structured Answer JSON with source, date, confidence, and citations
        ↓
Frontend checklist, warnings, evidence, and disclaimer
```

### Retrieval hierarchy

1. **Curated knowledge base first**
   - deterministic steps;
   - source and date;
   - medium confidence when marked verified;
   - preferred over imported RAG evidence.

2. **RAG fallback for supported PAN/Aadhaar queries**
   - BM25 lexical search;
   - multilingual vector search when enabled;
   - reciprocal-rank fusion;
   - official-source passages and citations;
   - low confidence because factual verification is unavailable.

3. **Safe refusal**
   - unsupported topics do not produce invented answers;
   - user is directed to official sources.

### Main backend components

| File | Responsibility | State |
|---|---|---|
| `backend/main.py` | FastAPI endpoints and upload boundary | Working |
| `backend/pipeline.py` | End-to-end request orchestration | Working |
| `backend/schemas.py` | Strict API and knowledge contracts | Working |
| `backend/modules/guardrails.py` | PII masking and risk flags | Working |
| `backend/modules/agent.py` | Deterministic routing | Working, still rule-based |
| `backend/modules/retrieval.py` | Curated KB retrieval | Working |
| `backend/modules/explainer.py` | Deterministic and extractive answers | Working, intentionally conservative |
| `backend/modules/translator.py` | Language detection and translation | Working when dependency/network is available |
| `backend/modules/ocr.py` | Text and text-PDF extraction | Working for supported formats |
| `backend/rag/loader.py` | Safe canonical corpus ingestion | Working |
| `backend/rag/retriever.py` | BM25 and hybrid fusion | Working |
| `backend/rag/vector_store.py` | Local Qdrant adapter | Working with local-mode limits |
| `backend/offline/build_vector_db.py` | New recursive refined-data builder | Working technically, safety alignment required |

---

## 4. Verified working behavior

### Automated tests

After installing the dependency declared in `backend/requirements.txt`:

```text
Default configuration: 91 passed
Hybrid RAG configuration: 91 passed
Python compile check: passed
JavaScript syntax check: passed
```

The hybrid test run produced one FastEmbed warning about a model pooling behavior change. It did not cause test failures, but the embedding version/model behavior should be pinned before production.

### Real API acceptance results

The backend was started with:

```text
RAG_ENABLED=true
RAG_VECTOR_ENABLED=true
TRANSLATION_ENABLED=true
```

Observed behavior:

| Workflow | Result |
|---|---|
| Health endpoint | 200, RAG ready |
| Capabilities endpoint | 200 |
| New PAN application | Verified structured guide, medium confidence |
| e-PAN download | Cited RAG evidence, low confidence |
| Hindi question | Hindi output returned |
| “in Gujarati” natural-language request | Gujarati structured answer returned |
| Loan document with PAN and phone | Sensitive values masked; warnings returned |
| Unsupported passport query | Safe “No verified guide found” response |
| Empty invalid request | Correct 422 validation error |
| Text-file upload | Parsed and explained successfully |
| Image upload | Correctly rejected with 415 because OCR is unavailable |

### Browser acceptance result

A real headless Chromium session was used against the running frontend and backend.

Verified:

- frontend loaded successfully;
- backend badge displayed Online;
- PAN request returned and rendered a structured answer;
- chat history appeared;
- the answer and history were restored after page reload;
- no page-level JavaScript error occurred.

---

## 5. Data and RAG status

### Canonical safe loader

Current production loader report:

| Metric | Result |
|---|---:|
| Records seen | 647 |
| Accepted records | 632 |
| Rejected records | 15 |
| Duplicate records | 0 |
| Unique documents | 632 |
| Aadhaar documents | 390 |
| PAN documents | 242 |
| Factual verification | Unverified |
| Corpus complete | Yes, after explicit rejections |

Rejection reasons:

- 11 unsafe source URLs;
- 4 source hosts outside the approved allowlist.

Warnings:

- all 632 records lack independent factual verification;
- 242 contain navigation or image-markdown indicators;
- 26 may contain UI or error-page text;
- 22 require review for passage length;
- reported quality scores are not independently calibrated.

### Vector index

Current runtime health reported:

- 632 indexed points;
- 632 runtime documents;
- matching corpus hash;
- multilingual MiniLM embeddings;
- hybrid mode ready.

This is internally consistent for the current running index.

### New unified builder discrepancy

The new recursive builder discovers:

```text
647 records
393 Aadhaar
254 PAN
```

This differs from the safe canonical loader, which accepts only 632 records.

The new builder currently:

- reads refined files directly;
- deduplicates by content hash;
- does not enforce the manifest host allowlist;
- does not reject unsafe source URLs in the same way as `rag/loader.py`;
- constructs documents without the canonical loader’s warnings;
- can therefore index the 15 records that the safe loader rejects.

**Required decision:** There must be one authoritative ingestion path. The unified builder should consume the canonical loader output or reproduce all of its validation and provenance rules before it is used for a production index.

---

## 6. Critical problems

### P0: raw personal information is stored in browser localStorage

The frontend stores the original user message before the backend masks it.

Observed acceptance evidence:

```text
User prompt contained phone number: 9876543210
Raw phone number found in localStorage: true
```

Why this matters:

- contradicts the privacy-by-design story;
- persists sensitive content across reloads;
- browser extensions, shared-device users, or injected scripts could access it;
- no retention limit or clear-history control is currently visible.

Required fix:

- mask sensitive values in the browser before saving history, or do not persist raw prompts;
- provide clear-chat and retention controls;
- clearly disclose local storage behavior;
- consider storing only redacted text and minimal answer metadata.

### P0: “multi-turn” history is not actual conversational intelligence

The frontend stores and displays multiple messages, and sends a `conversation_id`, but the backend does not use previous turns to resolve follow-ups.

Observed acceptance evidence:

```text
Turn 1: How do I apply for a new PAN card?
Result: Apply for a new PAN card

Turn 2: What documents do I need for that?
Result: No verified guide found
```

Required fix:

- send a small redacted conversation context window to the backend;
- or maintain server-side conversation state with explicit privacy and expiry rules;
- resolve pronouns such as “that,” “it,” and “this process” against the previous verified task;
- never allow conversation memory to bypass grounding or domain checks.

### P0/P1: factual verification is still unavailable for the imported RAG corpus

All 632 accepted RAG documents are structurally validated but not independently fact-checked.

Current safeguards are good:

- low confidence;
- citations;
- explicit unverified labels;
- confirmation prompts.

However, the application must not market these RAG responses as verified procedures.

Required fix:

- create a verification workflow for high-value procedures;
- record verification evidence, reviewer, official URL, and date;
- promote approved procedures into the curated knowledge base;
- keep unverified evidence separate from verified answers.

### P1: documentation and runtime capabilities are stale

`README.md`, `PROJECT_STATUS_REPORT.md`, and `backend/config.py` still claim:

- backend translation is not implemented;
- expected test count is 46;
- several newer RAG and frontend features are absent;
- knowledge status descriptions do not match current runtime statistics.

The live capabilities endpoint reported:

```text
English answers only. Hindi/Gujarati ... translation is not implemented yet.
```

This was false while translation was enabled and functioning.

Required fix:

- update documentation and capabilities dynamically from feature flags;
- document current test counts and setup;
- document the translation provider and privacy implications;
- distinguish feature available, feature enabled, and feature verified.

### P1: translation depends on an external unofficial service

`deep-translator` uses MyMemory for translation.

Risks:

- internet dependency;
- variable latency;
- provider rate limits;
- translation-quality variability;
- no explicit production SLA;
- civic text may be sent to a third party after masking;
- tests can depend on external availability.

Required fix:

- define a provider interface;
- add timeouts and circuit breaking;
- use mocked provider tests instead of live network tests;
- document external processing;
- consider Bhashini or a controlled/local translation provider;
- retain deterministic glossary overrides.

### P1: local Qdrant cannot support concurrent processes

Qdrant local mode locks its storage directory. A server process and a separate test/worker process cannot open the same index concurrently.

Required fix for deployment:

- run Qdrant as a service/container;
- or use managed Qdrant/pgvector;
- configure URL/API-key based access;
- keep local mode only for development.

### P1: OCR is not implemented

Text files and selectable-text PDFs work. Images and scanned PDFs are correctly rejected.

This is honest and safe, but document assistance remains incomplete because many real notices are scanned or photographed.

Required future work:

- privacy-reviewed OCR;
- rotation and image-quality checks;
- language-aware OCR;
- extraction-confidence reporting;
- strict file size/page limits;
- temporary-memory handling with no persistent uploads.

---

## 7. Additional technical weaknesses

### Frontend uses a hardcoded local backend URL

```javascript
const API_BASE = "http://127.0.0.1:8000";
```

This prevents direct production deployment without editing code.

Recommendation:

- use relative `/api` paths behind one reverse proxy;
- or inject environment/runtime configuration.

### CORS allows every origin

```python
CORS_ALLOW_ORIGINS = ["*"]
```

Acceptable for local demo only. Restrict to known deployed frontend origins before public hosting.

### No authentication, authorization, or abuse controls

The app currently has no:

- login or admin roles;
- API rate limiting;
- request quotas;
- bot protection;
- audit trail;
- security headers;
- production secrets management.

These are deployment blockers, not conclave-demo blockers.

### Conversation persistence has no retention policy

There is no automatic expiry, size limit, migration logic, or user-facing “delete all chats” control.

### Answer generation is still largely deterministic/extractive

This design is safer than uncontrolled generation, but broad RAG answers can feel like search excerpts rather than a helpful guided assistant.

Next-generation answer behavior should:

- ask targeted clarification questions;
- distinguish between procedures and document explanation;
- turn grounded evidence into an actionable checklist;
- identify the correct user situation;
- cite every material factual claim;
- refuse when evidence is insufficient;
- never generate unsupported legal or financial verdicts.

### Error observability is minimal

Generic 500 responses are safe for users, but production needs:

- structured server logs;
- request IDs;
- latency and failure metrics;
- translation/retrieval/provider health;
- privacy-safe tracing;
- alerting.

### Embedding behavior warning

FastEmbed reports that the multilingual model now uses mean pooling instead of its earlier behavior.

Recommendation:

- pin a known compatible FastEmbed/model revision;
- rebuild the index after any embedding configuration change;
- store embedding model, version, dimension, and corpus hash in index metadata;
- fail health checks if index metadata and runtime settings do not match.

---

## 8. Frontend status

### Completed

- polished responsive chat UI;
- light/dark theme;
- suggestion cards;
- backend connection badge;
- structured answer rendering;
- document checklist;
- procedure checklist;
- warning cards;
- citation cards;
- source/date/confidence display;
- file attachment flow;
- editable prompts;
- persistent chat history;
- history restoration after reload;
- HTML escaping for rendered user/server text.

### Incomplete or misleading

- persistent history stores raw prompts;
- no real conversational context;
- camera UI is absent from current markup while some controller references remain;
- frontend can fall back to mock/sample behavior, which must be clearly labeled during demonstrations;
- no language selector now exists, so users must type the language request or use native script;
- no clear-history/privacy control;
- no deployment configuration for API location;
- no end-to-end frontend test suite committed to the repository.

---

## 9. Backend status

### Completed

- strict Pydantic schemas;
- clean FastAPI endpoints;
- custom validation response;
- verified-guide-first routing;
- server-side privacy masking;
- deterministic document warnings;
- safe unsupported-domain refusal;
- real file upload processing without storing files;
- text-based PDF extraction;
- source-backed structured answers;
- hybrid RAG feature flags;
- multilingual query handling;
- optional answer translation;
- health and capability endpoints.

### Remaining

- real conversation-state handling;
- rate limiting and abuse protection;
- restricted CORS;
- deployment configuration;
- provider timeouts/retries/circuit breakers;
- robust observability;
- scanned-document OCR;
- voice input/output;
- professional escalation flow;
- automated official-source freshness checks;
- human verification administration.

---

## 10. Test status and gaps

### Current automated result

```text
91 passed in default mode
91 passed in hybrid RAG mode
```

### Covered

- request validation;
- API boundaries;
- privacy masking;
- KB retrieval;
- RAG loading;
- lexical retrieval;
- hybrid fusion;
- Qdrant persistence;
- corpus refinement;
- vector builder behavior;
- translation helpers;
- file upload behavior;
- answer contracts;
- supported and unsupported requests.

### Missing or weak coverage

- browser tests are not committed as part of CI;
- external translation tests are network-dependent;
- no load/concurrency testing;
- no security testing;
- no prompt-injection test suite;
- no factual-answer evaluation set with human-approved expected evidence;
- no OCR evaluation;
- no deployment smoke test;
- no real multi-turn context tests because context is not implemented;
- no localStorage privacy regression test;
- no index/runtime metadata compatibility test.

---

## 11. Recommended prioritized roadmap

### Phase 1: repair privacy and truth boundaries

1. Redact or stop persisting raw user prompts in localStorage.
2. Add clear-history and retention controls.
3. Make the unified vector builder consume the canonical safe loader.
4. Keep the 15 rejected records out of every index.
5. Update stale README, status report, and capabilities output.
6. Clearly mark RAG facts as unverified everywhere.

**Acceptance criteria:**

- no raw Aadhaar/PAN/phone/account values appear in browser storage;
- builder and runtime use the same accepted document IDs and corpus hash;
- documentation and live capabilities match actual enabled features.

### Phase 2: implement real guided conversation

1. Add a redacted, bounded context window.
2. Resolve follow-up references to the previous task.
3. Ask clarification questions before retrieval when necessary.
4. Keep grounding and citations on every turn.
5. Add explicit conversation expiration.

**Acceptance criteria:**

- after asking about PAN application, “What documents do I need for that?” returns the PAN document checklist;
- context cannot make an unsupported topic bypass domain refusal;
- stored context contains no raw PII.

### Phase 3: improve answer usefulness

1. Add a grounded answer-planning layer.
2. Convert relevant evidence into structured procedures only when evidence supports it.
3. Add evidence-to-claim mappings.
4. Add retrieval confidence thresholds and reranking.
5. Expand the human-approved evaluation set.

**Acceptance criteria:**

- answers are actionable rather than generic passage displays;
- every fee, date, eligibility rule, and warning maps to a citation;
- insufficient evidence produces clarification or refusal.

### Phase 4: professional data verification

1. Select the top 10–20 real procedures.
2. Verify each against live official sources.
3. Record reviewer, date, source snapshot/hash, and jurisdiction.
4. Add expiration/recheck dates.
5. Promote verified procedures into the curated KB.

**Acceptance criteria:**

- the conclave demo procedures are all manually verified;
- no expired procedure is served as current guidance;
- verification evidence is auditable.

### Phase 5: production infrastructure

1. Move Qdrant to a server or managed deployment.
2. Add environment-based API and CORS configuration.
3. Add rate limiting and security headers.
4. Add structured logging and monitoring.
5. Containerize backend, frontend, and vector service.
6. Add CI checks and deployment smoke tests.

### Phase 6: OCR and voice

Only after privacy, testing, and observability are mature:

- scanned PDF and image OCR;
- extraction quality/confidence;
- Hindi/Gujarati OCR;
- text-to-speech;
- optional voice input;
- accessible low-literacy interface.

---

## 12. Suggested team ownership

### Person A: knowledge, retrieval, and answer quality

- canonical ingestion alignment;
- verification workflow;
- retrieval evaluation;
- reranking and confidence gates;
- grounded answer planner;
- citation accuracy;
- official-source freshness.

### Person B: privacy, frontend, language, and uploads

- localStorage privacy correction;
- context UI and history controls;
- translation provider abstraction;
- frontend tests;
- OCR pipeline when approved;
- accessibility and voice;
- deployment API configuration.

### Together

- schemas and API contracts;
- conversation privacy design;
- end-to-end acceptance criteria;
- user testing;
- security review;
- demo and presentation.

---

## 13. Demo guidance

### Safe demo scenarios

- applying for a new PAN card;
- downloading e-PAN with clearly labeled RAG evidence;
- Aadhaar address-query retrieval in Hindi/Gujarati;
- uploading a fictional loan agreement text file;
- showing PII masking and deadline warnings;
- showing safe refusal for passport or other unsupported topics;
- showing citations and verification status.

### Do not claim

- that every RAG fact is verified;
- that it gives legal or financial advice;
- that it remembers conversational meaning across turns;
- that uploaded images are processed;
- that chat history is fully privacy-safe;
- that it is production-ready;
- that translation is fully local or guaranteed accurate.

### Recommended pitch wording

> GovBank Assistant is a privacy-aware, source-grounded civic guidance prototype. It prioritizes verified procedures, masks sensitive values before retrieval, cites official evidence, translates supported answers, and refuses unsupported tasks instead of guessing. The current build is designed for responsible demonstration and further verification, not unsupervised real-world decision-making.

---

## 14. Final verdict

The collaborator changes **meaningfully improved the project**. Translation, frontend persistence, editable prompts, vector tooling, and cleaner citations make the system more complete and impressive.

The project is currently:

- **strong enough for a polished AI Conclave demonstration;**
- **architecturally credible as an applied AI/RAG system;**
- **well tested at the unit and local integration level;**
- **not yet safe or mature enough for public production use.**

The next work should not be another broad feature expansion. The highest-value sequence is:

1. fix browser-storage privacy;
2. unify safe corpus ingestion and vector building;
3. implement real grounded follow-up context;
4. update documentation and capabilities;
5. verify the most important procedures;
6. then improve generative answer quality, OCR, voice, and deployment.

---

## 15. Evidence summary

| Evidence | Observed result |
|---|---|
| Git synchronization | Local `main` equals `origin/main` at `a7b20bf` before this report commit |
| Default tests | 91 passed |
| Hybrid tests | 91 passed, one embedding warning |
| Python syntax | Passed |
| JavaScript syntax | Passed |
| Browser response rendering | Passed |
| Browser reload persistence | Passed |
| Raw PII in localStorage | **Failed privacy expectation: raw phone persisted** |
| Follow-up conversational context | **Failed: follow-up returned no verified guide** |
| Text upload | Passed |
| Image OCR rejection | Passed with explicit 415 |
| PAN verified guide | Passed |
| e-PAN RAG citations | Passed |
| Hindi translation | Passed |
| Gujarati natural-language request | Passed |
| Unsupported-domain refusal | Passed |
| Canonical corpus | 632 accepted from 647; 15 safely rejected |
| Factual verification | Unavailable for all 632 RAG documents |
| New builder alignment | **Mismatch: discovers 647 rather than safe 632** |

This document should be treated as the current collaborator handoff until a later audit replaces it.
