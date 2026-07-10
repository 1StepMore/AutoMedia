#!/usr/bin/env bash
# AutoMedia test runner with coverage.
# Usage: bash scripts/run-tests.sh [pytest-args...]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== AutoMedia Test Suite ==="
echo "Args: $*"
echo ""

python -m pytest --cov=src/automedia -v "$@"
