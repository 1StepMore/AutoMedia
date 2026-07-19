#!/bin/bash
# Healthcheck for AutoMedia MCP server
# Returns 0 if healthy, 1 if unhealthy
#
# Uses a two-phase check:
#   1. Fast pgrep pre-check — process must exist
#   2. Real MCP ping — server must respond to JSON-RPC ping

set -e

# ---------------------------------------------------------------------------
# Phase 1: Fast pre-check — is the process alive?
# ---------------------------------------------------------------------------
if ! pgrep -f "automedia.mcp.server" > /dev/null 2>&1; then
    echo "CRITICAL: automedia-mcp is not running"
    exit 1
fi

# ---------------------------------------------------------------------------
# Phase 2: Real MCP ping — is the server responsive?
# ---------------------------------------------------------------------------
# Send a JSON-RPC ping request via stdin.  If the server responds with a
# valid result the server is healthy.  The `timeout` prevents a hung
# server from blocking the healthcheck forever.
RESPONSE=$(echo '{"jsonrpc":"2.0","method":"ping","id":1}' \
    | timeout 5 python -m automedia.mcp.server 2>/dev/null \
    | head -1)

if echo "$RESPONSE" | grep -q '"result"'; then
    echo "OK: automedia-mcp is running"
    exit 0
else
    echo "CRITICAL: automedia-mcp is not responding"
    exit 1
fi
