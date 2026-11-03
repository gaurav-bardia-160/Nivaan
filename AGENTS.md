# Nivaan - Project Core Directives & Memory

## Rule: Zero Predefined Responses
- **NEVER use or re-introduce predefined, hardcoded, or pre-canned responses.**
- All user-facing procedural answers, steps, document lists, and summaries must be dynamically generated from:
  1. Dense vector and lexical RAG retrieval against official canonical government documents.
  2. Live Corrective RAG (CRAG) web search on allowlisted official portals (`parivahan.gov.in`, `incometax.gov.in`, `uidai.gov.in`, `passportindia.gov.in`, `epfindia.gov.in`, etc.).
  3. Dynamic local LLM synthesis over the retrieved passages.
- Never output disclaimers referencing "pre-verified guides" or "predefined responses".
- If neither RAG nor live search has evidence to answer a question, provide an honest, ungrounded refusal rather than falling back to a pre-canned answer template.
