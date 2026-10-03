# GovBank Assistant

Status: folder structure and placeholders only. No runnable application yet.

An intended communication assistant for understanding government, legal, and banking information. Features, sources, privacy controls, and providers are not implemented or verified.

## Folder map

- `backend/main.py`: planned API entry point
- `backend/config.py`: planned configuration
- `backend/schemas.py`: shared request and answer shapes, to agree together
- `backend/pipeline.py`: planned processing flow
- `backend/modules/`: reading, privacy, routing, retrieval, flagging, explanation, translation and voice
- `backend/data/knowledge_base.json`: empty guide library
- `backend/requirements.txt`: future backend dependencies
- `frontend/`: placeholder HTML, CSS, JavaScript, and sample answer
- `tests/`: future component and integration checks
- `.env.example`: placeholder configuration, no credentials

## Build together, one part at a time

1. Discuss the first supported task and what the screen should show.
2. Agree on request and answer fields.
3. Review one official-source guide and its evidence.
4. Build and test the question flow.
5. Discuss AI integration before adding it.
6. Design and test privacy before accepting documents.
7. Add languages and voice only when the core is ready.

Do not start the next component without discussing it with the user.

## Privacy and Git

Never commit API keys or personal documents. Server-side masking is not on-device processing. No privacy guarantee exists merely because a placeholder file is named privacy.py.

This is a local Git repository only. No remote hosting or deployment is configured.
Optional result.html and a logo can be added when the interface design is agreed.
