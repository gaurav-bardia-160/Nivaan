# GovBank Assistant

Status: aligned folder skeleton only. No runnable application yet.

This project is planned as a communication assistant for government, legal, and banking tasks. It has two big parts:

1. **Offline knowledge building**: collect official-source material, clean it, structure it, verify it, then index it.
2. **Online user serving**: read user input, mask sensitive data before external AI use, retrieve relevant verified material, explain it simply, translate it, and show sources.

## Current state

- Folder structure exists.
- Local Git repository exists.
- No real backend logic is implemented.
- No crawler, vector database, AI provider, OCR, translation, or document upload is implemented.
- Privacy controls are only planned, not verified.

## Main folders

- `backend/offline/`: future Phase 1 knowledge-building scripts.
- `backend/modules/`: future Phase 2 runtime modules.
- `backend/data/`: source lists, future chunks, verified entries, and index folders.
- `frontend/`: future website files.
- `samples/`: fake request, answer, source, and chunk contracts.
- `tests/`: future tests.
- `docs/`: architecture and build notes.

## Build rule

Do not jump into the agent loop or crawler first. First agree on contracts in `backend/schemas.py` and samples in `samples/`.

## Privacy wording

If the backend receives a document, the backend sees the original file. So we should say **masked before external AI**, not "nobody sees it." True on-device masking can be added later as a separate design.
