# GovBank Assistant: Professional Flexible RAG Implementation Plan

Date: 2026-10-13
Revision: 2026-10-14. Section 18 supersedes conflicting earlier examples.
Repo: govbank-assistant
Purpose: give any future AI agent or developer the complete context and step-by-step plan to add a production-style RAG layer without breaking the existing project.

---

## 1. Project context

GovBank Assistant is an AI assistant for explaining government, legal, banking, tax, PAN, and Aadhaar related processes in simple language. The event theme is communication. The project bridges the communication gap between official institutions and citizens by turning complex forms, notices, schemes, bank terms, and official procedures into clear step-by-step guidance.

Current working backend already has:

- FastAPI app in `backend/main.py`
- request/answer schemas in `backend/schemas.py`
- orchestration in `backend/pipeline.py`
- privacy masking, OCR/text extraction, routing, retrieval, flagging, explanation modules in `backend/modules/`
- static frontend in `frontend/`
- verified procedural guide fallback in `backend/data/knowledge_base.json`
- refined data chunks for UIDAI and PAN under `backend/data/refined/` and `backend/data/processed/`

Current verified status from latest scan:

- Latest GitHub HEAD checked: `150baa6`
- Tests passed: 52/52
- API health and capabilities work
- `/api/ask` works with correct payload: `{ "question": "...", "language": "en" }`
- `/api/ask-file` works technically, but document routing can still choose the wrong guide for legal/bank notices
- Current main backend answers still mostly use `knowledge_base.json`, not the full refined PAN/UIDAI chunk datasets

Current RAG problem:

The project has strong refined data, but it is not fully powering the assistant yet. The next goal is to add a flexible RAG layer that can search the refined chunks and generate grounded answers with citations.

---

## 2. Existing data to use

Important data files already exist or have been evaluated:

### Existing fallback KB

`backend/data/knowledge_base.json`

Current role:

- Small curated procedural fallback
- About 10 verified entries
- Used by current `backend/modules/retrieval.py`
- Should not be deleted

Keep this as fallback when RAG has weak results.

### Refined chunk data

Expected current/future files:

- `backend/data/refined/pan/pan_chunks_clean.jsonl`
- `backend/data/refined/uidai/uidai_chunks_clean.jsonl` if present
- `backend/data/processed/uidai_chunks.jsonl`
- individual JSON chunks under `backend/data/refined/pan/*.json`
- individual JSON chunks under `backend/data/refined/uidai/*.json`

Good chunk schema from current data:

```json
{
  "id": "spider_uidai.gov.in_01178475_chunk_1",
  "source_url": "https://uidai.gov.in/...",
  "title": "Aadhaar Online Services",
  "section": "Download Aadhaar",
  "text": "clean useful chunk text here",
  "category": "aadhaar",
  "last_verified": "2026-10-13",
  "status": "verified",
  "quality_score": 0.95,
  "source_confidence": "official",
  "verification_method": "automated_official_source",
  "retrieval_tags": ["aadhaar", "download", "online_service"]
}
```

Earlier dataset ratings were subjective inspection scores, not measured accuracy or production approval. Canonical files contain 291 PAN records and 705 UIDAI records (996 total). Individual JSON exports repeat the JSONL records and must not also be ingested. Whole-record hashes hide repeated text when IDs and URLs differ.

The current refiner unconditionally assigns `status: verified`, `quality_score: 0.95`, and the processing date as `last_verified`. These are producer assertions, not evidence of factual verification. Preserve reported metadata, but normalize factual verification to `unverified` unless independently supported. Do not present this corpus as human-verified or fact-verified.

---

## 3. Target architecture

Do not rewrite the whole app. Add RAG as a new backend layer.

Current flow:

```text
main.py
  -> pipeline.py
      -> privacy / agent-router
      -> modules.retrieval using knowledge_base.json
      -> explainer
      -> answer
```

Target flow:

```text
main.py
  -> pipeline.py
      -> privacy mask
      -> agent/router detects category and task
      -> rag.retriever hybrid search
          -> metadata filter
          -> BM25 keyword search
          -> vector search
          -> reranker
          -> source/citation validator
      -> grounded RAG explainer
      -> answer with citations/source URLs
      -> fallback to knowledge_base.json if RAG confidence is weak
```

The RAG layer should be modular so the vector database can be changed later.

---

## 4. New folder structure to add

Add a new folder:

