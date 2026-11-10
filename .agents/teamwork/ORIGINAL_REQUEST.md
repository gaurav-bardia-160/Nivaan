# Original User Request

## Initial Request — 2026-11-09T11:53:25Z

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
