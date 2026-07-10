#!/bin/bash
# Healthcheck for AutoMedia MCP server
# Returns 0 if healthy, 1 if unhealthy

if pgrep -f "automedia.mcp.server" > /dev/null 2>&1; then
    echo "OK: automedia-mcp is running"
    exit 0
else
    echo "CRITICAL: automedia-mcp is not running"
    exit 1
fi
