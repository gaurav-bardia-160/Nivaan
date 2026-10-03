# GovBank Assistant

Status: simplified skeleton only. No runnable app yet.

This structure follows the two-person split:

- Person A: knowledge, retrieval, flagging, explaining.
- Person B: input, privacy, routing, agent/tools, translation/voice, frontend.
- Both: shared backend contract and integration files.

## Important notes

- Python package files are named `__init__.py`, not `_init_.py`.
- Do not commit a real `.env` file. Use `.env.example` as the template.
- `backend/data/knowledge_base.json` should contain verified entries only.
- `backend/data/structured/` can contain entries with `status: unverified` or `status: verified` while being prepared.
- `samples/fake_documents/` is only for fictional test documents.
