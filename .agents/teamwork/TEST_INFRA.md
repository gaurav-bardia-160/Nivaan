# E2E Test Infra: RAG Pipeline Remediation (Scenes 1-3)

## Test Philosophy
- Opaque-box, requirement-driven, derived strictly from `ORIGINAL_REQUEST.md` and Scenes 1-3 failure batch.
- Strictly verifies that queries do not suffer from cross-domain retrieval bleed, raw table DOM noise, confidence inflation, or unstated fact hallucination.
- Verifies adherence to the zero-predefined-response directive in `AGENTS.md`.

## Feature Inventory & Test Coverage Goals
| # | Feature | Requirement | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Real-World) |
|---|---------|-------------|:-----------------:|:-----------------:|:---------------------:|:-------------------:|
| 1 | EPFO Corpus Authenticity | R1 | 5 | 5 | ✓ | Scene 1 Turn 1 |
| 2 | Hard Domain Routing: MCA/SPICe+ | R2 | 5 | 5 | ✓ | Scene 1 Turn 3 |
| 3 | Hard Domain Routing: Petroleum/LPG | R2 | 5 | 5 | ✓ | Scene 3 Turn 1 |
| 4 | Hard Domain Routing: NSP Scholarships | R2 | 5 | 5 | ✓ | Scene 2 Turn 1 |
| 5 | Post-Retrieval Confidence Decoupling | R3 | 5 | 5 | ✓ | All Scenes |
| 6 | LLM Relevance Gate & Anti-Fabrication | R4 | 5 | 5 | ✓ | Scene 1 Turn 1, Scene 3 Turn 1 |
| 7 | Scraper DOM Noise Elimination | R5 | 5 | 5 | ✓ | Scene 3 Turn 2 |
| 8 | Sub-Procedure Discrimination (139(9) vs AIS) | R6 | 5 | 5 | ✓ | Scene 2 Turn 2 |

## Test Architecture
- Test Suite File: `tests/test_scenes_1_to_3_regression.py`
- Test Runner: `py -m pytest tests/test_scenes_1_to_3_regression.py -v`
- Pass/Fail Semantics: 100% of tests must pass with exit code 0.
