# start-redis.ps1 — Start Redis server (Windows)
# Redis lives at: <project_root>\Redis\redis-server.exe

$projectRoot = Split-Path $PSScriptRoot -Parent
$redisExe    = Join-Path $projectRoot "Redis\redis-server.exe"

if (-not (Test-Path $redisExe)) {
    Write-Host "[ERROR] Redis not found at: $redisExe"
    Write-Host "        Run the setup steps in README.md first."
    exit 1
}

# Check if already running
$running = Get-NetTCPConnection -State Listen -LocalPort 6379 -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "[Redis] Already running on port 6379"
    exit 0
}

Write-Host "[Redis] Starting on port 6379..."
Start-Process -FilePath $redisExe -ArgumentList "--port 6379 --loglevel notice" -WindowStyle Normal
Start-Sleep -Seconds 2

$cli = Join-Path $projectRoot "Redis\redis-cli.exe"
$pong = & $cli -p 6379 ping 2>&1
if ($pong -eq "PONG") {
    Write-Host "[Redis] Ready — PONG received"
} else {
    Write-Host "[Redis] WARNING: did not receive PONG. Check the Redis window."
}