```text
backend/rag/
  __init__.py
  models.py              # RAG document/result dataclasses or Pydantic models
  loader.py              # loads JSONL/JSON chunks from data/refined and data/processed
  normalizer.py          # validates/cleans chunk records before indexing
  embeddings.py          # embedding provider abstraction
  vector_store.py        # common interface + local implementation
  bm25.py                # keyword/BM25 retrieval
  reranker.py            # rerank results, initially lightweight heuristic
  retriever.py           # hybrid retrieval orchestration
  citation.py            # citation validation and source formatting
  index_builder.py       # CLI/script to rebuild index
  config.py              # RAG settings, paths, thresholds
```

Optional later:

```text
backend/rag/providers/
  chroma_store.py
  qdrant_store.py
  faiss_store.py
  openai_embeddings.py
  sentence_transformer_embeddings.py
```

Tests to add:

```text
tests/test_rag_loader.py
tests/test_rag_retriever.py
tests/test_rag_pipeline.py
tests/test_rag_quality.py
```

Generated index/cache folder:

```text
backend/data/vector_index/
```

This folder can be ignored if it is large or reproducible. If using a small demo local index, it may be committed only if acceptable.

---

## 5. Database strategy

### Phase 1: local demo vector store

Use a local no-server option first.

Recommended choices:

1. ChromaDB local persistent mode
2. FAISS local index
3. fallback pure Python cosine search for tests if dependencies are unavailable

For this project, choose **ChromaDB first** if dependency installation is fine. Choose **FAISS or in-memory sklearn/numpy** if Chroma creates setup problems.

### Phase 2: production-ready adapter

Design `vector_store.py` so future providers can be swapped.

Common interface:

```python
class VectorStore:
    def rebuild(self, documents: list[RagDocument]) -> None: ...
    def add_documents(self, documents: list[RagDocument]) -> None: ...
    def search(self, query_embedding: list[float], filters: dict, top_k: int) -> list[RagResult]: ...
    def health(self) -> dict: ...
```

Later provider options:

- Qdrant: best serious open-source vector DB for this project
- Pinecone: managed cloud option
- Weaviate: good hybrid support
- Supabase pgvector: useful if project already uses Postgres
- Elasticsearch/OpenSearch: best when keyword search is equally important

Final recommendation for serious production: **Qdrant + BM25 + reranker**.

---

## 6. Retrieval strategy

Do not use only vector search. Use hybrid retrieval.

### Step A: Query understanding

Use current router/agent first:

- input type: question/document
- category: pan, aadhaar, tax, banking, legal, scheme, general
- user intent: explain procedure, documents needed, fee, deadline, warning, compare, status/help
- language: en/hi/gu

For now, use rules and keywords. Later, add an LLM classifier if needed.

### Step B: Metadata filtering

Before search, filter candidate chunks by metadata:

- `category`
- `source_confidence == official`
- `quality_score >= 0.75`
- `status in ["verified", "automated_verified"]`
- optional domain whitelist

For example:

- PAN questions should prefer category `pan`
- Aadhaar questions should prefer category `aadhaar`
- tax/PAN linking can include both `pan` and `tax`

### Step C: BM25 keyword search

Use BM25 because government queries contain exact terms:

- PAN
- Form 49A
- e-PAN
- Aadhaar
- VID
- PVC
- KYC
- Form 26AS
- ITR
- deadline
- fee

BM25 catches exact official terms better than embeddings alone.

Possible library:

- `rank-bm25`
- or a simple built-in TF-IDF/BM25 implementation if avoiding dependencies

### Step D: Vector search

Use embeddings for meaning-based matches.

Embedding options:

- local: `sentence-transformers/all-MiniLM-L6-v2` or similar
- API: OpenAI/Gemini embeddings if keys are available
- fallback: deterministic hash/mock embeddings only for tests, not production

### Step E: Merge results

Use rank fusion (RRF) as the initial hybrid baseline rather than adding incomparable raw BM25 and cosine scores. Evaluate dense-only, lexical-only, and hybrid against held-out passage labels. Fusion constants and metadata boosts are tunable configuration, not accuracy guarantees. Metadata dates and producer quality scores are not evidence of factual accuracy.

### Step F: Rerank

First version can be heuristic. Later can use a cross-encoder reranker.

Reranker should consider:

