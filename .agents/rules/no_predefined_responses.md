# Rule: No Predefined Responses

## Directives
- **Zero Predefined / Canned Responses**: Never return hardcoded answers from static JSON files or code dictionaries.
- **Dynamic Retrieval**: All answers must be generated dynamically from official retrieved chunks (RAG) or live allowlisted government web search (CRAG).
- **No Predefined Disclaimers**: Disclaimers must refer directly to the official government portal, not missing pre-verified entries.
- **Honest Refusal**: If official sources lack evidence for a query, state this transparently instead of hallucinating or forcing a canned template.
