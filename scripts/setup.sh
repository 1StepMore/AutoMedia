#!/usr/bin/env bash
# AutoMedia development environment setup script.
# Usage: bash scripts/setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== AutoMedia Setup ==="

# ---- Python version check ----
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Install Python 3.11+ first."
    exit 1
fi

PY_VER=$("$PYTHON" --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "ERROR: Python 3.11+ required, found $PY_VER"
    exit 1
fi
echo "✓ Python $PY_VER"

# ---- Virtual environment ----
if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
echo "✓ Virtual environment activated"

# ---- Install package ----
echo "Installing AutoMedia with dev dependencies..."
pip install -e ".[dev]" --quiet
echo "✓ Package installed"

# ---- Initialize config ----
echo "Initializing AutoMedia configuration..."
automedia init --template minimal 2>/dev/null || true
echo "✓ Configuration initialized"

# ---- Health check ----
echo "Running health check..."
automedia doctor || true

echo ""
echo "=== Setup Complete ==="
echo "Activate the environment: source .venv/bin/activate"
