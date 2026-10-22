@echo off
setlocal enabledelayedexpansion
title GovBank Assistant Launcher
cd /d "%~dp0"

echo ==========================================================
echo  Starting GovBank Assistant Full-Stack System...
echo ==========================================================

set "PY_CMD="
where py >nul 2>nul
if !errorlevel! equ 0 (
    set "PY_CMD=py"
) else (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=python"
    ) else (
        where python3 >nul 2>nul
        if !errorlevel! equ 0 set "PY_CMD=python3"
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python 3.10+ was not found in PATH.
    echo Install Python from https://www.python.org/ and try again.
    pause
    exit /b 1
)

if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat
if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

set PYTHONIOENCODING=utf-8
set RAG_ENABLED=true
set RAG_VECTOR_ENABLED=true
set TRANSLATION_ENABLED=true

%PY_CMD% -c "import backend.main" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INFO] Installing project dependencies...
    %PY_CMD% -m pip install -r requirements.txt
    if !errorlevel! neq 0 exit /b 1
)

echo [1/3] Starting Frontend static server on port 5500...
start "GovBank Frontend" /B %PY_CMD% -m http.server 5500 --directory frontend >nul 2>&1

echo [2/3] Opening Web App in default browser...
start "" http://127.0.0.1:5500

echo [3/3] Starting Backend API on http://127.0.0.1:8000 (Ctrl+C to stop)...
echo Swagger Docs: http://127.0.0.1:8000/docs
echo Health Check: http://127.0.0.1:8000/api/health
echo Metrics API:  http://127.0.0.1:8000/api/metrics
echo ----------------------------------------------------------

%PY_CMD% -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

if !errorlevel! neq 0 (
    echo [ERROR] Backend server stopped unexpectedly.
    pause
    exit /b !errorlevel!
)
