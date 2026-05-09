# Solar Load Controller - Startup Script
# Usage: .\start.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ProjectRoot
try {
    # Create virtual environment if missing
    if (-not (Test-Path ".venv")) {
        Write-Host "[1/3] Creating virtual environment..." -ForegroundColor Cyan
        python -m venv .venv
    } else {
        Write-Host "[1/3] Virtual environment found" -ForegroundColor Green
    }

    # Activate venv
    & .\.venv\Scripts\Activate.ps1

    # Install / update dependencies
    Write-Host "[2/3] Installing dependencies..." -ForegroundColor Cyan
    pip install -q -r requirements.txt

    # Check .env
    if (-not (Test-Path ".env")) {
        Write-Host "[WARN] .env file not found — copy .env.example and fill in credentials" -ForegroundColor Yellow
    }

    # Start
    Write-Host "[3/3] Starting Solar Load Controller..." -ForegroundColor Cyan
    python run.py
} finally {
    Pop-Location
}
