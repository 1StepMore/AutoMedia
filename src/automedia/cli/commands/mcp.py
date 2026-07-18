"""``automedia mcp discover`` — Generate MCP server configuration for various clients."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer

from automedia._version import __version__

app = typer.Typer(
    name="mcp",
    help="MCP server management commands.",
    no_args_is_help=True,
)

# The base MCP server configuration template
_BASE_CONFIG: dict[str, Any] = {
    "command": sys.executable or "python",
    "args": ["-m", "automedia.mcp.server"],
}

# Per-client configuration templates
_CLIENT_CONFIGS: dict[str, dict[str, Any]] = {
    "claude": {
        "name": "automedia",
        "type": "mcpServers",
        "config_wrap": {"mcpServers": {"automedia": _BASE_CONFIG}},
        "description": "Claude Desktop / Claude Code — add to your claude_desktop_config.json or CLAUDE.md",
    },
    "opencode": {
        "name": "AutoMedia",
        "type": "mcpServers",
        "config_wrap": {"mcpServers": {"AutoMedia": _BASE_CONFIG}},
        "description": "OpenCode — add to .opencode/package.json under mcpServers",
    },
    "codexcli": {
        "name": "AutoMedia",
        "type": "mcpServers",
        "config_wrap": {"mcpServers": {"AutoMedia": _BASE_CONFIG}},
        "description": "Codex CLI — add to ~/.codex/config.json or project .codex/config.json",
    },
}


def _output_format(data: Any, json_output: bool) -> None:  # noqa: ANN401  # Any is appropriate for CLI display
    """Print data as JSON or formatted text."""
    if json_output:
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(json.dumps(data, indent=2))


@app.command("discover")
def mcp_discover(
    client: str = typer.Option(
        "all",
        "--client",
        "-c",
        help="Target client: claude, opencode, codexcli, or all",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON without labels",
    ),
) -> None:
    """Generate MCP server configuration for AI coding agents.

    Prints the MCP server configuration snippet for the specified client.
    Use this to quickly configure your agent tool to connect to AutoMedia's
    MCP server.
    """
    if client == "all":
        result: dict[str, Any] = {"version": __version__, "configurations": {}}
        for c_name, c_config in _CLIENT_CONFIGS.items():
            result["configurations"][c_name] = {
                "description": c_config["description"],
                "config": c_config["config_wrap"],
            }
        _output_format(result, json_output)
    elif client in _CLIENT_CONFIGS:
        config = _CLIENT_CONFIGS[client]
        result = {
            "version": __version__,
            "client": client,
            "description": config["description"],
            "config": config["config_wrap"],
        }
        _output_format(result, json_output)
    else:
        valid = ", ".join(sorted(_CLIENT_CONFIGS.keys()))
        typer.echo(f"Error: unknown client '{client}'. Valid options: {valid}, all", err=True)
        raise typer.Exit(code=1)
