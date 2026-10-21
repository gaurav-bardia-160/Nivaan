@echo off
title GovBank Assistant Launcher
echo ==========================================================
echo  Starting GovBank Assistant Full-Stack System...
echo ==========================================================

set PYTHONIOENCODING=utf-8
set RAG_ENABLED=true
set RAG_VECTOR_ENABLED=true
set TRANSLATION_ENABLED=true

echo [1/3] Starting Frontend static server on port 5500...
start /B py -m http.server 5500 --directory frontend >nul 2>&1

echo [2/3] Opening Web App in default browser...
start http://127.0.0.1:5500

echo [3/3] Starting Backend API on http://127.0.0.1:8000 (Ctrl+C to stop)...
echo Swagger Docs: http://127.0.0.1:8000/docs
echo Health Check: http://127.0.0.1:8000/api/health
echo Metrics API:  http://127.0.0.1:8000/api/metrics
echo ----------------------------------------------------------

py -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
