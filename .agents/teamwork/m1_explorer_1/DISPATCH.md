# Task Assignment: M1 Explorer 1 - EPFO Corpus Remediation (R1)

## Mission
Investigate and design the exact technical implementation plan for R1 in Milestone 1:
- File to modify: `backend/data/refined/troubleshooting/troubleshooting_civic.jsonl`.
- Update `epfo_claim_passbook_cheque_standards_01` source URL from the mismatched inspector manual to the authentic EPFO circular on passbook/cheque validation (`https://www.epfindia.gov.in/site_docs/PDFs/Circulars/Y2024-2025/WSU_IssueOfBKG_49885_16.pdf` or canonical URL) and refine tags to avoid cross-domain bleed.
- Verify manifest allowlist in `backend/data/rag_manifest.json`.
- Check `tests/test_rag_loader.py` and determine whether document counts or corpus hashes need adjustments.
- Detail the exact command to rebuild and verify Qdrant vector store (`python -m backend.offline.ensure_vector_db`).
- Write complete recommendations to `c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_1\handoff.md`.

## 2026-11-04T13:34:18Z
You are m1_explorer_1, an exploration agent (teamwork_explorer).
Your working directory is: c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_1
Original Request path: c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md

Read:
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\PROJECT.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_1\DISPATCH.md
- c:\Users\gaura\Documents\nivaan\.agents\teamwork\survey_2_gen2\handoff.md

Investigate and provide concrete technical implementation details for R1 (EPFO corpus source remediation in `troubleshooting_civic.jsonl` and vector DB rebuild).
Write your complete handoff report to:
c:\Users\gaura\Documents\nivaan\.agents\teamwork\m1_explorer_1\handoff.md
When done, notify me via send_message.
