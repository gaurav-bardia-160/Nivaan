$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$ModelsDir = Join-Path $ProjectDir "models"
if (-not (Test-Path $ModelsDir)) {
    New-Item -ItemType Directory -Path $ModelsDir -Force | Out-Null
}

$env:OLLAMA_MODELS = $ModelsDir

$LocalOllama = Join-Path $ProjectDir "ollama\ollama.exe"
if (Test-Path $LocalOllama) {
    $OllamaExe = $LocalOllama
} elseif (Get-Command "ollama" -ErrorAction SilentlyContinue) {
    $OllamaExe = "ollama"
} else {
    Write-Host "[ERROR] ollama.exe not found in $ProjectDir\ollama or system PATH." -ForegroundColor Red
    exit 1
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Starting Ollama Local AI Server for GovBank Assistant" -ForegroundColor Cyan
Write-Host " Binary:           $OllamaExe" -ForegroundColor Cyan
Write-Host " Models Directory: $env:OLLAMA_MODELS" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

& $OllamaExe serve
