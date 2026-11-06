# BRIEFING — 2026-11-04T13:05:00Z

## Mission
Investigate backend RAG architecture, vector retrieval, and procedure discrimination to prepare for R2 (hard domain routing) and R6 (same-domain sub-procedure granularity).

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: explorer, analyst, synthesizer
- Working directory: c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1
- Original parent: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Milestone: Survey 1 - RAG Retrieval Architecture, Domain Routing, Sub-Procedure Discrimination (R2, R6)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- AGENTS.md / GEMINI.md Zero Predefined Responses directive: never use or re-introduce predefined/pre-canned responses. Dynamic generation or honest ungrounded refusal.
- Write only to your folder c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1\
- NEVER place source code, tests, or data files in .agents/teamwork/
- Never name a file AGENTS.md or GEMINI.md

## Current Parent
- Conversation ID: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Updated: not yet

## Investigation State
- **Explored paths**: `backend/rag/retriever.py`, `backend/rag/runtime.py`, `backend/rag/vector_store.py`, `backend/rag/embeddings.py`, `backend/modules/domain_router.py`, `backend/pipeline.py`, `backend/data/refined/troubleshooting/troubleshooting_tax.jsonl`, `backend/data/rag_manifest.json`, `backend/offline/build_vector_db.py`, `backend/offline/ensure_vector_db.py`.
- **Key findings**:
  1. Vector search uses FastEmbed ONNX `MiniLM-L12` (384-dim) and local Qdrant collection `govbank_chunks` with cosine distance. Fused with lexical BM25 via RRF `1/(60+rank)`.
  2. Uncovered domains (MCA/SPICe+, petroleum/LPG, NSP scholarships) currently get classified as `Domain.UNKNOWN`. When queries contain common civic tokens (portal, subsidy, failed, delay), `runtime.py` falls back to `category="civic"`. Qdrant nearest-neighbor search then matches arbitrary civic chunks (e.g., Udyam, Ration card), leading to severe cross-domain retrieval bleed and hallucination during LLM synthesis.
  3. Pre-vector search hard domain routing interceptor must be added to `backend/rag/retriever.py` and `domain_router.py` to short-circuit uncovered domain queries to empty hits with `status="uncovered_domain"`, returning an honest dynamic ungrounded refusal adhering to AGENTS.md zero-predefined-response directive.
  4. Same-domain confusion between Section 139(9) defective return and AIS feedback occurs because: (a) the corpus has `itr_defective_return_manual_01` mentioning AIS mismatches, but lacks an authentic `itr_ais_feedback_manual_01` document; (b) both share terms ("AIS", "mismatch", "incometax", "rectify"); (c) `retriever.py` symptom clusters lack an `ais_feedback` cluster and lack anti-contamination penalties against `defective_return`.
- **Unexplored areas**: None for survey_1 scope. Ready for structured handoff.

## Key Decisions Made
- Formulate two-tier interception: (1) Domain classifier identifies uncovered domains; (2) `RagRetriever.search` directly aborts before BM25/vector search to prevent nearest-neighbor bleed.
- Propose new authentic official document `itr_ais_feedback_manual_01` and bidirectional symptom cluster discrimination in `retriever.py` to cleanly isolate Section 139(9) and AIS feedback.

## Artifact Index
- DISPATCH.md — incoming task dispatch
- BRIEFING.md — working memory and identity
- progress.md — liveness heartbeat
- handoff.md — final 5-component handoff report
