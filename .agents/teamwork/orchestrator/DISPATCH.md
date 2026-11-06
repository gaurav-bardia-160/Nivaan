# Dispatch Log

## 2026-11-04T13:02:07Z
Sender: 223e7ed8-0437-4dcc-89bd-101dfe69e7c2
Priority: MESSAGE_PRIORITY_HIGH

Remediate RAG pipeline failures identified in the Scenes 1-3 test batch (Nov 2026) for production pipeline stabilization, covering corpus source verification, domain routing, post-retrieval confidence decoupling, relevance gating, scraper cleanup, sub-procedure discrimination, and guardrail additions.

Working directory: c:\Users\gaura\Documents\nivaan
Integrity mode: development

## Requirements

### R1. EPFO Corpus Source Verification and Remediation
Inspect the 3 EPFO documents in `backend/data/rag_manifest.json` hosted on `pmvbry-cdn.epfindia.gov.in` (Joint Declaration SOP, Attestation Framework for Closed Establishments, Passbook/Cheque Validation Standards) to verify whether their content matches their titles or consists of PMVBRY boilerplate. If the content is boilerplate, fetch and ingest authentic official EPFO circulars/SOPs matching the titles into the corpus.

### R2. Hard Domain Routing and Retrieval Bleed Prevention
Add hard domain routing / intent classification before vector search in `backend/rag/retriever.py`. Short-circuit queries belonging to uncovered domains (MCA/SPICe+, petroleum/LPG, NSP scholarships) so they do not fall back to nearest-neighbor vector retrieval, returning an honest ungrounded refusal that the domain is uncovered in accordance with the `AGENTS.md` zero-predefined-response directive.

### R3. Confidence Badge Decoupling from Cosine Similarity
Decouple the confidence badge from raw cosine similarity scores by implementing a post-retrieval relevance check that evaluates retrieved context into MATCH, PARTIAL, or NO_MATCH before LLM synthesis.

### R4. LLM Synthesis Relevance Gating and Hallucination Guardrails
Add a relevance-gate prompt directive in `backend/modules/llm.py` that explicitly prevents synthesizing answers from mismatched domains or fabricating unstated facts (such as assuming an establishment is closed when not stated).

### R5. Scraper DOM Noise Elimination in CRAG Fallback
Replace raw requests/BeautifulSoup parsing in the Corrective RAG (CRAG) fallback path with `trafilatura` extraction to remove scraper DOM noise.

### R6. Same-Domain Sub-Procedure Granularity
Improve sub-procedure discrimination within the same domain to accurately distinguish between closely related procedures, specifically distinguishing Section 139(9) defective returns from AIS feedback.

### R7. AGENTS.md Guardrail Updates
Update `AGENTS.md` with guardrails reflecting these RAG pipeline failure mitigations.

## Acceptance Criteria

### Automated Tests & Regression Suite
- [ ] Automated regression/unit tests reproducing the failure scenarios from Scenes 1-3 are implemented and pass.
- [ ] EPFO documents in `backend/data/rag_manifest.json` have verified authentic content matching their titles rather than PMVBRY boilerplate.
- [ ] Queries for uncovered domains (MCA/SPICe+, petroleum/LPG, NSP scholarships) are intercepted by intent classification/domain routing prior to vector search and return an honest refusal without nearest-neighbor cross-domain bleed.
- [ ] Post-retrieval relevance check (MATCH, PARTIAL, NO_MATCH) determines the confidence badge rather than raw cosine similarity alone.
- [ ] LLM synthesis adheres to the relevance-gate directive without cross-domain bleed or fabricating unstated facts (such as unstated closed establishment status).
- [ ] CRAG fallback path utilizes `trafilatura` for web extraction in place of raw requests/BeautifulSoup.
- [ ] Queries regarding Section 139(9) defective returns and AIS feedback correctly resolve to their respective distinct sub-procedures.
- [ ] `AGENTS.md` contains the updated guardrails.

## 2026-11-04T18:05:11Z
Sender: 223e7ed8-0437-4dcc-89bd-101dfe69e7c2
Priority: MESSAGE_PRIORITY_HIGH

Quota has reset. Please resume orchestration.
