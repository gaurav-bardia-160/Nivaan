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


## 2026-11-09T11:54:36Z
Sender: 63247ec2-b8b8-40d2-a5ba-cd61604e4af3
Priority: MESSAGE_PRIORITY_HIGH

Remediate RAG and synthesis pipeline architectural gaps in Nivaan for production implementation, addressing test failures in Case 1 (Section 148A(b) reassessment notice) and Case 2 (Inoperative PAN / 20% TDS Refund).

Working directory: c:\Users\gaura\Documents\nivaan
Integrity mode: development

## Requirements

### R1. Response Shape and Scaffolding
Separate procedural/checklist queries from analytical, calculation, and legal-interpretation queries. Do not force every query into a 3-step procedural checklist ("Review [Doc 1], Review [Doc 2], Verify Official Portal"); provide direct analytical answers for analytical, calculation, and legal-interpretation queries.

### R2. Relevance and Confidence Gating Before Synthesis
Implement relevance and confidence gating prior to synthesis such that retrieved chunks lacking semantic alignment or cross-attention support with query terms do not output a HIGH confidence rating. When retrieved chunks lack sufficient support, trigger live CRAG search or output an honest refusal.

### R3. Multi-part Query Decomposition
Structure retrieval and synthesis to decompose multi-part user queries and answer every distinct sub-question.

### R4. Corpus Coverage for Reassessment and Inoperative PAN
Ingest official Income Tax Act statutory provisions and CBDT circulars covering reassessment (Sections 147, 148, 148A, 149, 151) and inoperative PAN consequences (Section 206AA, Rule 114AAA, Circular 03/2023) by fetching directly from official portals or adding official text into the local corpus manifest.

## Acceptance Criteria

### Case 1: Section 148A(b) Reassessment Notice (AY 2018-19)
- [ ] For the query: "I got an email notice under Section 148A(b) of the Income Tax Act for Assessment Year 2018-19 alleging ₹6.5 Lakhs in unexplained share trading transactions. Did the time limit to issue this notice expire under the 3-year vs 10-year rule, and how many days do I have to submit my reply?":
  - Response calculates limitation under Section 149 (AY 2018-19 ended 31 March 2019; 3-year base period expired; ₹6.5 Lakhs is below the ₹50 Lakhs threshold for 10-year extended limitation).
  - Response specifies the reply window under Section 148A(b) is minimum 7 days up to 30 days.
  - Off-topic retrieved documents (e.g., PAN FAQ, 139(9), 119(2)(b)) do not result in a HIGH confidence badge.
  - Response provides a direct analytical answer rather than a generic 3-step procedural checklist.

### Case 2: Inoperative PAN / 20% TDS Refund
- [ ] For the query: "My salary credit in August came with a flat 20% TDS deduction because my PAN became 'Inoperative' for missing the Aadhaar linking deadline. I just paid the ₹1,000 late fee under Section 234H on the portal. How long before my PAN becomes active, and how do I get my company to refund the excess 20% TDS?":
  - Response states the reactivation timeline (~30 days from date of linking request under CBDT Circular 03/2023 / Rule 114AAA).
  - Response explains that the employer cannot refund excess TDS via payroll once deposited under Section 206AA, and the taxpayer must claim credit/refund by filing an ITR after PAN is operative.
  - Response addresses both sub-questions directly rather than outputting a generic procedural checklist.

### Automated Tests and Regression Suite
- [ ] Automated regression and unit tests covering Case 1 and Case 2 are added to the repository test suite and pass.
- [ ] Tests verify that relevance and confidence gating correctly prevents HIGH confidence badges and triggers CRAG or honest refusal when retrieved chunks lack semantic alignment with query terms.
- [ ] Tests verify that multi-part queries are decomposed and answered across all distinct sub-questions.
