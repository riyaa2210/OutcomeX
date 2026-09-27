# start-frontend.ps1 — Start React/Vite development server

$projectRoot  = Split-Path $PSScriptRoot -Parent
$frontendDir  = Join-Path $projectRoot "frontend"
$nodeModules  = Join-Path $frontendDir "node_modules"

if (-not (Test-Path $nodeModules)) {
    Write-Host "[Frontend] node_modules not found. Installing..."
    Set-Location $frontendDir
    npm install
}

Write-Host "[Frontend] Starting Vite dev server on http://localhost:5173 ..."
Write-Host "           Press Ctrl+C to stop"
Write-Host ""

Set-Location $frontendDir
npm run dev
