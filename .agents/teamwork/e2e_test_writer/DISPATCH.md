# Task Assignment: E2E Test Suite Creation for Scenes 1-3 Regression

## Mission
Design and implement the automated E2E regression and unit test suite in `tests/test_scenes_1_to_3_regression.py` covering Tiers 1-4 based on `ORIGINAL_REQUEST.md`, `PROJECT.md`, `TEST_INFRA.md`, and the survey reports. When complete, publish `TEST_READY.md` at project root `c:\Users\gaura\Documents\nivaan\TEST_READY.md`.

## Test Requirements (Tiers 1-4)
1. **Tier 1 - Feature Coverage**:
   - R1: Test EPFO documents in `troubleshooting_civic.jsonl` have official source URLs and valid content.
   - R2: Test queries for MCA/SPICe+, petroleum/LPG, and NSP scholarships are intercepted by domain router / retriever and return `uncovered_domain` / empty hits without nearest-neighbor vector bleed.
   - R3: Test confidence badge calculation evaluates semantic relevance (`MATCH`, `PARTIAL`, `NO_MATCH`) rather than raw cosine similarity alone.
   - R4: Test LLM synthesis relevance gate directives prevent synthesizing answers from mismatched domains or fabricating unstated facts (e.g. closed establishment).
   - R5: Test CRAG web fetcher extracts clean text via `trafilatura` with `include_tables=False` and rejects directory markdown tables.
   - R6: Test sub-procedure discrimination between Section 139(9) defective returns and AIS feedback.
2. **Tier 2 - Boundary & Corner Cases**:
   - Queries with generic civic trouble words ("error", "subsidy", "failed", "resubmission") across covered and uncovered domains.
   - AIS feedback queries containing words like "defective" or "notice".
   - Section 139(9) queries containing words like "AIS" or "mismatch".
   - CRAG web pages containing only HTML tables.
3. **Tier 3 - Cross-Feature Combinations**:
   - Domain router interception + confidence badge (uncovered domain produces low confidence / refusal, not high confidence).
   - Sub-procedure discrimination + LLM prompt grounding.
4. **Tier 4 - Real-World Application Scenarios (Verbatim Scenes 1-3 Turns)**:
   - Scene 1 Turn 1: EPFO Joint Declaration DSC error with active employer (must NOT hallucinate closed establishment).
   - Scene 1 Turn 3: SPICe+ Part A MCA name reservation (must NOT bleed into EPFO passbook/cheque).
   - Scene 2 Turn 1: NSP scholarship status "Defective by Institute" (must NOT bleed into Section 139(9)).
   - Scene 2 Turn 2: AIS SFT mutual fund duplicate feedback (must resolve to AIS feedback, NOT Section 139(9)).
   - Scene 3 Turn 1: LPG subsidy dormant account MoPNG grievance (must NOT bleed into EPFiGMS).
   - Scene 3 Turn 2: Post Office MIS claim without nomination (must NOT return raw table DOM noise).

## Output Deliverables
- Write `tests/test_scenes_1_to_3_regression.py`.
- Run pytest on the new test file to verify its syntax, fixtures, and execution structure.
- Write `c:\Users\gaura\Documents\nivaan\TEST_READY.md`.
- Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_test_writer\handoff.md`.


## 2026-11-04T13:33:34Z
You are e2e_test_writer, a specialized test writer (teamwork_test_writer).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_test_writer
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read:
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\TEST_INFRA.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_test_writer\DISPATCH.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_2_gen2\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3\handoff.md

Implement the automated regression test suite covering Tiers 1-4 in `tests/test_scenes_1_to_3_regression.py`.
Verify that the tests run via pytest.
Publish `c:\Users\gaura\Documents\nivaan\TEST_READY.md`.
Write your full handoff report to:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\e2e_test_writer\handoff.md
When done, notify me via send_message.
