# ==============================================================================
# GovBank Assistant - Backend Server Runner (PowerShell for Windows)
# ==============================================================================
[CmdletBinding()]
param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " GovBank Assistant - Starting Backend API Server (Windows)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Detect Python executable
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

# 2. Auto-activate virtual environment if present
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (venv)..." -ForegroundColor Yellow
    & "venv\Scripts\Activate.ps1"
} elseif (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (.venv)..." -ForegroundColor Yellow
    & ".venv\Scripts\Activate.ps1"
}

# 3. Export required environment variables
$env:PYTHONIOENCODING = "utf-8"
$env:RAG_ENABLED = "true"
$env:RAG_VECTOR_ENABLED = "true"
$env:TRANSLATION_ENABLED = "true"

Write-Host "[INFO] Configuration:" -ForegroundColor Yellow
Write-Host "       - Host: $HostAddress"
Write-Host "       - Port: $Port"
Write-Host "       - Hybrid RAG: $env:RAG_ENABLED"
Write-Host "       - Qdrant Vector Store: $env:RAG_VECTOR_ENABLED"
Write-Host "       - Indic Translation: $env:TRANSLATION_ENABLED"
Write-Host ""

# 4. Verify backend module dependencies
& $pyCmd -c "import backend.main" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] Dependencies may be missing. Installing from requirements..." -ForegroundColor Yellow
    if (Test-Path "backend\requirements.txt") {
        & $pyCmd -m pip install -r backend\requirements.txt
    } elseif (Test-Path "requirements.txt") {
        & $pyCmd -m pip install -r requirements.txt
    }
}

if ($env:RAG_VECTOR_ENABLED -eq "true") {
    Write-Host "[INFO] Checking local vector index readiness..." -ForegroundColor Yellow
    & $pyCmd -m backend.offline.ensure_vector_db
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARNING] Vector index unavailable. Continuing with lexical RAG fallback." -ForegroundColor Yellow
    }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Backend Server Running!" -ForegroundColor Green
Write-Host " - API Root:      http://$HostAddress`:$Port/" -ForegroundColor Cyan
Write-Host " - Swagger Docs:  http://$HostAddress`:$Port/docs" -ForegroundColor Cyan
Write-Host " - ReDoc:         http://$HostAddress`:$Port/redoc" -ForegroundColor Cyan
Write-Host " - Health Check:  http://$HostAddress`:$Port/api/health" -ForegroundColor Cyan
Write-Host " - Metrics:       http://$HostAddress`:$Port/api/metrics" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host ""

& $pyCmd -m uvicorn backend.main:app --host $HostAddress --port $Port --reload
