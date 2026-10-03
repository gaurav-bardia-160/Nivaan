# GovBank Assistant

> AI-powered assistant that explains Indian government, legal, and banking procedures and notices in plain language, step by step, with verified official sources.
> Prepared for the IBCP AI Conclave (Theme: Communication).

## Quick Overview

Official forms, notices, schemes, and banking guidelines are often complex and inaccessible to ordinary citizens. GovBank Assistant bridges this communication barrier by converting dense official text into:
1. **Plain-language explanation**
2. **Actionable tick-box checklist of steps**
3. **Required documents list**
4. **Deadline and risk warnings with explicit reasons**
5. **Source URLs & verification dates**
6. **Masked sensitive data notification**
7. **Informational disclaimer**

## Folder Structure

See [PROJECT_STRUCTURE.txt](file:///C:/Users/gaura/Documents/govbank-assistant/PROJECT_STRUCTURE.txt).

## Setup & Running

### 1. Python Environment
```bash
py -m venv venv
.\venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `backend/.env`:
```bash
copy .env.example backend\.env
```

### 3. Run Backend Stub
```bash
cd backend
py -m uvicorn main:app --reload --port 8000
```
Open API docs at `http://127.0.0.1:8000/docs`.

### 4. Run Frontend
Open `frontend/index.html` in your browser.