- query term overlap
- title/section relevance
- category match
- source quality
- chunk length
- whether chunk is procedure-like
- whether chunk contains answer type requested, e.g. fee/documents/steps

Target: retrieve top 20, rerank to top 5 to 8.

### Step G: Confidence gate

If best chunks are weak, do not let LLM guess.

Rules:

- If no result over threshold, return safe not-found answer
- If only noisy chunks, fallback to `knowledge_base.json`
- If fallback also weak, say not enough verified data

Calibrate abstention on held-out answerable, unanswerable, and conflicting-source cases. Previously suggested 0.55/0.72 thresholds are unvalidated, not correctness probabilities. One sufficient source can support an answer; duplicate chunks are not independent sources. Fallback guides must pass their own relevance and freshness checks.

---

## 7. Answer generation rules

The LLM should receive:

- masked user question/document text
- top retrieved chunks only
- source metadata for each chunk
- strict instructions

Prompt rules:

1. Answer only using the retrieved chunks.
2. If chunks do not contain the answer, say so.
3. Do not invent fees, deadlines, documents, legal conclusions, or government rules.
4. Show citations/source URLs in the answer metadata.
5. Use simple language.
6. For high-stakes legal/tax/banking matters, explain and flag, but do not tell user what final decision to make.
7. Add disclaimer.

Answer should remain compatible with current `Answer` schema, but ideally add citations later.

Current `Answer` has one `source_url`. For RAG, better future schema:

```python
class Citation(BaseModel):
    title: str
    section: str | None
    source_url: HttpUrl
    chunk_id: str
    last_verified: date

class Answer(BaseModel):
    ...existing fields...
    citations: list[Citation] = []
    retrieval_confidence: Literal["low", "medium", "high"] = "medium"
```

If changing schema breaks frontend/tests, first keep `source_url` as the top source and add citations later.

---

## 8. How this fits current project without major architecture break

Minimal integration changes:

1. Add `backend/rag/` package.
2. Add requirements for chosen local vector/BM25 libraries.
3. Add index builder script.
4. Modify `backend/pipeline.py` to call RAG retriever before old retrieval.
5. Keep old `backend/modules/retrieval.py` as fallback.
6. Keep `knowledge_base.json` as curated fallback.
7. Keep frontend mostly unchanged.

Do not remove existing code until RAG tests pass.

Suggested pipeline logic:

```python
def run(request: AskRequest) -> Answer:
    masked = privacy.mask(...)
    route = agent.route(...)

    rag_result = rag_retriever.retrieve(
        query=masked.query_text,
        category=route.category,
        top_k=8,
    )

    if rag_result.confidence in ["high", "medium"]:
        return rag_explainer.answer_from_chunks(request, rag_result)

    fallback_entry = retrieval.find_entry(...)
    if fallback_entry:
        return explain_entry(...)

    return not_found_answer(...)
```

---

## 9. Implementation phases

### Phase 0: no-risk preparation

Goal: add files without changing active behavior.

Tasks:

- Create `backend/rag/` folder
- Create models and loader
- Load PAN/UIDAI JSONL chunks
- Validate schema
- Add tests for loader

Acceptance:

- `pytest` still passes
- loader reports chunk counts
- invalid/missing fields are caught

### Phase 1: local retrieval without LLM change

Goal: make search work in terminal/tests.

Tasks:

- Add BM25 index
- Add embeddings interface
- Add simple vector store, local/in-memory first
- Add hybrid retriever
- Add test questions

Example test questions:

- How to apply for PAN card?
- What documents are needed for PAN?
- How to download e-PAN?
- How to link PAN with Aadhaar?
- How to update mobile number in Aadhaar?
- What is Aadhaar lock/unlock?
- How to download Aadhaar?

Acceptance:

- correct category result appears in top 3 for at least 85 percent of test queries
- exact PAN/Aadhaar queries retrieve relevant official chunks
- no invalid JSON

### Phase 2: integrate RAG into pipeline behind feature flag

Goal: use RAG only when enabled.

Add config:

```python
RAG_ENABLED = False  # enable only after integration and evaluation gates
RAG_PROVIDER = "local"
RAG_TOP_K = 8
RAG_MIN_CONFIDENCE = 0.55
```

Tasks:

- call retriever from pipeline
- if RAG weak, fallback to old KB
- preserve response schema

Acceptance:

- old tests still pass
- `/api/ask` returns answers for PAN/Aadhaar questions
- no source-less answer

