# start-backend.ps1 — Start FastAPI backend (uvicorn, hot-reload)
# Run from the MeetTrack-main directory or from scripts/

$projectRoot = Split-Path $PSScriptRoot -Parent
$venvPy      = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "[ERROR] Virtual environment not found."
    Write-Host "        Create it: python -m venv .venv"
    Write-Host "        Install deps: .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path (Join-Path $projectRoot ".env"))) {
    Write-Host "[ERROR] .env file not found. Copy .env.production.example → .env and fill in values."
    exit 1
}

Write-Host "[Backend] Starting FastAPI on http://127.0.0.1:8000 ..."
Write-Host "          API docs: http://127.0.0.1:8000/docs"
Write-Host "          Press Ctrl+C to stop"
Write-Host ""

Set-Location $projectRoot
$env:PYTHONPATH = $projectRoot

& $venvPy -m uvicorn backend.app.main:app `
    --reload `
    --host 127.0.0.1 `
    --port 8000 `
    --log-level info
