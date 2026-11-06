# Task Assignment: Survey 3 - Test Suite, Confidence Badge, LLM Synthesis Guardrails, and AGENTS.md

## Mission
Investigate test fixtures/runners, Scenes 1-3 test batch, confidence badge logic, LLM synthesis prompt directives, and AGENTS.md guardrails to prepare for R3, R4, R7, and regression test suites.

## Scope & Questions
1. Read `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`.
2. Locate existing tests and test runner scripts:
   - Where are the test files located? (Look for `tests/`, `pytest`, test scripts, Scenes 1-3 test batch Nov 2026).
   - What test commands exist and how are tests run in this project?
   - What are the specific test failures in Scenes 1-3?
3. Inspect `backend/modules/llm.py` and confidence calculation:
   - How is the confidence badge currently calculated? (Trace where cosine similarity is used).
   - How is LLM synthesis called? What prompts and system instructions are used?
   - How should post-retrieval relevance check (MATCH, PARTIAL, NO_MATCH) be integrated?
   - How should the relevance-gate prompt directive be structured in `backend/modules/llm.py` to prevent hallucinating unstated facts (e.g. assuming establishment is closed)?
4. Inspect `AGENTS.md` and `GEMINI.md`:
   - What rules are currently defined?
   - What new guardrails need to be added per R7?
5. Write your complete findings to `.agents/teamwork/survey_3/handoff.md`.

## 2026-11-04T13:04:09Z
[Message] timestamp=2026-11-04T13:04:09Z sender=dbf15a36-ef58-4a18-a9f2-171e93acf6cc priority=MESSAGE_PRIORITY_HIGH
content=You are survey_3, a specification investigator (teamwork_spec_miner).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md and c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3\DISPATCH.md.
Investigate test fixtures/runners, Scenes 1-3 test batch, confidence badge logic, LLM synthesis prompt directives, and AGENTS.md guardrails to prepare for R3, R4, R7, and regression test suites.
1. Locate existing tests and test runner scripts across the repository (e.g. tests/, pytest, scripts, Scenes 1-3 test batch Nov 2026).
2. Trace the exact test failure scenarios from Scenes 1-3.
3. Inspect `backend/modules/llm.py` and confidence calculation:
   - Where is the confidence badge currently calculated? How is cosine similarity used?
   - How should post-retrieval relevance check (MATCH, PARTIAL, NO_MATCH) decouple confidence badges from raw cosine similarity?
   - How should the relevance-gate prompt directive be structured in `backend/modules/llm.py` to prevent hallucinating unstated facts (e.g. assuming establishment is closed)?
4. Inspect `AGENTS.md` and `GEMINI.md`:
   - What rules are currently defined?
   - What new guardrails need to be added per R7?
Write your complete analysis and structured handoff to:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_3\handoff.md
When finished, notify me using send_message.