### Phase 3: grounded answer/citations

Goal: answers cite chunks and do not hallucinate.

Tasks:

- add citation builder
- include retrieved chunk sources in answer
- update explainer prompt to answer only from chunks
- add citation checker

Acceptance:

- every RAG answer has source URL
- answer content overlaps retrieved chunk facts
- weak retrieval gives not-found/fallback answer

### Phase 4: document upload routing fix

Goal: fix known blocker where legal/bank notice can route to wrong guide.

Tasks:

- improve route category detection for documents
- detect legal notice, banking notice, deadline, penalty, loan, KYC
- retrieve chunks by document type and flags
- if the document is legal/bank but no good chunks exist, do not choose random savings account guide

Acceptance:

- fake legal notice does not return PAN/savings account unless actually relevant
- deadline and penalty warnings appear
- source confidence is shown honestly

### Phase 5: production vector DB adapter

Goal: prepare Qdrant or similar without forcing local setup.

Tasks:

- add `QdrantVectorStore` adapter
- keep local store as default
- add `.env.example` fields
- add health check for vector DB

Acceptance:

- local mode works without Qdrant
- Qdrant mode works when env is configured
- no code outside `backend/rag/` needs to know the provider

---

## 10. Accuracy evaluation plan

Create:

```text
tests/fixtures/rag_eval_questions.json
```

Example format:

```json
[
  {
    "question": "How do I download e-PAN?",
    "expected_category": "pan",
    "must_include_terms": ["e-PAN", "PAN"],
    "expected_source_domains": ["proteantech.in", "utiitsl.com", "incometax.gov.in"]
  }
]
```

Metrics:

- Recall@3: correct source/category appears in top 3
- Recall@5: correct source/category appears in top 5
- Citation coverage: answer has at least one valid source URL
- Groundedness: answer uses only retrieved source facts
- Fallback correctness: weak/out-of-scope query refuses or uses fallback

Do not award production readiness from these targets alone. Evaluate passage-level Recall@k (relevant passages retrieved / all labeled relevant passages), Hit@k, MRR, supported-claim rate, abstention errors, latency, and each language. Category/domain matching alone is not Recall@k. Keep development and held-out sets separate.

- 90 percent Recall@5 on PAN/Aadhaar eval set
- 80 percent Recall@3
- 100 percent answers have source URL
- 0 invalid JSON chunks
- no random wrong guide for legal/bank uploaded notice

---

## 11. Safety and privacy rules

Do not weaken current privacy design.

Rules:

1. Mask PII before RAG search if user uploads/pastes personal document text.
2. Do not store user uploaded documents in vector DB.
3. Do not add user inputs to dataset automatically.
4. Only index official source chunks from controlled data folders.
5. Keep disclaimer in every answer.
6. For legal/tax/banking high-stakes cases, explain and flag, do not give final verdict.
7. If sources are insufficient, say so.

---

## 12. Config additions

Add to `backend/config.py` or `backend/rag/config.py`:

```python
RAG_ENABLED = False  # enable only after integration and evaluation gates
RAG_DATA_PATHS = [
    DATA_DIR / "refined" / "pan" / "pan_chunks_clean.jsonl",
    DATA_DIR / "refined" / "uidai" / "uidai_chunks_clean.jsonl",
    # Exclude legacy processed exports and individual JSON mirrors.
]
RAG_VECTOR_PROVIDER = "local"
RAG_EMBEDDING_PROVIDER = "sentence_transformers"
RAG_TOP_K_VECTOR = 20
RAG_TOP_K_BM25 = 20
RAG_TOP_K_FINAL = 8
RAG_MIN_SCORE = 0.55
RAG_MIN_QUALITY_SCORE = 0.75
RAG_ALLOWED_STATUSES = ["verified", "automated_verified"]
```

Important: current repo has some older `unverified` chunks in `backend/data/processed/uidai_chunks.jsonl`. The loader should prefer clean verified data when available and avoid indexing low-quality old chunks by default.

---

## 13. Dependencies

Minimal local setup:

```text
rank-bm25
numpy
```

Embedding options:

Option A, local:

```text
sentence-transformers
```

Option B, API:

```text
openai
```

Vector DB options:

Option A:

```text
chromadb
```

Option B:

```text
qdrant-client
```

Recommendation for first implementation:

