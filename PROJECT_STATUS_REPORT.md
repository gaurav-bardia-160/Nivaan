# GovBank Assistant: Current Technical Status

**Last Updated:** October 22, 2026
**Version:** 0.5.0
**Branch:** `main`

## Executive status

GovBank Assistant is a working privacy-aware civic RAG application, not a display-only prototype. It provides verified procedures first, hybrid retrieval over official-source candidate data, structured citations, multilingual output, document analysis, real OCR when Tesseract is present, bounded redacted conversation memory, and optional local Ollama answer enhancement.

| Area | Current rating | Evidence |
|---|---:|---|
| Conclave/demo readiness | 9.3/10 | Complete UI and working typed, document, OCR, multilingual, follow-up, and cited-RAG flows |
| Backend engineering | 9.0/10 | FastAPI contracts, auth, rate limiting, metrics, safe errors, feature flags, tests |
| Retrieval/RAG | 8.8/10 | 681 allowlisted chunks, BM25 plus multilingual vectors, verified-first routing, safe fallback |
| Privacy | 8.8/10 | Client and server masking, no upload persistence, redacted TTL memory, local-only model default |
| Frontend | 8.6/10 | Responsive chat, editing, persistence, source tags, backend context and deletion integration |
| Production deployment | 7.2/10 | Strong single-host build, but shared services, monitoring, factual review, and load testing remain |

## Working capabilities

- 11 curated verified procedures, including PAN, Aadhaar, ITR, banking, consumer, legal, EPF, PM-Kisan, FIR, and passport guidance.
- Canonical allowlisted corpus of 681 candidate chunks. The local Qdrant collection is rebuilt to the same 681-document count.
- Verified knowledge is always preferred. Imported RAG evidence remains labelled unverified and cannot override verified guides.
- Retrieval refuses unrelated short, cooking, entertainment, cryptocurrency, weather, and commercial-pilot questions instead of forcing a civic match.
- Client-side and server-side masking for Aadhaar, PAN, phone, email, bank account, and IFSC patterns.
- Bounded process-local conversation memory stores only redacted questions, answer topics, and verified entry IDs. Defaults: six turns, 30-minute TTL, 500 conversations.
- Optional Ollama-compatible local generation rewrites only an already-grounded cited summary. All citations, steps, warnings, confidence, and source metadata remain deterministic.
- Exact deterministic fallback when Ollama is disabled, unreachable, times out, emits invalid JSON, or fails grounding checks.
- Text, text-based PDF, image, and scanned-PDF extraction. OCR availability is reported dynamically and depends on Tesseract.
- Hindi and Gujarati language selection, translation policy, and civic glossary.
- API-key authentication, configurable CORS, in-memory rate limiting, metrics, CI, privacy/security/terms documents, and Windows launcher scripts.

## Privacy and trust boundaries

- Uploaded files are processed in memory and are not saved by the application.
- Browser chat persistence is sanitized before writing to `localStorage`.
- Backend memory receives masked question text and never receives raw identifiers from the pipeline.
- Deleting a frontend conversation also requests deletion of backend memory for that conversation ID.
- Local-model endpoints are restricted to loopback addresses unless `LOCAL_LLM_ALLOW_REMOTE=true` is explicitly configured.
- The model cannot replace sources or raise confidence. Candidate-corpus answers remain low confidence until factual review is completed.

## Remaining production work

1. Manually or independently fact-check the highest-use RAG chunks. The 681 imported chunks currently have source provenance but not complete factual verification.
2. Move process-local memory, rate limits, and metrics to protected shared services before using multiple backend workers.
3. Move local-file Qdrant to a Qdrant server or another managed vector backend for concurrent production workers.
4. Add structured privacy-safe logs, tracing, dashboards, alerts, backup procedures, and operational runbooks.
5. Add load, soak, accessibility, cross-browser, translation-quality, OCR-quality, and adversarial prompt-injection evaluations.
6. Configure production-only CORS origins, secrets management, HTTPS termination, reverse proxy limits, and deployment health probes.
7. Expand verified procedures and keep volatile fees, deadlines, and eligibility rules under an approval workflow.

## Safe release position

The project is suitable for the AI conclave and controlled pilot demonstrations. It should still be presented as an informational guidance assistant rather than an authority for legal, tax, financial, eligibility, or filing decisions. Public production release should wait until the shared-service, factual-review, observability, and deployment requirements above are completed.
