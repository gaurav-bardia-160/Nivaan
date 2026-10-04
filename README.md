# GovBank Assistant

Status: backend foundation in progress. The repository is not a runnable app yet, but the first shared data contracts, starter knowledge base, retrieval module, and backend tests are implemented.

This project follows the two-person split:

- Person A: knowledge, retrieval, flagging, explaining.
- Person B: input, privacy, routing, agent/tools, translation/voice, frontend.
- Both: shared backend contract and integration files.

## Current implemented pieces

- `backend/schemas.py`: strict Pydantic contracts for requests, answers, knowledge entries, warnings, steps, sources, and masked items.
- `backend/data/knowledge_base.json`: three starter entries for PAN, ITR basics, and loan agreement explanation. These are intentionally marked `unverified` until live official re-checks are done.
- `backend/modules/retrieval.py`: local fuzzy/keyword retrieval over the starter knowledge base.
- `tests/test_a.py`: backend foundation tests for schema validity, retrieval behavior, and safe rejection cases.

## Not implemented yet

- No FastAPI endpoint in `main.py` yet.
- No pipeline integration in `pipeline.py` yet.
- No explainer, privacy masking, OCR, router, agent loop, tools, translation, or voice implementation yet.
- No real document upload should be enabled yet.

## Important notes

- Python package files are named `__init__.py`, not `_init_.py`.
- Do not commit a real `.env` file. Use `.env.example` as the template.
- `backend/data/knowledge_base.json` should contain only entries that are safe to retrieve. Use `status: "unverified"` until facts, fees, and dates are checked live from official sources.
- `backend/data/structured/` can contain entries with `status: unverified` or `status: verified` while being prepared.
- `samples/fake_documents/` is only for fictional test documents.
