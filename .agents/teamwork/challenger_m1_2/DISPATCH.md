# Task Assignment: Challenger M1-2 - Adversarial Verification of M1

## Mission
Adversarially challenge the EPFO corpus remediation (R1) and vector search integrity.
Files to challenge:
- `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl`
- Qdrant collection `govbank_chunks`

## Adversarial Focus
1. Test EPFO passbook/cheque retrieval:
   - Run queries asking about cancelled cheque leaf rejection ("pre-printed name missing", "Form 19 rejection", "cancelled cheque stamp").
   - Verify that `epfo_claim_passbook_cheque_standards_01` is retrieved in top hits with valid score and official circular URL.
2. Test cross-domain bleed resistance:
   - Challenge with corporate name reservation queries (SPICe+ Part A Rule 8A) to ensure `epfo_claim_passbook_cheque_standards_01` is NOT erroneously boosted.
3. Verify vector DB integrity:
   - Check point count (1387), embedding dimension (384), and distance metric (Cosine).
4. Render verdict: `APPROVE` or `REQUEST_CHANGES`.
5. Write your complete handoff report to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m1_2\handoff.md`.

## 2026-11-04T14:24:45Z
You are challenger_m1_2, an adversarial verifier (teamwork_challenger).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m1_2
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read:
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\worker_m1\handoff.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m1_2\DISPATCH.md

Empirically verify and stress-test the EPFO corpus document retrieval and vector database integrity.
Render your verdict (APPROVE / REQUEST_CHANGES) in:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\challenger_m1_2\handoff.md
When done, notify me via send_message.

