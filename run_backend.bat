@echo off
setlocal enabledelayedexpansion
title GovBank Assistant - Backend Server

:: Ensure we run in the repository root directory
cd /d "%~dp0"

echo ==========================================================
echo  GovBank Assistant - Starting Backend API Server (Windows)
echo ==========================================================
echo.

:: 1. Detect Python executable (py, python, or python3)
set "PY_CMD="
where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=py"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PY_CMD=python"
    ) else (
        where python3 >nul 2>nul
        if %errorlevel% equ 0 (
            set "PY_CMD=python3"
        )
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python was not found in your system PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    echo Remember to check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [INFO] Detected Python command: %PY_CMD%

:: 2. Auto-activate virtual environment if present
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment (venv)...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment (.venv)...
    call .venv\Scripts\activate.bat
)

:: 3. Export default environment variables
set PYTHONIOENCODING=utf-8
if "%RAG_ENABLED%"=="" set RAG_ENABLED=true
if "%RAG_VECTOR_ENABLED%"=="" set RAG_VECTOR_ENABLED=true
if "%TRANSLATION_ENABLED%"=="" set TRANSLATION_ENABLED=true
if "%HOST%"=="" set HOST=127.0.0.1
if "%PORT%"=="" set PORT=8000

echo [INFO] Configuration:
echo        - Host: %HOST%
echo        - Port: %PORT%
echo        - Hybrid RAG: %RAG_ENABLED%
echo        - Qdrant Vector Store: %RAG_VECTOR_ENABLED%
echo        - Indic Translation: %TRANSLATION_ENABLED%
echo.

:: 4. Verify backend module dependencies
%PY_CMD% -c "import backend.main" >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Dependencies may be missing. Installing from requirements...
    if exist "backend\requirements.txt" (
        %PY_CMD% -m pip install -r backend\requirements.txt
    ) else if exist "requirements.txt" (
        %PY_CMD% -m pip install -r requirements.txt
    )
)

echo ==========================================================
echo  Backend Server Running!
echo  - API Root:      http://%HOST%:%PORT%/
echo  - Swagger Docs:  http://%HOST%:%PORT%/docs
echo  - ReDoc:         http://%HOST%:%PORT%/redoc
echo  - Health Check:  http://%HOST%:%PORT%/api/health
echo  - Metrics:       http://%HOST%:%PORT%/api/metrics
echo ==========================================================
echo Press Ctrl+C to stop the server.
echo.

%PY_CMD% -m uvicorn backend.main:app --host %HOST% --port %PORT% --reload

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Backend server stopped unexpectedly with code %errorlevel%.
    pause
)