- start with `rank-bm25 + sentence-transformers + local persisted vectors`
- if dependency becomes heavy, use BM25 + simple cached embeddings later
- do not block core tests on external API keys

---

## 14. Important blockers to fix later

1. Backend still reports `knowledge_entries: 10`, because refined RAG chunks are not integrated into `/api/health` yet.
2. Current answers still mainly use `knowledge_base.json`.
3. Uploaded legal/bank notice can route to the wrong guide.
4. Translation/voice is not fully implemented in backend answers.
5. Refined data is official-source automated verified, not human verified.
6. Some old processed chunks are unverified and noisy, so loader must filter them.

---

## 15. Acceptance checklist for the agent

Before saying RAG is complete, verify:

- [ ] `pytest` passes
- [ ] RAG loader loads PAN and UIDAI chunks
- [ ] invalid chunks are skipped with reason
- [ ] index build command works
- [ ] `/api/health` or `/api/capabilities` reports RAG status
- [ ] `/api/ask` for PAN uses PAN chunk sources
- [ ] `/api/ask` for Aadhaar uses UIDAI chunk sources
- [ ] out-of-scope question does not hallucinate
- [ ] uploaded fake bank/legal notice does not return unrelated savings account/PAN guide
- [ ] every answer has source URL
- [ ] fallback to `knowledge_base.json` works
- [ ] no user document is stored

---

## 16. Suggested build order for next agent

1. Read this file fully.
2. Run current tests: `python3 -m pytest -q`.
3. Add `backend/rag/models.py` and `loader.py`.
4. Add loader tests.
5. Add BM25 retrieval.
6. Add local vector/embedding interface.
7. Add hybrid retriever.
8. Add eval questions.
9. Integrate RAG behind config flag.
10. Add citations.
11. Fix document routing using RAG confidence gate.
12. Run full tests and API smoke checks.

Do not delete current fallback retrieval until the new RAG path is proven.

---

## 18. Authoritative implementation decisions (2026-10-14)

These requirements override earlier alternatives and illustrative thresholds.

### 18.1 Milestones and delivery

M0: canonical ingestion, provenance normalization, duplicate control, read-only validation CLI and regression tests. No change to live answers and no external model calls.
M1: lexical baseline, embedding/provider contracts, genuine multilingual dense retrieval, persistent vector adapter, rank fusion and passage-level evaluation.
M2: bounded answer generation, supporting citations, safe routing/fallback, feature-flagged API integration and privacy regression tests.
M3: citation UI, per-language query/answer behavior and real browser acceptance tests.
M4: remote vector adapter, timeout/retry/resource budgets, atomic versioned index rollout/rollback, deployment and failure testing.

After each complete milestone: run its tests plus existing regressions, inspect staged diff, commit only owned changes, fetch, integrate collaborator changes safely, push without force and verify remote HEAD. Never overwrite collaborator work. Report precisely which milestone is complete. A working loader is not a working RAG system.

### 18.2 Cross-lingual retrieval and answer language

- Keep original query, masked query, requested answer language and detected input language separate. A UI language selection is not proof of input language.
- Mask both question and document before remote translation, embeddings or generation. Current pipeline retains the raw question in `safe_request`; correct this before any network-capable routing is added.
- Evaluate a multilingual embedding candidate against English, Hindi, Gujarati, Hinglish and transliterated Gujarati examples. `paraphrase-multilingual-MiniLM-L12-v2` is a candidate, not guaranteed Gujarati support. Pin model revision, dimensions, tokenizer and normalization in the index manifest. Use the same encoder contract at indexing and query time.
- If a language does not meet acceptance criteria, use an explicit QueryTranslator adapter to English after masking. Preserve PAN/Aadhaar/ITR/VID identifiers, form codes, numeric amounts and dates. Search original and translated variants, with lexical search for exact terms. Do not silently translate the stored evidence.
- Translation failure must return an honest unsupported-language/clarification response or an explicitly labeled English fallback. Never mark English-only answers as translated.
- Retain chunk language as `und` when unknown; do not infer Hindi from a URL or Gujarati from navigation links. Query translation and output translation are different components.
- Start with at least 20 held-out question pairs per advertised language, labeled to relevant source passages and unanswerable cases, plus mixed-language cases. Evaluate retrieval per language, numeric preservation and answer groundedness separately. Automated evaluation is useful but is not expert factual certification.

### 18.3 Backward-compatible citations and frontend contract

