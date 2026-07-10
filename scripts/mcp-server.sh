#!/usr/bin/env bash
# AutoMedia MCP Server launcher (stdio transport).
# Usage: bash scripts/mcp-server.sh [--show-tools]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ "${1:-}" = "--show-tools" ]; then
    python -m automedia.mcp.server --show-tools
    exit 0
fi

echo "Starting AutoMedia MCP Server (stdio transport)..."
echo "PID: $$"
echo ""

# Handle SIGTERM gracefully
cleanup() {
    echo ""
    echo "Shutting down MCP server..."
    exit 0
}
trap cleanup SIGTERM SIGINT

python -m automedia.mcp.server
