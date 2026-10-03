# Architecture

## Phase 1: Offline knowledge building

Official sources flow through:

1. `sources.json`
2. `offline/crawl.py`
3. `offline/clean_chunk.py`
4. `offline/structure.py`
5. human verification
6. `offline/build_index.py`
7. searchable verified library

Output goal: every chunk and structured entry has source URL, retrieval date, verification status, and topic area.

## Phase 2: Online user serving

User input flows through:

1. frontend sends question or future document
2. `ocr.py` reads files when document support exists
3. `privacy.py` masks sensitive values before external AI
4. `router.py` identifies intent and area
5. `retrieval.py` finds verified chunks
6. `flagger.py` detects deadlines and risky clauses
7. `explainer.py` creates a structured answer
8. `tools.py` checks official pages only when needed
9. `translate_voice.py` adds language and audio support
10. frontend displays checklist, warnings, source, date, and disclaimer

## Agent scope

`agent.py` should come later. It is for deciding whether to ask a clarifying question, retrieve more context, call a freshness-check tool, or continue the conversation.
