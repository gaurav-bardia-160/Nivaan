# BRIEFING — 2026-11-04T13:16:00Z

## Mission
Investigate test fixtures/runners, Scenes 1-3 test batch, confidence badge logic, LLM synthesis prompt directives, and AGENTS.md guardrails to prepare for R3, R4, R7, and regression test suites.

## 🔒 My Identity
- Archetype: teamwork_spec_miner
- Roles: Specification Investigator
- Working directory: c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3
- Original parent: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Milestone: Survey & Investigation (Scenes 1-3, Tests, Confidence Badge, LLM Prompts, Guardrails)

## 🔒 Key Constraints
- Zero Predefined Responses: Never use or re-introduce predefined, hardcoded, or pre-canned responses. Dynamic generation only.
- Read-only: Do NOT implement anything — you are read-only.
- Prioritize authoritative sources over LLM prior knowledge.
- Only write to your assigned directory: c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3

## Current Parent
- Conversation ID: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Updated: 2026-11-04T13:04:09Z

## Task Summary
- **What to build**: Specification investigation for R3 (Confidence badge decoupling), R4 (LLM synthesis relevance gate & hallucination guardrails), R7 (AGENTS.md guardrails), test runners/fixtures, and Scenes 1-3 test batch failures.
- **Success criteria**: Comprehensive discovery and analysis documented in handoff.md, with clear evidence chain and verification commands.
- **Interface contracts**: ORIGINAL_REQUEST.md
- **Code layout**: backend/modules/llm.py, backend/rag/, tests/, AGENTS.md, GEMINI.md

## Key Decisions Made
- Identified exact Scenes 1-3 test batch files in `backend/data/conversations/`: `chat_1793792993115_k2y6f.json` (Scene 1), `chat_1793793767437_wbeu6.json` (Scene 2), `chat_1793794139711_p0bhr.json` (Scene 3).
- Traced the exact failure mechanisms: cross-domain bleed into nearest neighbors, unstated fact hallucination (closed establishment assumption), lack of same-domain discrimination (AIS feedback vs 139(9)), and CRAG table DOM noise.
- Analyzed confidence badge calculation: identified current coupling to raw RRF/cosine similarity in `explainer.py`, `confidence.py`, and `pipeline.py`. Formulated MATCH/PARTIAL/NO_MATCH post-retrieval decoupling architecture.
- Analyzed LLM prompt directives in `backend/modules/llm.py`: identified missing ban on unstated situational fact fabrication and structured the relevance-gating instructions.
- Inspected `AGENTS.md` and `GEMINI.md`: established the exact list of guardrails to add per R7.

## Artifact Index
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3\handoff.md — Final handoff report
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3\progress.md — Progress and liveness tracker
