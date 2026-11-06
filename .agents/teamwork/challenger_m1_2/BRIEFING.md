# BRIEFING — 2026-11-04T14:26:00Z

## Mission
Adversarially challenge and empirically verify EPFO corpus document retrieval and vector database integrity.

## 🔒 My Identity
- Archetype: challenger
- Roles: critic, specialist
- Working directory: c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m1_2
- Original parent: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Milestone: M1
- Instance: 2 of 2

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code
- Zero predefined responses directive (AGENTS.md / GEMINI.md)
- Empirical reproduction required — do NOT trust claims or logs without testing
- Layout compliance: .agents/teamwork/ holds metadata only

## Current Parent
- Conversation ID: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Updated: 2026-11-04T14:26:00Z

## Review Scope
- **Files to review**: `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl`, `backend/data/rag_manifest.json`, Qdrant collection `govbank_chunks`, retriever behavior
- **Interface contracts**: PROJECT.md / ORIGINAL_REQUEST.md
- **Review criteria**: Vector DB integrity (points=1387, dim=384, cosine distance, checksum), authentic official URLs, cancelled cheque & passbook query retrieval accuracy, cross-domain bleed resistance (corporate name reservation SPICe+ Rule 8A not erroneously boosting EPFO)

## Key Decisions Made
- Created reproducible adversarial test harness `tests/test_adversarial_m1_2_epfo_vector.py` covering Qdrant collection geometry, metadata parity, document schema, EPFO query retrieval rankings, and cross-domain bleed resistance.
- Executed empirical retrieval tests under both hybrid vector+lexical (FastEmbed MiniLM-L12 + Qdrant + BM25) and pure lexical mode.
- Rendered verdict APPROVE for Milestone 1 (R1 & vector database integrity).

## Artifact Index
- `BRIEFING.md` — persistent working memory
- `progress.md` — heartbeat and execution log
- `handoff.md` — final 5-component adversarial review handoff report
- `tests/test_adversarial_m1_2_epfo_vector.py` — 19-test automated adversarial challenge harness

## Attack Surface
- **Hypotheses tested**:
  - Hypothesis 1: Qdrant collection `govbank_chunks` has exact geometry: 1387 points, 384 dimensions, Cosine distance metric, and matching corpus SHA256 checksum (`5b329aa5f02688f1e3ee5e34f29d52b662965cc9bf5d0a858ee4192f3f78aee6`). Result: CONFIRMED (100% verified).
  - Hypothesis 2: EPFO document `epfo_claim_passbook_cheque_standards_01` in `troubleshooting_civic.jsonl` contains authentic official circular URL (`https://www.epfindia.gov.in/site_docs/PDFs/Circulars/Y2024-2025/WSU_IssueOfBKG_49885_16.pdf`), correct allowlisted host (`www.epfindia.gov.in`), and updated tags (`sop`, `epf_claim_rejected`, `epf_bank_kyc`) with zero PMVBRY boilerplate. Result: CONFIRMED.
  - Hypothesis 3: Queries regarding cancelled cheque rejection ("pre-printed name missing", "Form 19 rejection", "cancelled cheque stamp", "passbook attested", Hinglish variations) retrieve `epfo_claim_passbook_cheque_standards_01` as Rank 1. Result: CONFIRMED across all 6 test queries.
  - Hypothesis 4: Closed establishment attestation queries retrieve `epfo_closed_establishment_attestation_01` at Rank 1. Result: CONFIRMED.
  - Hypothesis 5: Joint Declaration SOP queries retrieve `epfo_joint_declaration_minor_major_sop_01` at Rank 1. Result: CONFIRMED.
  - Hypothesis 6: Corporate name reservation (SPICe+ Part A Rule 8A, MCA name approval), petroleum/LPG subsidies, and NSP scholarships do not leak or boost EPFO records into top hits. Result: CONFIRMED (0 bleed detected).
- **Vulnerabilities found**:
  - Concurrent access locking: Local file-based Qdrant client enforces single-process exclusive lock via `portalocker`. If an external unclosed process or previous test run holds the lock, runtime gracefully falls back to deterministic lexical search (`lexical_candidate_corpus`), but vector similarity is disabled until released. This is mitigated by proper fixture cleanup and handled safely in `backend/rag/runtime.py`.
- **Untested angles**:
  - Post-retrieval confidence decoupling and LLM relevance gating (scheduled for Milestones 2-4).
  - MCA/LPG hard domain short-circuit in retriever (scheduled for Milestone 2).

## Loaded Skills
- None specified in dispatch

