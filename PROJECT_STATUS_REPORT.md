# GovBank Assistant: Technical Status, Audit Findings, and Roadmap

**Last Updated:** October 19, 2026  
**Audited Branch:** `main`  
**Reference Document:** `COLLABORATOR_PROJECT_AUDIT_2026-10-19.md`

---

## 1. Executive Status & Conclave Readiness

GovBank Assistant is an applied-AI prototype for explaining Indian government, tax, banking, and legal procedures in plain language with strict source citations and privacy guardrails.

### Current Overall Readiness (Collaborator Audit Oct 2026)

| Area | Rating | Status & Assessment |
|---|:---:|---|
| **Conclave / Demo Readiness** | **8.5 / 10** | **Strong & Demonstrable.** Interactive UI, verified guides, and bilingual translation. |
| **Backend Engineering** | **8.5 / 10** | Modular FastAPI architecture, strict schemas, verified-first routing, 93 passing tests. |
| **RAG Architecture** | **8.2 / 10** | Hybrid (BM25 + Qdrant multilingual vector store) over 632 canonical documents with exact SHA. |
| **Frontend Experience** | **8.0 / 10** | Multi-turn sessions in `localStorage`, editable prompts (✏️), dark/light theme, interactive checklists. |
| **Regional Language Layer** | **7.8 / 10** | Script auto-detection, natural-phrase query cleaning, high-precision civic glossary for Hindi/Gujarati. |
| **Privacy Readiness** | **7.0 / 10** | Server-side masking for 6 PII types before retrieval; client-side storage redaction in progress. |
| **Production Readiness** | **5.5 / 10** | Prototype complete (~80%); needs production auth, rate-limiting, and managed deployment. |

---

## 2. What Is Working Now

### Backend & API
- **FastAPI Endpoints:** `/api/health`, `/api/capabilities`, `/api/ask`, and `/api/ask-file`.
- **Dynamic Capabilities:** `/api/capabilities` dynamically reports active feature flags (`RAG_ENABLED`, `RAG_VECTOR_ENABLED`, `TRANSLATION_ENABLED`), exact document counts, and supported upload formats.
- **Curated Knowledge Base (10 Verified Guides):**
  - Form 49A PAN Card Application
  - Aadhaar Enrolment Basics
  - ITR-1 Sahaj Tax Filing Basics
  - Loan Prepayment & Foreclosure Rules (RBI Circular DBOD.Dir.BC.No.27/13.03.00/2014-15)
  - Cheque Bounce Legal Notice (Negotiable Instruments Act Section 138)
  - Bank Account Opening & KYC Guidelines
  - PM-Kisan Scheme Eligibility
  - Consumer Complaint Filing Process (E-Daakhil)
  - Legal Notice Response Procedure
  - EPF Withdrawal Process
- **Deterministic Agent Routing:** Automatically categorizes questions (`tax`, `banking`, `scheme`, `legal`, `general`) and maps verified procedures before any RAG fallback.
- **Server-Side Privacy Guardrails:** Masks Aadhaar, PAN, phone numbers, email addresses, bank accounts, and IFSC codes with regex replacements prior to retrieval or translation.
- **Document Risk Flags:** Rule-based detection of deadlines, penalties, interest clauses, auto-renewal, and forfeiture in uploaded texts.
- **Safe Document Uploads:** Text files and text-based PDFs processed in memory without disk retention; scanned PDFs/images rejected with 415.

### Hybrid RAG Pipeline
- **Canonical Safe Ingestion (`rag/loader.py`):** Ingests 632 safe chunks, rejecting 15 unsafe URLs / non-allowlisted records. Verified SHA: `91e49a1aae05`.
- **Hybrid Fusion Retriever:** BM25 lexical search combined with dense multilingual embeddings (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) via Reciprocal Rank Fusion.
- **Unified Vector Database (`backend/offline/build_vector_db.py`):** Ingests canonical safe loader documents into a unified local Qdrant collection (`govbank_chunks`, exactly 632 points).
- **Explicit Provenance & Caveats:** All RAG evidence passages include official URLs, last-verified dates, and explicit `UNVERIFIED` badges.

### Regional Language Translation Layer
- **Automatic Language Detection:** Detects Devanagari (Hindi) and Gujarati Unicode blocks, as well as natural phrases (`"in hindi"`, `"in gujarati"`, `"hindi me"`).
- **Query Cleaning:** Strips language-intent tokens before retrieval to prevent query dilution.
- **High-Precision Civic Glossary:** Hardened mapping for sensitive government terms (Proof of Identity, Proof of Address, Proof of Date of Birth, Free of Cost) guaranteeing 100% accuracy.
- **Feature Flag Control:** `TRANSLATION_ENABLED=true` enables live translation; defaults to honest English explanation with informative limitation warning if disabled.

### Frontend
- **Editable User Prompts:** Users can edit previously sent queries directly in the chat with inline Save/Submit and Cancel.
- **Persistent Chat History:** Conversations and checklists survive page reloads via `localStorage`.
- **Session Continuity:** Successive queries append to the active chat session instead of fragmenting into new sidebar entries.

---

## 3. Test Coverage

```text
Platform: Python 3.12, pytest 9.1
Result: 93 passed in 12.5s (unit, API, RAG loader, vector builder, translation)
```

Covered areas:
- Request validation and custom 422 handlers
- API health and capabilities honesty checks
- Server-side PII masking and document risk flags
- Verified KB retrieval and scoring
- RAG manifest loading and 15-record safety rejection
- BM25 and multilingual vector hybrid retrieval
- Qdrant store rebuild, health, and close
- Unified vector database generator with canonical loader alignment
- Language detection, query cleaning, and civic glossary translation

---

## 4. Current Limitations & Action Plan

### Priority 1: Browser Storage Privacy (P0)
- **Current State:** The backend masks PII before processing, but the frontend writes user messages to `localStorage` before the backend response is received.
- **Action:** Redact sensitive patterns client-side prior to writing to `localStorage` or store only sanitized server responses.

### Priority 2: Follow-Up Conversational Context (P0)
- **Current State:** Backend evaluates each request independently. Follow-up pronouns (*"What documents do I need for that?"*) return *No verified guide found*.
- **Action:** Pass `previous_topic` or `previous_entry_id` in API payload to resolve anaphoric pronouns.

### Priority 3: Production Hardening (P2)
- Restrict `CORS_ALLOW_ORIGINS` to trusted domains.
- Transition from local-file Qdrant to containerized Qdrant service.
- Add rate limiting and structured server logging.

---

## 5. Safe Demo Guidelines

### Strongest Demo Scenarios:
1. **New PAN Application:** Type *"How do I apply for a new PAN card online?"* $\rightarrow$ Demonstrates verified procedure, required documents checklist, and official Protean/UTIITSL link.
2. **Bilingual Aadhaar Inquiry:** Type *"apply for aadhar card in hindi"* $\rightarrow$ Demonstrates language intent extraction, transliteration normalization, verified guide routing, and Hindi translation with accurate civic terms.
3. **e-PAN Download:** Type *"How can I download e-PAN?"* $\rightarrow$ Demonstrates hybrid RAG retrieval, citations, and explicit `UNVERIFIED` candidate warning.
4. **Loan Agreement Risk Check:** Paste or upload a loan agreement with personal identifiers $\rightarrow$ Demonstrates server-side PII masking, prepayment penalty ban warnings (RBI Circular), and 30-day deadline alerts.
5. **Prompt Editing & Persistence:** Edit a sent prompt using ✏️, reload the page $\rightarrow$ Demonstrates chat session restoration and seamless prompt resubmission.