At M2 extend Answer additively, preserving source_url and last_verified for old clients:

- `citations`: default empty list. Each item has a request-scoped ID, chunk ID, source URL, title, section, evidence excerpt, nullable factual-check date and explicit verification label.
- `claim_citations`: mappings from displayed summary/step/warning to citation IDs that actually support that claim.
- `retrieval_status`: not_run, supported, insufficient, conflict or unavailable. Retrieval scores are not probabilities of correctness.
- `answer_language` and `language_status`: report actual delivered language and fallback state.

Server builds citations from retrieved records, not model-invented URLs or dates. A valid URL is not proof that a claim is supported. Reject unknown citation IDs, detect unsupported material claims, preserve conflicting-source warnings and abstain when necessary. Processing dates must not become fresh verification dates.

At M3 change frontend/app.js to render accessible numbered source buttons next to supported content and a source list showing title, section, source domain, date availability and verification label. Keep the old single-source renderer when citations is empty or absent. Use DOM textContent for untrusted text, validate http(s) URLs, reject javascript/data URLs, and set rel=noopener noreferrer for new tabs. Add minimal responsive styles in style.css and accessible markup in index.html. Show insufficient/conflicting evidence without falsely reassuring users with a numeric confidence percentage.

Browser acceptance: legacy answers, one/multiple citations, Unicode labels, long titles, absent dates, malformed URLs, HTML/XSS strings, keyboard navigation, narrow screens and backend failure. Frontend updates belong to M3, not this ingestion milestone.

### 18.4 Canonical data, provenance and provider boundaries

- Load ONLY the two explicitly listed refined JSONL files by default. Never recursively ingest both aggregate JSONL and individual JSON mirrors or the obsolete processed dataset.
- Resolve manifest paths within the approved data directory. Bound file, record and corpus sizes; validate JSON, nonempty text, IDs, dates, numeric scores and exact permitted URL hosts. Do not fetch source URLs during loading.
- Keep producer status/date/quality separate from factual verification. All existing automated records normalize to factual `unverified`. Host allowlisting is a provenance screening rule only. Leave original files unchanged.
- Use deterministic category+normalized-content fingerprints to deduplicate identical text while preserving every contributing source reference. Reject conflicting reuse of an ID. Do not drop useful short complete FAQs solely for missing a word target; flag suspicious sizes instead. Near-duplicates and boilerplate need separate evaluation.
- Manifest records corpus selection and schema version. Ingestion output records source-file hashes, accepted/rejected counts, duplicate counts, coverage and warnings. Candidate documents are eligible for indexing, not approved factual answers.
- Source adapters (JSONL, future SQL/API) are separate from embedding adapters and vector-store adapters. Supporting another database requires an implemented/tested adapter, not merely changing a setting.
- Start with canonical ingestion with no new dependency. Before M1 choose one real persistent backend after checking environment and provider fit. Do not implement every Chroma/FAISS/Qdrant alternative. Preserve provider-independent upsert/search/delete/health contracts and index metadata.
- Build indexes into versioned staging directories/collections. Verify IDs/counts/model fingerprints before atomically activating. Keep rollback and idempotent updates/deletions. Never ingest private user uploads into the public corpus.

### 18.5 Safety and release gates

- Treat retrieved text as untrusted data, never agent instructions. Test prompt injection in queries, uploads and source chunks.
- Do not depend on arbitrary quality_score >= 0.75 or status=verified for truth. Source freshness, effective dates, conflicts and claim support need evidence.
- A legal notice without adequate legal sources must not be answered with an unrelated PAN/savings-account guide. Every fallback is gated too.
- Unit tests are not a factual accuracy benchmark. A phase gate needs observed results from the actual CLI/provider/API/browser workflow for that phase.
- Do not claim production readiness from a review rating. Record unsupported features and blocked external dependencies explicitly.

### 18.6 Primary technical references

Reviewed for planning, not evidence of project accuracy:

```text
https://www.sbert.net/docs/sentence_transformer/pretrained_models.html
https://www.sbert.net/examples/sentence_transformer/training/multilingual/README.html
https://qdrant.tech/documentation/search/hybrid-queries/
```

## 17. One-line goal

Turn GovBank Assistant from a small verified guide chatbot into a source-grounded, citation-based, flexible RAG assistant that can use PAN, UIDAI, and future official datasets through a swappable vector database layer.
