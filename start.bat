@echo off
setlocal enabledelayedexpansion

title Nivaan - Launcher
cd /d "%~dp0"

echo =====================================================================
echo    Nivaan - Full-Stack Launcher (Backend + Ollama AI)
echo =====================================================================
echo.

rem --- 1. Detect Python executable ---
set "PY_CMD="
if not "%PYTHON%"=="" (
    set "PY_CMD=%PYTHON%"
) else (
    py -3.11 --version >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=py -3.11"
    ) else (
        where py >nul 2>nul
        if !errorlevel! equ 0 (
            set "PY_CMD=py"
        ) else (
            where python3.11 >nul 2>nul
            if !errorlevel! equ 0 (
                set "PY_CMD=python3.11"
            ) else (
                where python >nul 2>nul
                if !errorlevel! equ 0 (
                    set "PY_CMD=python"
                ) else (
                    where python3 >nul 2>nul
                    if !errorlevel! equ 0 set "PY_CMD=python3"
                )
            )
        )
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python 3.11+ was not found in your system PATH.
    echo Please install Python 3.11+ from https://www.python.org/
    pause
    exit /b 1
)

rem --- 2. Activate virtual environment if present ---
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment: venv
    call venv\Scripts\activate.bat
)
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment: .venv
    call .venv\Scripts\activate.bat
)

rem --- 2.1 Verify Python Dependencies ---
%PY_CMD% -c "import backend.main" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INFO] Verifying and installing required dependencies...
    if exist "requirements.txt" (
        %PY_CMD% -m pip install -r requirements.txt
    ) else if exist "backend\requirements.txt" (
        %PY_CMD% -m pip install -r backend\requirements.txt
    )
)

rem --- 3. Configure Environment Variables ---
set PYTHONIOENCODING=utf-8
set RAG_ENABLED=true
set RAG_VECTOR_ENABLED=true
set TRANSLATION_ENABLED=true
set LOCAL_LLM_ENABLED=true
set LOCAL_LLM_PROVIDER=ollama_compatible
set LOCAL_LLM_MODEL=qwen2.5:3b
set LOCAL_LLM_BASE_URL=http://127.0.0.1:11434
set LOCAL_LLM_NUM_CTX=3072
set LOCAL_LLM_NUM_PREDICT=384
set LOCAL_LLM_TIMEOUT_SECONDS=90
set HOST=0.0.0.0
set PORT=8000
set "LAN_IP=127.0.0.1"
for /f "delims=" %%i in ('%PY_CMD% -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 53)); print(s.getsockname()[0]); s.close()" 2^>nul') do (
    set "LAN_IP=%%i"
)

rem --- 4. Locate and Launch Ollama Local AI Server ---
echo [1/4] Checking Ollama Local AI Server and Preloading Model...
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

set "OLLAMA_EXE=%APP_DIR%\ollama\ollama.exe"
if not exist "%OLLAMA_EXE%" (
    where ollama >nul 2>nul
    if !errorlevel! equ 0 (
        set "OLLAMA_EXE=ollama"
    ) else (
        set "OLLAMA_EXE="
    )
)

if not defined OLLAMA_EXE (
    echo [WARNING] ollama.exe not found. Proceeding with heuristic and RAG fallbacks.
    goto :check_vector
)

set "OLLAMA_MODELS=%APP_DIR%\models"
set "OLLAMA_HOST=127.0.0.1:11434"
set "OLLAMA_NO_CLOUD=1"
if not exist "%APP_DIR%\models" mkdir "%APP_DIR%\models"

netstat -ano | findstr ":11434" | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [INFO] Ollama server is already active on port 11434.
) else (
    echo [INFO] Starting Ollama local server daemon...
    if exist "%APP_DIR%\start_ollama.bat" (
        start "Nivaan - Ollama AI Daemon" /MIN "%APP_DIR%\start_ollama.bat"
    ) else (
        start "Nivaan - Ollama AI Daemon" /MIN "%OLLAMA_EXE%" serve
    )

    rem Wait up to 15 seconds for Ollama server to bind port 11434
    set "OLLAMA_READY=0"
    for /l %%i in (1,1,15) do (
        if !OLLAMA_READY! equ 0 (
            ping -n 2 127.0.0.1 >nul
            netstat -ano | findstr ":11434" | findstr "LISTENING" >nul 2>&1
            if !errorlevel! equ 0 set "OLLAMA_READY=1"
        )
    )
    if !OLLAMA_READY! equ 1 (
        echo [INFO] Ollama server is active and listening on port 11434.
    ) else (
        echo [WARNING] Ollama server did not bind port 11434 in time.
    )
)

rem Explicitly load qwen2.5:3b into RAM/VRAM with keep_alive=-1
%PY_CMD% -m backend.offline.preload_model %LOCAL_LLM_MODEL%

:check_vector
rem --- 5. Verify Unified Vector Index Readiness ---
echo.
echo [2/4] Verifying Qdrant Vector Index Readiness - 1,521 canonical documents...
%PY_CMD% -m backend.offline.ensure_vector_db --check-only >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] Vector index initializing...
    %PY_CMD% -m backend.offline.ensure_vector_db
) else (
    echo [INFO] Vector database verified and healthy.
)

rem --- 6. Launch Frontend Static Server (Port 5500) ---
echo.
echo [3/4] Checking Frontend Static Server on port 5500...
netstat -ano | findstr ":5500" | findstr "LISTENING" >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] Starting Frontend Web Server on http://127.0.0.1:5500...
    start "Nivaan - Frontend Server" /MIN %PY_CMD% -m http.server 5500 --bind 0.0.0.0 --directory frontend
    ping -n 2 127.0.0.1 >nul
) else (
    echo [INFO] Frontend server is already active on port 5500.
)

rem --- 7. Start FastAPI Backend Server with Uvicorn ---
echo.
echo [4/4] Starting FastAPI Backend API Server on http://%HOST%:%PORT%...
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [INFO] Backend server is already active on port %PORT%.
) else (
    echo [INFO] Launching FastAPI Backend Server...
    start "Nivaan - Backend Server" /MIN %PY_CMD% -m uvicorn backend.main:app --host %HOST% --port %PORT%

    rem Wait up to 20 seconds for backend to bind port %PORT%
    set "BACKEND_READY=0"
    for /l %%i in (1,1,20) do (
        if !BACKEND_READY! equ 0 (
            ping -n 2 127.0.0.1 >nul
            netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
            if !errorlevel! equ 0 set "BACKEND_READY=1"
        )
    )
    if !BACKEND_READY! equ 1 (
        echo [INFO] Backend API server is active and listening on port %PORT%.
    ) else (
        echo [WARNING] Backend API server did not bind port %PORT% in time.
    )
)

echo =====================================================================
echo  Nivaan Civic and Banking Assistant is Live!
echo  - Citizen Web UI (PC):    http://127.0.0.1:5500
echo  - Citizen Web UI (Mobile):http://%LAN_IP%:5500 (Use on phone connected to hotspot)
echo  - API Swagger UI: http://%HOST%:%PORT%/docs
echo  - System Health:  http://%HOST%:%PORT%/api/health
echo  - Ollama AI LLM:  http://127.0.0.1:11434 [Model: %LOCAL_LLM_MODEL%]
echo =====================================================================
echo  To cleanly stop all servers, run stop.bat or close this window.
echo =====================================================================
echo.

rem Open browser automatically after backend is confirmed ready
start "" http://127.0.0.1:5500
