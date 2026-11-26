"""Protocol-level failure signalling for MCP tool calls (issue #704).

MCP clients read ``isError`` — not ``structuredContent`` — to decide whether a
``tools/call`` failed.  A tool that returns ``{"success": false, "error": ...}``
must therefore surface as ``isError: true`` on the wire while keeping the
structured error payload.

The dispatcher wrapper in :mod:`automedia.mcp.server` is the single choke point
every call passes through, so these tests exercise it both in-process
(``FastMCP.call_tool``) and over a real stdio round trip.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from mcp.types import CallToolResult

from automedia.mcp.allowlist import _reset_allowlist_cache


@pytest.fixture()
def denied_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Point the allowlist at another directory and run from outside it.

    Since #703 the no-arg ``list_projects`` call succeeds (the default
    projects directory is allowed implicitly), so the failure trigger is an
    EXPLICIT ``base_dir`` outside the allowlist — the denial shape is the
    same structured ``Permission denied`` envelope this issue is about.
    """
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    allowlist = tmp_path / "allowlist.yaml"
    allowlist.write_text(f"allowed_directories:\n  - {allowed}\n", encoding="utf-8")

    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", str(allowlist))
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("AUTOMEDIA_POOL_DB", str(tmp_path / "missing-pool.db"))
    _reset_allowlist_cache()
    yield elsewhere
    _reset_allowlist_cache()


def _structured(raw: Any) -> dict[str, Any]:
    """Return the authoritative structured payload from a dispatcher result."""
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], dict):
        return raw[1]
    if isinstance(raw, dict):
        return raw
    structured = getattr(raw, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    raise AssertionError(f"unexpected dispatcher result shape: {raw!r}")


def test_list_projects_failure_is_an_iserror_result(denied_cwd: Path) -> None:
    """A structured failure is promoted to ``CallToolResult(isError=True)``."""
    import asyncio

    from automedia.mcp.server import create_server

    server = create_server()
    # Explicit base_dir outside the allowlist: after #703 the no-arg call
    # succeeds, so the denial trigger must be caller-supplied.
    raw = asyncio.run(server.call_tool("list_projects", {"base_dir": str(denied_cwd)}))

    assert isinstance(raw, CallToolResult), f"failure was not a protocol error: {raw!r}"
    assert raw.isError is True
    payload = _structured(raw)
    assert payload["success"] is False
    message = payload["error"]["message"]
    assert "Permission denied" in message
    assert "allowed directory" in message or "mcp_allowlist" in message


def test_help_mcp_success_keeps_the_plain_payload(denied_cwd: Path) -> None:
    """A successful tool is not wrapped and its payload is unchanged."""
    import asyncio

    from automedia.mcp.server import create_server

    server = create_server()
    raw = asyncio.run(server.call_tool("help_mcp", {}))

    assert not isinstance(raw, CallToolResult), "success was mislabelled as an error"
    payload = _structured(raw)
    assert "error" not in payload
    assert payload["tool_count"] > 0
    assert "categories" in payload and "hint" in payload


def _send(proc: subprocess.Popen[str], message: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def _read_response(
    proc: subprocess.Popen[str], request_id: int, timeout: float = 180.0
) -> dict[str, Any]:
    """Read stdout until the JSON-RPC response with *request_id* arrives."""
    assert proc.stdout is not None
    box: dict[str, Any] = {}

    def _readline() -> None:
        box["line"] = proc.stdout.readline()

    reader = threading.Thread(target=_readline, daemon=True)
    reader.start()
    reader.join(timeout)
    if reader.is_alive():
        proc.kill()
        raise AssertionError(f"timed out waiting for MCP response id={request_id}")
    line = box.get("line", "")
    if not line:
        raise AssertionError(f"MCP server closed stdout before response id={request_id}")
    message = json.loads(line)
    assert message.get("id") == request_id, f"unexpected response: {message!r}"
    return message


def test_stdio_round_trip_sets_iserror(denied_cwd: Path) -> None:
    """The wire result carries ``isError`` for a failure and not for a success."""
    env = dict(os.environ)
    proc = subprocess.Popen(
        [sys.executable, "-m", "automedia.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        # Pin the codec: on Windows text mode defaults to cp1252 and the server's
        # UTF-8 JSON-RPC stream then dies with UnicodeDecodeError (#704 CI).
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=denied_cwd,
        env=env,
    )
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "iserror-test", "version": "0"},
                },
            },
        )
        _read_response(proc, 1)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                # Explicit base_dir outside the allowlist: after #703 the
                # no-arg call succeeds, so the denial trigger must be
                # caller-supplied.
                "params": {
                    "name": "list_projects",
                    "arguments": {"base_dir": str(denied_cwd)},
                },
            },
        )
        failure = _read_response(proc, 2)["result"]
        assert failure["isError"] is True
        assert failure["structuredContent"]["success"] is False
        assert "Permission denied" in failure["structuredContent"]["error"]["message"]
        assert "Permission denied" in failure["content"][0]["text"]

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "help_mcp", "arguments": {}},
            },
        )
        success = _read_response(proc, 3)["result"]
        assert success["isError"] is False
        assert success["structuredContent"]["tool_count"] > 0
        assert "error" not in success["structuredContent"]
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            proc.kill()
            proc.wait(timeout=30)
