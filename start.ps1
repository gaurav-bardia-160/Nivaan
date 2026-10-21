# GovBank Assistant - Single Launch Script (PowerShell)
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Starting GovBank Assistant Full-Stack System..." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

$env:PYTHONIOENCODING = "utf-8"
$env:RAG_ENABLED = "true"
$env:RAG_VECTOR_ENABLED = "true"
$env:TRANSLATION_ENABLED = "true"

# 1. Start Frontend Server in background on port 5500
Write-Host "[1/3] Starting Frontend static server on port 5500..." -ForegroundColor Yellow
$frontendProcess = Start-Process -FilePath "py" -ArgumentList "-m http.server 5500 --directory frontend" -PassThru -WindowStyle Hidden

# 2. Open Web Browser
Write-Host "[2/3] Opening Web App in default browser..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:5500"

# 3. Start Backend Server on port 8000
Write-Host "[3/3] Starting Backend API on http://127.0.0.1:8000 (Ctrl+C to stop)..." -ForegroundColor Green
Write-Host "Swagger Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "Health Check: http://127.0.0.1:8000/api/health" -ForegroundColor Cyan
Write-Host "Metrics API:  http://127.0.0.1:8000/api/metrics" -ForegroundColor Cyan
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray

try {
    py -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
} finally {
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
