@echo off
setlocal
cd /d "%~dp0"
set OLLAMA_MODELS=%~dp0models
if not exist "%~dp0models" mkdir "%~dp0models"

set OLLAMA_EXE=%~dp0ollama\ollama.exe
if not exist "%OLLAMA_EXE%" (
    where ollama >nul 2>&1
    if %errorlevel% equ 0 (
        set OLLAMA_EXE=ollama
    ) else (
        echo [ERROR] ollama.exe not found in "%~dp0ollama" or system PATH.
        exit /b 1
    )
)

echo ========================================================
echo  Starting Ollama Local AI Server for GovBank Assistant
echo  Binary: %OLLAMA_EXE%
echo  Models Directory: %OLLAMA_MODELS%
echo ========================================================
"%OLLAMA_EXE%" serve
