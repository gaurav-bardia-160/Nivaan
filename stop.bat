@echo off
setlocal enabledelayedexpansion
title Nivaan - Shutdown
cd /d "%~dp0"

echo =====================================================================
echo    Nivaan - Stopping Backend, Ollama LLM, and Frontend
echo =====================================================================
echo.

rem Close launcher windows first
taskkill /F /FI "WINDOWTITLE eq Nivaan - Launcher*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Nivaan - Frontend Server*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Nivaan - Backend Server*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Nivaan - Ollama AI Daemon*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq GovBank Assistant - Launcher*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq GovBank Assistant - Frontend Server*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq GovBank Assistant - Backend Server*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq GovBank Assistant - Ollama AI Daemon*" >nul 2>&1

rem --- 1. Terminate FastAPI Backend Server (Port 8000) ---
echo [1/3] Terminating Backend Server on port 8000...
set "FOUND_BACKEND=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    set "PID=%%a"
    if "!PID!" neq "0" (
        taskkill /F /T /PID !PID! >nul 2>&1
        set "FOUND_BACKEND=1"
    )
)
rem Kill any backend python instances strictly matching python/py executable names
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like '*python*' -or $_.Name -like '*py*') -and ($_.CommandLine -like '*backend.main:app*' -or $_.CommandLine -like '*uvicorn*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

if !FOUND_BACKEND! equ 1 (
    echo [INFO] Backend server terminated cleanly.
) else (
    echo [INFO] No active backend server found on port 8000.
)

rem --- 2. Terminate Ollama Local AI Server (Port 11434 & processes) ---
echo.
echo [2/3] Terminating Ollama Local AI Server...
set "FOUND_OLLAMA=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":11434" ^| findstr "LISTENING"') do (
    set "PID=%%a"
    if "!PID!" neq "0" (
        taskkill /F /T /PID !PID! >nul 2>&1
        set "FOUND_OLLAMA=1"
    )
)
taskkill /F /T /IM ollama.exe >nul 2>&1
if !errorlevel! equ 0 set "FOUND_OLLAMA=1"
taskkill /F /T /IM ollama_llama_server.exe >nul 2>&1
if !errorlevel! equ 0 set "FOUND_OLLAMA=1"
taskkill /F /T /IM llama-server.exe >nul 2>&1
if !errorlevel! equ 0 set "FOUND_OLLAMA=1"

rem Guarantee all Ollama instances are killed
powershell -NoProfile -Command "Get-Process *ollama*, *llama* -ErrorAction SilentlyContinue | Stop-Process -Force" >nul 2>&1

if !FOUND_OLLAMA! equ 1 (
    echo [INFO] Ollama AI server terminated. RAM and GPU VRAM released.
) else (
    echo [INFO] Ollama server was not running.
)

rem --- 3. Terminate Frontend Static Server (Port 5500) ---
echo.
echo [3/3] Terminating Frontend Web Server on port 5500...
set "FOUND_FRONTEND=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5500" ^| findstr "LISTENING"') do (
    set "PID=%%a"
    if "!PID!" neq "0" (
        taskkill /F /T /PID !PID! >nul 2>&1
        set "FOUND_FRONTEND=1"
    )
)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like '*python*' -or $_.Name -like '*py*') -and ($_.CommandLine -like '*http.server 5500*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

if !FOUND_FRONTEND! equ 1 (
    echo [INFO] Frontend server process terminated.
) else (
    echo [INFO] No active frontend server found on port 5500.
)

rem Verification sweep: ensure ports 8000, 11434, 5500 are completely released
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":11434" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5500" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1

echo.
echo =====================================================================
echo  Shutdown Complete!
echo  - Backend API (Port 8000):   STOPPED
echo  - Ollama LLM (Port 11434):   STOPPED
echo  - Frontend Web (Port 5500):  STOPPED
echo =====================================================================
echo.
ping -n 2 127.0.0.1 >nul
exit /b 0
