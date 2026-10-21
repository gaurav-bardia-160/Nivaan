# GovBank Assistant - Privacy & Data Protection Policy

**Last Updated:** October 2026  
**Compliance Standard:** Digital Personal Data Protection Act (DPDP Act 2023), India

---

## 1. Core Privacy Commitments

GovBank Assistant is designed with **Privacy-by-Design** and **Zero-Data-Retention** principles for sensitive citizen data:

1. **Client-Side Masking Before Persistence:**  
   Before any message is saved into browser `localStorage`, high-precision client-side regular expressions redact sensitive identifiers including:
   - **Aadhaar Numbers:** 12-digit numbers formatted as `[AADHAAR]`
   - **Permanent Account Numbers (PAN):** 10-character alphanumeric strings formatted as `[PAN]`
   - **Mobile Phone Numbers:** 10-digit numbers (with optional +91 prefix) formatted as `[PHONE]`
   - **Bank Account Numbers:** Account numbers matching 9-18 digits formatted as `[BANK_ACCOUNT]`
   - **IFSC Codes:** Bank routing codes formatted as `[IFSC]`
   - **Email Addresses:** Standard email patterns formatted as `[EMAIL]`

2. **Server-Side Dual Masking Guardrails:**  
   When requests reach the FastAPI backend, an independent second-tier regex guardrail (`backend/modules/guardrails.py`) sanitizes both questions and document text before query routing or RAG retrieval occurs.

3. **Zero Storage of Uploaded Files:**  
   Uploaded documents (`.pdf`, `.txt`, `.csv`) processed via `/api/ask-file` are read in-memory into temporary byte buffers and discarded immediately after text extraction. Files are **never saved to disk**, persistent storage, or third-party cloud buckets.

4. **Transparent Redaction Badges:**  
   Whenever a sensitive token is detected and masked, the user is presented with a prominent badge in the assistant bubble:  
   `🛡️ Protected Sensitive Data: Redacted [ITEM] before processing.`

---

## 2. Conversation Storage & Clearing

- Chat transcripts are stored purely in the user's local browser memory (`window.localStorage`).
- Users can delete individual conversations or clear all chat history at any time using the "Delete" button in the sidebar.
- No user tracking cookies or third-party advertising SDKs are included.

---

## 3. Data Processing Boundary

GovBank Assistant operates as a stateless procedural guidance engine:
- User queries are mapped to verified civic guides or open government knowledge sources.
- The assistant refuses out-of-scope personal inquiries and instructs users to confirm final filings on the official government portal (`india.gov.in`, `incometax.gov.in`, `passportindia.gov.in`, etc.).
