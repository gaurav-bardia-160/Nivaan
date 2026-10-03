# Contracts to agree before coding

## AskRequest draft

- `input_type`: `question` or `document`
- `question`: user question text
- `language`: `en`, `hi`, or `gu` later
- `conversation_id`: optional, for follow-up context
- `file_attached`: true or false

## Answer draft

- `title`
- `summary`
- `documents_needed`
- `steps`
- `warnings`
- `source_url`
- `last_verified`
- `confidence`
- `masked_items`
- `disclaimer`

## KnowledgeEntry draft

- `id`
- `area`
- `title`
- `keywords`
- `documents_needed`
- `steps`
- `common_mistakes`
- `source_url`
- `last_verified`
- `verified`

## Chunk draft

- `chunk_id`
- `source_url`
- `retrieved_at`
- `heading`
- `text`
- `verified`

No code should depend on these until both teammates agree they are final enough for Phase 1.
