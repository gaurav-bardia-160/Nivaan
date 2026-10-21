# GovBank Assistant - Security Architecture & Threat Model

**Version:** 0.4.0  
**Target Architecture:** Hardened civic assistance gateway

---

## 1. Threat Mitigation Matrix

| Threat Category | Potential Attack Vector | Applied Mitigation |
| :--- | :--- | :--- |
| **Data Leakage (PII)** | Aadhaar/PAN written to storage or logs | Dual-tier client & server masking (`maskClientPII`, `backend/modules/guardrails.py`) |
| **Denial of Service (DoS)** | Automated request flooding | In-memory sliding-window rate limiter (default 120 req/min per IP, HTTP 429 response) |
| **Cross-Origin Abuse** | Malicious scripts calling API | Dynamic CORS middleware restricting origins via `CORS_ORIGINS` environment variable |
| **Unauthorized Access** | Unauthenticated production calls | Optional API Key enforcement via `API_KEY` header (`X-API-Key` or `Authorization: Bearer`) |
| **Prompt Injection** | Jailbreaks attempting false tax/legal advice | Deterministic verified-first procedure routing with strict out-of-scope refusal |
| **Malicious File Upload** | Buffer overflow / zip bombs / corrupted PDFs | Strict file size ceiling (2 MB limit), timeout-protected `pdfplumber` parsing, no disk writes |

---

## 2. API Security Configuration

### Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `API_KEY` | *(empty - open demo mode)* | Sets mandatory secret key required in `X-API-Key` or `Bearer` header |
| `RATE_LIMIT_ENABLED` | `true` | Enables/disables IP-based sliding window rate limiting |
| `RATE_LIMIT_RPM` | `120` | Maximum requests permitted per minute per client IP |
| `CORS_ORIGINS` | `*` *(local)* | Comma-separated list of allowed origins (e.g., `https://govbank.app`) |
| `TRANSLATION_ENABLED`| `false` | Enables multilingual translation to Hindi/Gujarati |
| `RAG_ENABLED` | `false` | Enables hybrid BM25 + Qdrant civic knowledge retrieval |

---

## 3. Monitoring & Telemetry

Production monitoring is exposed via the `/api/metrics` endpoint:
- Uptime seconds
- Total / successful / failed requests
- Active rate-limited client count
- RAG retrieval vs. curated procedure hit ratios
- Engine availability flags (Qdrant, OCR, Translation)
