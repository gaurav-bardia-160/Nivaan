# Progress Tracker — Milestone 2 Iteration 2

Last visited: 2026-11-04T17:40:00Z

## Status
- [x] Read DISPATCH.md, reviewer_m2, challenger_m2, auditor_m2 handoffs, and project specs
- [x] Initialized BRIEFING.md and progress.md
- [x] Inspect existing `backend/modules/domain_router.py`, `backend/pipeline.py`, `backend/rag/retriever.py`, and test files
- [x] Implement regex and domain router improvements in `backend/modules/domain_router.py`:
  - Disambiguated Hindi "din" (days) from Director Identification Number (DIN) using contextual tokens and uppercase `\bDIN\b`
  - Required scheme context for PAHAL (`\b(?:pahal\s+(?:scheme|yojana|dbtl|subsidy|lpg)|(?:lpg|dbtl)\s+pahal)\b` and `\bPAHAL\b`)
  - Separated `\bspice\+(?!\w)` and require plus/part context (`spice\s+plus`, `spice\s+part`, `form\s+spice`) to avoid bare "spice" collisions
  - Expanded MCA patterns for company incorporation/registration: `incorporat(?:e|ion)\s+(?:of\s+)?(?:(?:a|the)\s+)?(?:new\s+)?company`, `company\s+incorporat(?:e|ion)`, `company\s+registration`, `private\s+limited\s+company`, `public\s+limited\s+company`, `one\s+person\s+company`, `\bopc\b`, `\bllp\b`, `limited\s+liability\s+partnership`
  - Expanded LPG patterns for solid brands (`bharat\s*gas`, `hp\s*gas`) and delivery/subsidy terms (`cooking\s+gas`, `gas\s+subsidy`, `gas\s+connection`, `cylinder\s+(?:delivery|booking|refill|status|subsidy|agency|delay|delayed)`)
  - Expanded NSP patterns with hyphen/space tolerance: `pre[-\s]?matric\s+scholarship`, `post[-\s]?matric\s+scholarship`, `merit[-\s]cum[-\s]means`, `scholarship\s+(?:portal|application|status|registration)`
- [x] Implement refusal labeling fix in `backend/pipeline.py`:
  - Replaced fragile substring matching (`"roc"`, `"din"`) with direct pattern matching against `_UNCOVERED_DOMAIN_PATTERNS`
  - Fixed domain labeling for NSP queries containing "process" or "pending" and LPG queries containing "procedure"
- [x] Enforce unconditional check in `backend/rag/retriever.py`:
  - Placed `if classify_domain(clean_query) == Domain.UNCOVERED or domain in (Domain.UNCOVERED, "uncovered"):` unconditionally at the top of `search()`
  - Prevented caller-passed `domain=Domain.GENERAL_CIVIC` bypass
- [x] Update tests in `tests/test_domain_router.py` and `tests/test_adversarial_m2_harness.py`:
  - Added Hindi "din" tests ensuring `"Passport banne me kitne din lagte hai?"`, `"Driving license kitne din me aayega?"` return covered domains, not UNCOVERED
  - Added Hindi "pahal" and bare "spice" non-collision tests
  - Added spelling and phrasing variation tests asserting `UNCOVERED` across all 14 empirical test cases
  - Added domain labeling accuracy tests asserting correct portal name in refusal summary without substring confusion
  - Added caller domain argument bypass tests verifying short-circuit
- [x] Run full test suites on Python 3.12:
  - 15 passed in `tests/test_scenes_1_to_3_regression.py -k "test_tier1_r2"`
  - 89 passed in `tests/test_domain_router.py` & `tests/test_adversarial_m2_harness.py`
  - 10 passed in `tests/test_scenes_1_to_3_regression.py -k "test_tier1_r1 or test_tier1_r5"`
  - 42 passed in `tests/test_web_search.py`, `tests/test_rag_loader.py`, `tests/test_build_vector_db.py`
  - Total: 156 passed, 0 failed
- [x] Write handoff report and notify parent
