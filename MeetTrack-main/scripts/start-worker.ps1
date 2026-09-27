# start-worker.ps1 — Start Celery worker (background task queue)
# Requires Redis to be running first (run start-redis.ps1)

$projectRoot = Split-Path $PSScriptRoot -Parent
$venvPy      = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "[ERROR] Virtual environment not found."
    exit 1
}

# Check Redis is reachable
$redisCli = Join-Path $projectRoot "Redis\redis-cli.exe"
if (Test-Path $redisCli) {
    $pong = & $redisCli -p 6379 ping 2>&1
    if ($pong -ne "PONG") {
        Write-Host "[ERROR] Redis is not running. Start it first:"
        Write-Host "        .\scripts\start-redis.ps1"
        exit 1
    }
}

Write-Host "[Worker] Starting Celery worker..."
Write-Host "         Queues: transcription, ai_extraction, email_delivery, analytics, webhooks"
Write-Host "         Press Ctrl+C to stop"
Write-Host ""

Set-Location $projectRoot
$env:PYTHONPATH = $projectRoot

& $venvPy -m celery -A backend.worker.celery_app worker `
    -Q transcription,ai_extraction,email_delivery,analytics,webhooks `
    --loglevel=info `
    --concurrency=2 `
    --pool=solo        # solo pool works on Windows (no fork support)
