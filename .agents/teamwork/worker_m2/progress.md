# Progress — Milestone 2

- Last visited: 2026-11-04T17:05:00Z
- Status: COMPLETED
- Summary of Work:
  1. Implemented Domain.UNCOVERED and _UNCOVERED_DOMAIN_PATTERNS in `backend/modules/domain_router.py`.
  2. Implemented hard short-circuit in `backend/rag/retriever.py` returning status "uncovered_domain", hits=(), searched_documents=0.
  3. Isolated runtime retrieval in `backend/rag/runtime.py` (`supported_category` and `retrieve_if_enabled` return None).
  4. Intercepted uncovered domains in `backend/pipeline.py` (`run()` and `run_stream()`), logging to `unresolved_queries.csv`, bypassing web search, and returning honest dynamic ungrounded refusal adhering to AGENTS.md zero-predefined-response directive. Added `run_pipeline()` convenience function.
  5. Implemented comprehensive test suite in `tests/test_domain_router.py` (35 unit tests, 100% pass).
  6. Verified all 15 Tier 1 R2 tests in `tests/test_scenes_1_to_3_regression.py` pass. Verified R1, R5, web search, and rag retriever tests pass without regressions.
