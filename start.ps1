# ==============================================================================
# GovBank Assistant - Full-Stack Application Launcher (PowerShell for Windows)
# ==============================================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Starting GovBank Assistant Full-Stack System...         " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

$pyCmd = $null
if ($env:PYTHON) {
    $pyCmd = $env:PYTHON
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $has311 = & py -3.11 -c "import sys; print(sys.version_info.major)" 2>$null
    if ($has311 -eq "3") {
        $pyCmd = "py -3.11"
    } else {
        $pyCmd = "py"
    }
} elseif (Get-Command python3.11 -ErrorAction SilentlyContinue) {
    $pyCmd = "python3.11"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pyCmd = "python3"
} else {
    Write-Host "[ERROR] Python was not found in your system PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.11+ from https://www.python.org/" -ForegroundColor Yellow
    exit 1
}

$pyVer = & $pyCmd --version 2>&1
Write-Host "[INFO] Detected Python: $pyVer" -ForegroundColor Yellow

if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
} elseif (Test-Path ".venv\Scripts\Activate.ps1") {
    & ".venv\Scripts\Activate.ps1"
}

$env:PYTHONIOENCODING = "utf-8"
$env:RAG_ENABLED = "true"
$env:RAG_VECTOR_ENABLED = "true"
$env:TRANSLATION_ENABLED = "true"

& $pyCmd -c "import backend.main" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] Installing project dependencies..." -ForegroundColor Yellow
    & $pyCmd -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }
}

Write-Host "[0/4] Checking local vector index readiness..." -ForegroundColor Yellow
& $pyCmd -m backend.offline.ensure_vector_db
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] Vector index unavailable. Continuing with lexical RAG fallback." -ForegroundColor Yellow
}

$ollamaListening = Get-NetTCPConnection -LocalPort 11434 -ErrorAction SilentlyContinue
if (-not $ollamaListening -and (Test-Path "start_ollama.bat")) {
    Write-Host "[1/4] Starting Local Ollama AI Server..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c start_ollama.bat" -WindowStyle Hidden
}

# 2. Start Frontend Server in background on port 5500
Write-Host "[2/4] Starting Frontend static server on port 5500..." -ForegroundColor Yellow
$frontendProcess = Start-Process -FilePath $pyCmd -ArgumentList "-m http.server 5500 --directory frontend" -PassThru -WindowStyle Hidden

# 3. Open Web Browser
Write-Host "[3/4] Opening Web App in default browser..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:5500"

# 4. Start Backend Server on port 8000
Write-Host "[4/4] Starting Backend API on http://127.0.0.1:8000 (Ctrl+C to stop)..." -ForegroundColor Green
Write-Host "Swagger Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "Health Check: http://127.0.0.1:8000/api/health" -ForegroundColor Cyan
Write-Host "Metrics API:  http://127.0.0.1:8000/api/metrics" -ForegroundColor Cyan
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray

try {
    & $pyCmd -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
} finally {
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
