# Build order

## Start here

1. Agree on contracts in `docs/CONTRACTS.md`.
2. Update `backend/schemas.py` with those contracts.
3. Update `samples/` to match the schemas.
4. Commit.

## Then Phase 1

Person A:
- `backend/data/knowledge_base.json`
- `backend/modules/retrieval.py`

Person B:
- `frontend/index.html`
- `frontend/style.css`
- `frontend/app.js`

## Later phases

- Explainer and privacy/OCR.
- Router, flagger, translation, voice.
- Pipeline and FastAPI integration.
- Tests, user feedback, presentation.

## Do not start yet

- Crawler.
- Vector database.
- Agent loop.
- Document upload.
- Real confidential files.
