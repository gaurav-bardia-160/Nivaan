# Task Assignment: Survey 1 - RAG Retrieval, Hard Domain Routing, and Sub-Procedure Discrimination

## Mission
Investigate backend RAG architecture, vector retrieval, and procedure discrimination to prepare for R2 and R6.

## Scope & Questions
1. Read `c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md`.
2. Inspect `backend/rag/retriever.py` and related retrieval modules:
   - How does vector search work? Where are embeddings computed and queried?
   - How is query intent currently classified or routed? Is there any existing domain routing?
   - How should hard domain routing intercept queries for uncovered domains (MCA/SPICe+, petroleum/LPG, NSP scholarships) to prevent vector fallback and return an honest refusal?
   - How are Section 139(9) defective returns and AIS feedback indexed and retrieved? What causes the cross-procedure confusion and how can same-domain sub-procedure discrimination be made granular?
3. Identify existing code structure, function signatures, classes, dependencies, and potential side-effects.
4. Run no builds or tests directly unless needed for passive checks; your primary output is an evidence-backed investigation report.
5. Write your complete findings to `.agents/teamwork/survey_1/handoff.md`.


## 2026-11-04T13:03:55Z
You are survey_1, an exploration agent (teamwork_explorer).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md and c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1\DISPATCH.md.
Investigate backend RAG architecture, vector retrieval, and procedure discrimination to prepare for R2 and R6.
1. Inspect `backend/rag/retriever.py` and related retrieval modules.
2. Determine how vector search works, how queries are routed or if routing exists.
3. Investigate how hard domain routing / intent classification can short-circuit queries for uncovered domains (MCA/SPICe+, petroleum/LPG, NSP scholarships) before vector search, returning an honest refusal in accordance with the AGENTS.md zero-predefined-response directive.
4. Investigate same-domain sub-procedure granularity: how Section 139(9) defective returns and AIS feedback are retrieved, why cross-procedure confusion occurs, and how to accurately distinguish them.
5. Identify all key files, function signatures, dependencies, and propose concrete technical remediation strategies.
Write your complete analysis and structured handoff to:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_1\handoff.md
When finished, notify me using send_message.
