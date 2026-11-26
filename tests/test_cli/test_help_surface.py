"""Regression tests for the root CLI help surface (#696).

The lazy loader must expose every registered top-level command under its real
invocation name. Previously a resolved sub-app group carried an empty ``.name``
(so typer's rich help rendered a blank ``account`` row) and a single-command
sub-app collapsed into its only verb (help advertised a phantom top-level
``discover`` while the real ``mcp`` command had vanished).

Layout independence is deliberate: the same app renders as a rich box on a wide
terminal, as two columns by click, and as name-only rows with an indented
description when the name column does not fit — and the console may transcode
box-drawing characters or emit ANSI escapes. The assertions below therefore
never assume a layout, encoding or section delimiter: they only require that a
registered name appears as the first token of some help line.

Hermetic: CliRunner + in-process resolution only, no network, no keys.
"""

from __future__ import annotations

import re

import click
from typer.main import get_command as typer_get_command
from typer.testing import CliRunner

from automedia.cli.app import LazyTyperGroup, app

runner = CliRunner()
_root_click_cmd = typer_get_command(app)

_ENV = {"TERM": "xterm-256color", "COLUMNS": "200", "NO_COLOR": "1"}

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# First token of a line, whatever the renderer puts in front of it (indent,
# rich box border, or a border character the console transcoded to '?').
_LINE_START = re.compile(r"^[^A-Za-z0-9]*([A-Za-z][A-Za-z0-9_-]*)")


def _help_line_starts(help_output: str) -> list[str]:
    """First token of every help line, with ANSI escapes stripped."""
    text = _ANSI.sub("", help_output)
    tokens: list[str] = []
    for line in text.splitlines():
        match = _LINE_START.match(line)
        if match:
            tokens.append(match.group(1))
    return tokens


def _root_help() -> tuple[str, list[str]]:
    result = runner.invoke(app, ["--help"], prog_name="automedia", env=_ENV)
    assert result.exit_code == 0, result.output
    return result.output, _help_line_starts(result.output)


def _registered() -> list[str]:
    ctx = click.Context(_root_click_cmd, info_name="automedia")
    names = _root_click_cmd.list_commands(ctx)
    assert names, "sanity: the root app must register commands"
    return names


def test_every_registered_command_appears_in_help() -> None:
    output, tokens = _root_help()
    missing = sorted(set(_registered()) - set(tokens))
    assert not missing, f"registered but not rendered in --help: {missing}\n--- help ---\n{output}"


def test_no_phantom_top_level_command() -> None:
    output, tokens = _root_help()
    ctx = click.Context(_root_click_cmd, info_name="automedia")
    assert "discover" not in tokens, f"phantom top-level 'discover' row\n--- help ---\n{output}"
    assert _root_click_cmd.get_command(ctx, "discover") is None
    assert "account" in tokens, f"'account' missing from help\n--- help ---\n{output}"
    assert "mcp" in tokens, f"'mcp' missing from help\n--- help ---\n{output}"


def test_resolved_commands_carry_their_registration_name() -> None:
    """The invariant behind the blank row: ``cmd.name`` must equal the registration.

    Rendering-agnostic on purpose — typer renders ``cmd.name``, so an empty or
    wrong name is exactly what produced the blank ``account`` row.
    """
    ctx = click.Context(_root_click_cmd, info_name="automedia")
    for name in _registered():
        cmd = _root_click_cmd.get_command(ctx, name)
        assert cmd is not None, f"{name} is registered but get_command cannot resolve it"
        assert cmd.name == name, (
            f"command registered as {name!r} resolves to .name={cmd.name!r} "
            "(help would render that instead)"
        )


def test_mcp_stays_a_group_and_discover_is_nested() -> None:
    mcp_help = runner.invoke(app, ["mcp", "--help"], env=_ENV)
    assert mcp_help.exit_code == 0, mcp_help.output
    assert "discover" in mcp_help.output

    nested = runner.invoke(app, ["mcp", "discover", "--help"], env=_ENV)
    assert nested.exit_code == 0, nested.output

    phantom = runner.invoke(app, ["discover", "--help"], env=_ENV)
    assert phantom.exit_code != 0, phantom.output


def test_bare_mcp_prints_client_configuration() -> None:
    """Historical behaviour preserved: `automedia mcp` with no verb prints config.

    The group/collapse fix must not turn the bare invocation into a help page
    with exit code 2 — `cli/cli-surface-behavior` asserts the config output.
    """
    result = runner.invoke(app, ["mcp"], env=_ENV)
    assert result.exit_code == 0, result.output
    assert "mcpServers" in result.output


def test_lazy_registry_names_are_all_rendered() -> None:
    output, tokens = _root_help()
    lazy = set(LazyTyperGroup._lazy_sub_apps) | set(LazyTyperGroup._lazy_fns)
    missing = sorted(lazy - set(tokens))
    assert not missing, f"lazy registrations missing from help: {missing}\n--- help ---\n{output}"


def test_line_start_parser_handles_every_layout() -> None:
    """One parser, five shapes: rich box, plain, wrapped, ANSI+CRLF, mangled box."""
    boxed = (
        "╭─ Commands ─────────────────────────────╮\n"
        "│ account     Manage platform accounts.  │\n"
        "│             (wrapped continuation)     │\n"
        "│ mcp         MCP server management.     │\n"
        "╰────────────────────────────────────────╯\n"
    )
    plain = (
        "Options:\n"
        "  --help  Show this message and exit.\n"
        "\n"
        "Commands:\n"
        "  account  Manage platform accounts for publishing.\n"
        "  mcp      MCP server management commands.\n"
    )
    wrapped = (
        "Commands:\n"
        "  account\n"
        "      Manage platform accounts for publishing.\n"
        "  mcp\n"
        "      MCP server management commands.\n"
    )
    ansi_crlf = (
        "\x1b[1mCommands:\x1b[0m\r\n"
        "\x1b[36m  account\x1b[0m  Manage platform accounts.\r\n"
        "\x1b[36m  mcp\x1b[0m      MCP server management commands.\r\n"
    )
    mangled = (
        "?─ Commands ─────────────────────────────?\n"
        "? account     Manage platform accounts.  ?\n"
        "? mcp         MCP server management.     ?\n"
    )
    for sample in (boxed, plain, wrapped, ansi_crlf, mangled):
        tokens = _help_line_starts(sample)
        assert "account" in tokens, sample
        assert "mcp" in tokens, sample
