# GovBank Assistant

GovBank Assistant is a grounded, privacy-aware RAG (Retrieval-Augmented Generation) assistant that helps citizens understand Indian government, banking, tax, and legal procedures in plain language. Designed for the IBCP AI Conclave 2026, it addresses the communication gap between official institutions and citizens by prioritizing verified procedures, masking personal identifiers before retrieval, citing official sources, translating answers into regional languages (Hindi & Gujarati), and refusing to invent facts on unsupported queries.

---

## Current Architecture & Capabilities

### 1. Hybrid Grounded Retrieval (Verified-First + RAG Fallback)
- **Verified Knowledge Base:** Deterministic, human-checked procedure guides (e.g. Form 49A PAN application, Aadhaar enrolment, ITR filing, loan prepayment) are checked first and take absolute precedence over candidate passages.
- **Hybrid RAG Fallback:** Lexical search (BM25) combined with dense multilingual vector search (FastEmbed `paraphrase-multilingual-MiniLM-L12-v2` + local Qdrant) via Reciprocal Rank Fusion (RRF).
- **Strict Ingestion Allowlist:** Ingests exactly 632 safe canonical chunks from official portals (`incometax.gov.in`, `uidai.gov.in`, `tinpan.proteantech.in`), safely rejecting non-allowlisted and malformed sources.
- **Explicit Provenance:** Every response includes official source URLs, reporting dates, verification labels (`VERIFIED` vs `UNVERIFIED`), and step-by-step checklists.

### 2. Privacy-by-Design Guardrails
- **Server-Side Masking:** Redacts Aadhaar numbers, PAN cards, phone numbers, email addresses, bank accounts, and IFSC codes before retrieval and model processing.
- **Document Risk Flags:** Rule-based detection of deadlines, penalties, interest clauses, and forfeiture terms in uploaded agreements or notices.

### 3. Regional Language Support (Hindi & Gujarati)
- **Automatic Language Detection:** Recognizes native Indic scripts (Devanagari for Hindi, Gujarati script) and natural language instructions (e.g., *"in hindi"*, *"in gujarati"*, *"hindi me"*).
- **Clean Query Search:** Strips language-intent phrases before retrieval to prevent search index dilution.
- **Translation Layer & Civic Glossary:** Feature-flagged translation (`TRANSLATION_ENABLED=true`) with high-precision domain glossary for critical civic terms (PoI, PoA, PoB, Free of cost) preserving URLs, form codes, and PII masks.

### 4. Interactive Frontend
- **Editable User Prompts:** Users can edit previously sent messages with inline Save/Submit and Cancel.
- **Persistent Multi-Turn Sessions:** Conversations, checklists, and active session history persist across page reloads via `localStorage`.
- **Document & Checklist Actions:** Interactive checkboxes for required documents and procedure steps.

---

## Current Limitations

- **Scanned PDF/Image OCR:** Text-based PDFs and `.txt` uploads are fully supported; scanned PDFs and images are rejected with clear 415 errors until OCR is integrated.
- **Stateless Turn Context:** Turns are stored in the client session, but follow-up pronoun queries (e.g., *"What documents do I need for that?"*) currently require mentioning the subject.
- **Educational Prototype:** Sourced plain-language guidance helper; not a substitute for official portal submissions or legal/financial advice.

---

## Running Locally

### 1. Backend Server

```bash
# Install dependencies
python -m pip install -r backend/requirements.txt

# Start backend with full feature set (RAG + Vectors + Translation)
# On Windows PowerShell:
$env:RAG_ENABLED="true"; $env:RAG_VECTOR_ENABLED="true"; $env:TRANSLATION_ENABLED="true"; python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# On Linux/macOS:
RAG_ENABLED=true RAG_VECTOR_ENABLED=true TRANSLATION_ENABLED=true python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 2. Frontend Interface

Open `frontend/index.html` directly in any modern browser, or serve it via python:

```bash
python -m http.server 5500 --directory frontend
```
Navigate to `http://127.0.0.1:5500/`.

---

## Offline Vector Database Building

To rebuild the unified Qdrant vector index from the canonical safe corpus:

```bash
python -m backend.offline.build_vector_db
```
*Note: Uses `backend/data/rag_manifest.json` by default to ensure only the 632 safe canonical records are indexed.*

---

## Testing

Run the full automated test suite (unit tests, API contracts, RAG loader, vector builder, translation layer):

```bash
python -m pytest
```

Expected result:
```text
======================= 93 passed =======================
```

---

## Project Structure

```text
govbank-assistant/
├── backend/
│   ├── main.py                     # FastAPI application endpoints (/api/health, /api/capabilities, /api/ask, /api/ask-file)
│   ├── pipeline.py                 # Core request pipeline (masking -> routing -> verified KB / RAG -> translation)
│   ├── schemas.py                  # Pydantic data schemas and contracts
│   ├── config.py                   # App configuration and dynamic capabilities
│   ├── data/
│   │   ├── knowledge_base.json     # Curated verified procedure guides
│   │   ├── rag_manifest.json       # Ingestion manifest with source allowlists
│   │   ├── refined/                # Pre-processed official civic text chunks
│   │   └── vector_index/qdrant/    # Unified local Qdrant vector collection
│   ├── modules/
│   │   ├── agent.py                # Deterministic intent routing
│   │   ├── guardrails.py           # Regex PII masking and document risk flagging
│   │   ├── retrieval.py            # Verified KB lookup and scoring
│   │   ├── explainer.py            # Structured answer generation
│   │   ├── translator.py           # Language extraction, script detection, civic glossary
│   │   ├── translate_voice.py      # Language policy handler
│   │   └── ocr.py                  # Text and PDF extraction boundary
│   ├── offline/
│   │   ├── build_vector_db.py      # Unified vector DB generator using canonical safe loader
│   │   └── data_builder.py         # Data chunking and draft builder
│   └── rag/
│       ├── embeddings.py           # FastEmbed multilingual dense embeddings
│       ├── loader.py               # Canonical safe corpus ingestion with host allowlist
│       ├── models.py               # RAG document models and dataclasses
│       ├── normalizer.py           # Provenance validation and URL safety checks
│       ├── retriever.py            # BM25 + Vector hybrid retriever with RRF
│       ├── runtime.py              # Feature-flagged runtime access to RAG
│       └── vector_store.py         # Local Qdrant vector store adapter
├── frontend/
│   ├── index.html                  # Responsive chat interface
│   ├── app.js                      # Chat controller, prompt editing, and localStorage persistence
│   └── style.css                   # Custom styles, responsive layout, dark/light theme
├── tests/                          # 93 automated pytest unit and integration tests
├── COLLABORATOR_PROJECT_AUDIT_2026-10-19.md # Detailed collaborator technical audit report
└── PROJECT_STATUS_REPORT.md        # Phased development status and technical roadmap
```
