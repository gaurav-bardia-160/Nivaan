# GovBank Assistant

GovBank Assistant is a grounded, privacy-aware RAG (Retrieval-Augmented Generation) assistant that helps citizens understand Indian government, banking, tax, and legal procedures in plain language. Designed for the IBCP AI Conclave 2026, it addresses the communication gap between official institutions and citizens by prioritizing verified procedures, masking personal identifiers before retrieval, citing official sources, translating answers into regional languages (Hindi & Gujarati), and refusing to invent facts on unsupported queries.

---

## Current Architecture & Capabilities

### 1. Hybrid Grounded Retrieval (Verified-First + RAG Fallback)
- **Verified Knowledge Base:** 11 deterministic, human-checked procedure guides (e.g. Passport Seva fresh/re-issue application, Form 49A PAN application, Aadhaar enrolment, ITR filing basics, EPF withdrawal, loan prepayment, FIR filing) are checked first and take absolute precedence over candidate passages.
- **Hybrid RAG Fallback:** Lexical search (BM25) combined with dense multilingual vector search (FastEmbed `paraphrase-multilingual-MiniLM-L12-v2` + local Qdrant) via Reciprocal Rank Fusion (RRF).
- **Strict Ingestion Allowlist:** Ingests exactly 681 safe canonical chunks across PAN, Aadhaar, and civic portals while rejecting non-allowlisted and malformed sources.
- **Explicit Provenance:** Every response includes official source URLs, reporting dates, verification labels (`VERIFIED` vs `UNVERIFIED`), and step-by-step checklists.

### 2. Privacy-by-Design Guardrails
- **Server-Side Masking:** Redacts Aadhaar numbers, PAN cards, phone numbers, email addresses, bank accounts, and IFSC codes before retrieval and model processing.
- **Document Risk Flags:** Rule-based detection of deadlines, penalties, interest clauses, and forfeiture terms in uploaded agreements or notices.
- **Redacted Backend Memory:** Bounded TTL/LRU memory retains only masked questions, answer topics, and verified entry IDs for follow-up resolution.
- **Optional Local AI:** An Ollama-compatible model can rewrite already-grounded RAG summaries locally. Citations, warnings, confidence, and deterministic fallback remain code-controlled.

### 3. Regional Language Support (Hindi & Gujarati)
- **Automatic Language Detection:** Recognizes native Indic scripts (Devanagari for Hindi, Gujarati script) and natural language instructions (e.g., *"in hindi"*, *"in gujarati"*, *"hindi me"*).
- **Clean Query Search:** Strips language-intent phrases before retrieval to prevent search index dilution.
- **Translation Layer & Civic Glossary:** Feature-flagged translation (`TRANSLATION_ENABLED=true`) with high-precision domain glossary for critical civic terms (PoI, PoA, PoB, Free of cost) preserving URLs, form codes, and PII masks.

### 4. Interactive Frontend
- **Editable User Prompts:** Users can edit previously sent messages with inline Save/Submit and Cancel.
- **Persistent Multi-Turn Sessions:** Conversations and active session history persist across page reloads via `localStorage` with client-side PII masking.
- **Clean Structured Responses (No Checkboxes):** Formats required documents with clean bullet points and step-by-step procedures with numbered badges, bold titles, and contextual details—eliminating messy checkboxes.
- **Tagged Official Source Links:** Displays verified primary portals and RAG citations as numbered pill tags (`[1]`, `[2]`, ...) with domain badges, external link arrows (`↗`), and an optional expandable drawer for RAG evidence excerpts.

---

## Current Limitations

- **OCR Host Dependency:** Images and scanned PDFs work when Tesseract-OCR is installed. The API reports OCR availability and rejects unsupported hosts honestly.
- **Process-Local Memory:** Follow-up memory is intentionally non-persistent and should be moved to a protected shared TTL store only for multi-worker deployments.
- **Educational Prototype:** Sourced plain-language guidance helper; not a substitute for official portal submissions or legal/financial advice.

---

## Running Locally

### One-Click Launch Scripts

| Platform | Backend Only | Full-Stack (Backend + Frontend + Browser) |
| :--- | :--- | :--- |
| **Windows** | Double-click `run_backend.bat` or run `.\run_backend.ps1` | Double-click `start.bat` or run `.\start.ps1` |
| **macOS / Linux** | `./run_backend.sh` | `./start.sh` |

---

### Manual Launch

#### 1. Backend Server

```bash
# Install dependencies
python -m pip install -r requirements.txt

# Start backend with full feature set (RAG + Vectors + Translation)
# On Windows PowerShell:
$env:RAG_ENABLED="true"; $env:RAG_VECTOR_ENABLED="true"; $env:TRANSLATION_ENABLED="true"; python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# On Linux/macOS:
RAG_ENABLED=true RAG_VECTOR_ENABLED=true TRANSLATION_ENABLED=true python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Optional local Ollama answer enhancement

```bash
# Start Ollama and use any installed local chat model.
ollama serve
ollama pull qwen3.5:4b

LOCAL_LLM_ENABLED=true LOCAL_LLM_MODEL=qwen3.5:4b \
RAG_ENABLED=true RAG_VECTOR_ENABLED=true \
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The local model never replaces retrieval. It only rewrites a cited extractive summary, runs on a loopback URL by default, and falls back to the deterministic answer on timeout, invalid JSON, weak grounding, or server failure.

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
*Note: Uses `backend/data/rag_manifest.json` by default to ensure only the 681 safe canonical records are indexed.*

---

## Testing

Run the full automated test suite (unit tests, API contracts, RAG loader, vector builder, translation layer):

```bash
python -m pytest
```

Also run `python tests/eval_retrieval.py` to verify retrieval, refusal, privacy, context, and latency behavior.

---

## Project Structure

```text
govbank-assistant/
├── run_backend.bat                 # Windows one-click backend runner (CMD/Explorer)
├── run_backend.ps1                 # Windows PowerShell backend runner
├── run_backend.sh                  # macOS / Linux backend runner
├── start.bat                       # Windows one-click full-stack launcher (Backend + Frontend + Browser)
├── start.ps1                       # Windows PowerShell full-stack launcher
├── start.sh                        # macOS / Linux full-stack launcher
├── requirements.txt                # Unified project dependencies
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
│   │   ├── llm.py                  # Optional local Ollama grounded summary enhancement
│   │   ├── memory.py               # Bounded redacted conversation context
│   │   ├── translator.py           # Language extraction, script detection, civic glossary
│   │   ├── translate_voice.py      # Language policy handler
│   │   └── ocr.py                  # Text, PDF, scanned PDF, and image OCR boundary
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
├── tests/                          # Automated unit, integration, safety, and retrieval evaluation tests
├── COLLABORATOR_PROJECT_AUDIT_2026-10-19.md # Detailed collaborator technical audit report
└── PROJECT_STATUS_REPORT.md        # Phased development status and technical roadmap
```
