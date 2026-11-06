# BRIEFING — 2026-11-04T17:15:00Z

## Mission
Conduct an independent adversarial review of Milestone 2: Uncovered Domains isolation, short-circuit retrieval, refusal pipeline, and logging.

## 🔒 My Identity
- Archetype: teamwork_reviewer
- Roles: reviewer, critic
- Working directory: c:\Users\gaura\Documents\nivaan\.agents\teamwork\reviewer_m2
- Original parent: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Milestone: milestone_2
- Instance: 1 of 1

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code
- Zero Predefined Responses: Never allow pre-canned answers; refusals must be honest and dynamic or cleanly structured
- Check for integrity violations: hardcoded results, dummy facades, test cheating

## Current Parent
- Conversation ID: dbf15a36-ef58-4a18-a9f2-171e93acf6cc
- Updated: 2026-11-04T17:15:00Z

## Review Scope
- **Files to review**:
  - `backend/modules/domain_router.py`
  - `backend/rag/retriever.py`
  - `backend/rag/runtime.py`
  - `backend/pipeline.py`
  - `tests/test_domain_router.py`
- **Interface contracts**:
  - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md`
  - `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`
- **Review criteria**:
  - Domain.UNCOVERED classification correctness
  - Short-circuit retrieval without Qdrant/FastEmbed/BM25 execution
  - Dynamic refusal and logging to unresolved_queries.csv
  - Non-regression on Tier 1 R1/R5
  - Adversarial robustness & integrity verification

## Key Decisions Made
- Executed independent test runs (15/15 Tier 1 R2, 35/35 test_domain_router, 10/10 R1/R5, 42/42 web search & build vector).
- Validated core R2 requirements: `Domain.UNCOVERED`, short-circuit in `retriever.py`, refusal structure in `pipeline.py`, and logging to `unresolved_queries.csv`.
- Discovered 2 major adversarial failure modes: (1) case-insensitive `\bdin\b` hijacking common Hindi/Hinglish queries containing "din" (day), (2) raw substring check `"roc" in lowered` in `_build_uncovered_domain_refusal()` misclassifying queries with "process" as MCA corporate registration.
- Rendered verdict: REQUEST_CHANGES.

## Artifact Index
- `handoff.md` — Final review and verdict handoff report
- `progress.md` — Liveness and step tracking
- `DISPATCH.md` — Task assignment and instructions

## Review Checklist
- **Items reviewed**:
  - `backend/modules/domain_router.py`: reviewed
  - `backend/rag/retriever.py`: reviewed
  - `backend/rag/runtime.py`: reviewed
  - `backend/pipeline.py`: reviewed
  - `tests/test_domain_router.py`: reviewed
  - `tests/test_scenes_1_to_3_regression.py`: reviewed
- **Verdict**: REQUEST_CHANGES
- **Unverified claims**: none remaining; all claims independently verified.

## Attack Surface
- **Hypotheses tested**:
  - Hindi/Hinglish vocabulary collisions in regex patterns: CONFIRMED VULNERABILITY (`\bdin\b` collides with Hindi "दिन").
  - Substring collision in pipeline refusal domain classifier: CONFIRMED VULNERABILITY (`"roc"` matches `"process"`).
  - General Hindi initiative vocabulary collision: CONFIRMED VULNERABILITY (`\bpahal\b` collides with Hindi "पहल").
  - Word boundary stripping on SPICe+: CONFIRMED VULNERABILITY (`spice\+?` matches airline "Spice jet").
- **Vulnerabilities found**:
  - `\bdin\b` intercepts covered passport/DL/Aadhaar/EPF queries.
  - Substring `"roc"` in `_build_uncovered_domain_refusal()` labels NSP scholarship queries as MCA.
- **Untested angles**: Full multilingual phonetic transliteration (out of scope for M2).
