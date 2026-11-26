"""`automedia mcp discover` must not hand out a configuration that cannot start (#702).

`mcp` lives in its own extra, so a Text-tier install (``.[openai,rich]``) has no
MCP server. The command used to print a perfectly valid-looking config pointing at
``sys.executable -m automedia.mcp.server``, and the agent then watched the server
die on import with ``ModuleNotFoundError: No module named 'mcp'``.

These cases pin both halves: refuse + explain when the SDK is absent, and keep the
normal output when it is present.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


@pytest.fixture()
def without_mcp_sdk(monkeypatch):
    monkeypatch.setattr("automedia.cli.commands.mcp._mcp_sdk_available", lambda: False)


def test_discover_refuses_when_sdk_missing(without_mcp_sdk):
    result = runner.invoke(app, ["mcp", "discover", "--client", "claude"])

    assert result.exit_code == 1, result.output
    assert ".[mcp]" in result.output, result.output
    assert "ModuleNotFoundError" in result.output, result.output
    # The point of the guard: no copy-pasteable config is emitted.
    assert "mcpServers" not in result.output, result.output


def test_bare_mcp_also_refuses_when_sdk_missing(without_mcp_sdk):
    """`automedia mcp` delegates to discover; it must not fake success either."""
    result = runner.invoke(app, ["mcp"])

    assert result.exit_code == 1, result.output
    assert ".[mcp]" in result.output, result.output


def test_discover_prints_config_when_sdk_available():
    pytest.importorskip("mcp", reason="dev environment installs the [dev] extra")

    result = runner.invoke(app, ["mcp", "discover", "--client", "claude"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    server = payload["config"]["mcpServers"]["automedia"]
    assert server["args"] == ["-m", "automedia.mcp.server"]
    assert server["command"]
