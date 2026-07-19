<#
.SYNOPSIS
    AutoMedia development environment setup script for Windows (PowerShell).

.DESCRIPTION
    Checks for Python 3.11+, creates a virtual environment, installs
    AutoMedia with all extras, installs FFmpeg and Bun via winget and
    the official Bun install script, then runs automedia init and doctor.

.NOTES
    Run this from the repository root:
        .\scripts\setup.ps1

    If you get an execution policy error, run:
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

.EXAMPLE
    .\scripts\setup.ps1
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

Write-Host "=== AutoMedia Setup (Windows) ===" -ForegroundColor Cyan

# ---- Python version check ----
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Host "ERROR: Python not found. Install Python 3.11+ first:" -ForegroundColor Red
    Write-Host "  winget install Python.Python.3.11" -ForegroundColor Yellow
    Write-Host "Then close and reopen PowerShell, and run this script again." -ForegroundColor Yellow
    exit 1
}

$pyVersion = & $python --version 2>&1
Write-Host "Found: $pyVersion" -ForegroundColor Green

# Parse version (e.g. "Python 3.12.2")
if ($pyVersion -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        Write-Host "ERROR: Python 3.11+ required, found $major.$minor" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "ERROR: Could not parse Python version string" -ForegroundColor Red
    exit 1
}

Write-Host "`u{2713} Python $major.$minor" -ForegroundColor Green

# ---- Virtual environment ----
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    & $python -m venv .venv
}

# Activate and upgrade pip
& .\.venv\Scripts\Activate.ps1
Write-Host "`u{2713} Virtual environment activated" -ForegroundColor Green

# Upgrade pip
& python -m pip install --upgrade pip --quiet
Write-Host "`u{2713} pip upgraded" -ForegroundColor Green

# ---- Install package ----
Write-Host "Installing AutoMedia with all extras..." -ForegroundColor Cyan
& pip install -e ".[all]" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed." -ForegroundColor Red
    exit 1
}
Write-Host "`u{2713} Package installed" -ForegroundColor Green

# ---- Install FFmpeg (via winget) ----
$ffmpegCheck = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpegCheck) {
    Write-Host "Installing FFmpeg via winget..." -ForegroundColor Cyan
    & winget install "FFmpeg (Essentials Build)" --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`u{2713} FFmpeg installed" -ForegroundColor Green
        Write-Host "  You may need to close and reopen PowerShell for FFmpeg to be on PATH." -ForegroundColor Yellow
    } else {
        Write-Host "WARNING: FFmpeg installation may have failed." -ForegroundColor Yellow
        Write-Host "  Install manually: winget install `"FFmpeg (Essentials Build)`"" -ForegroundColor Yellow
    }
} else {
    Write-Host "`u{2713} FFmpeg already installed" -ForegroundColor Green
}

# ---- Install Bun (via PowerShell install script) ----
$bunCheck = Get-Command bun -ErrorAction SilentlyContinue
if (-not $bunCheck) {
    Write-Host "Installing Bun..." -ForegroundColor Cyan
    try {
        $env:BUN_INSTALL = "$env:USERPROFILE\.bun"
        & powershell -NoProfile -Command "irm https://bun.sh/install.ps1 | iex" 2>&1 | Out-Null
        # Add Bun to PATH for this session
        $env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
        Write-Host "`u{2713} Bun installed" -ForegroundColor Green
        Write-Host "  Added to PATH for this session." -ForegroundColor Yellow
        Write-Host "  To make it permanent, add $env:USERPROFILE\.bun\bin to your user PATH." -ForegroundColor Yellow
    } catch {
        Write-Host "WARNING: Bun installation failed: $_" -ForegroundColor Yellow
        Write-Host "  Install manually: powershell -c `"irm https://bun.sh/install.ps1 | iex`"" -ForegroundColor Yellow
    }
} else {
    Write-Host "`u{2713} Bun already installed" -ForegroundColor Green
}

# ---- Install edge-tts ----
Write-Host "Installing edge-tts..." -ForegroundColor Cyan
& pip install edge-tts --quiet
Write-Host "`u{2713} edge-tts installed" -ForegroundColor Green

# ---- Initialize config ----
Write-Host "Initializing AutoMedia configuration..." -ForegroundColor Cyan
try {
    & automedia init --template minimal 2>&1 | Out-Null
    Write-Host "`u{2713} Configuration initialized" -ForegroundColor Green
} catch {
    Write-Host "WARNING: automedia init failed (may already be configured): $_" -ForegroundColor Yellow
}

# ---- Health check ----
Write-Host "Running health check..." -ForegroundColor Cyan
try {
    & automedia doctor
} catch {
    Write-Host "WARNING: automedia doctor failed: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "Activate the environment: .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Set AUTOMEDIA_LLM_API_KEY environment variable" -ForegroundColor White
Write-Host "  2. Run: automedia run --topic `"Your Topic`" --brand my-brand --mode text_only" -ForegroundColor White
Write-Host "  3. For full Windows docs, see: docs/user/windows-deployment.md" -ForegroundColor White
