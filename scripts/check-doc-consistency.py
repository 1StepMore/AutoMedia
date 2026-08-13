#!/usr/bin/env python3
"""Doc-consistency introspection check for AutoMedia.

Enforcement heart of the doc-sync plan: introspects the *real* MCP tool
count and CLI command count from the code itself (never hardcoded), then
fails (exit != 0) whenever any scanned doc file or code docstring carries
a numeric claim (``N tools`` / ``N commands`` / ``N command modules``)
that disagrees with the derived counts.

Scanned by default: README.md, AGENTS.md, docs/index.md and the mcp module
docstrings in ``src/automedia/mcp/__init__.py`` and
``src/automedia/mcp/server.py``.

KNOWN LIMITATION (enforcement gap): ``docs/user/cli-reference.md``,
``docs/user/mcp-setup.md`` and ``docs/user/api-reference.md`` are NOT
scanned by default — they are reconciled manually in the doc-sync workflow
(Wave A4) and future drift there is un-enforced by this gate. Pass
``--check-user-docs`` to include them explicitly.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import click

from automedia.cli.app import app as _cli_app
from automedia.mcp.server import create_server

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files scanned by default. See module docstring for the KNOWN LIMITATION
# (user docs are reconciled manually and intentionally NOT in this list).
_DEFAULT_DOC_FILES: tuple[str, ...] = (
    "README.md",
    "AGENTS.md",
    "docs/index.md",
    "src/automedia/mcp/__init__.py",
    "src/automedia/mcp/server.py",
)

_USER_DOC_FILES: tuple[str, ...] = (
    "docs/user/cli-reference.md",
    "docs/user/mcp-setup.md",
    "docs/user/api-reference.md",
)

# Numeric claims we look for. Each entry maps the claim kind to the derived
# count it must equal (tools -> MCP tool count, commands -> CLI command count).
# ``(?:\s+modules?)?`` captures the "13 command modules" style of claim.
_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tools", re.compile(r"(\d+)\s+tools?\b", re.IGNORECASE)),
    ("commands", re.compile(r"(\d+)\s+commands?(?:\s+modules?)?\b", re.IGNORECASE)),
)


def _count_mcp_tools() -> int:
    """Derive the real MCP tool count from the running server.

    Uses the public tool-listing API ``ToolManager.list_tools()`` rather
    than grepping source. Note: list_tools is an async method in some mcp
    versions and synchronous in others (sync in mcp 1.28.1) — the result is
    wrapped in ``asyncio.run()`` only when it actually returns a coroutine.
    Only if that public API does not exist do we fall back to the private
    ``_tool_manager._tools`` attribute.
    """
    server = create_server()
    manager = server._tool_manager
    if hasattr(manager, "list_tools"):
        listed = manager.list_tools()
        if inspect.iscoroutine(listed):
            # Async in newer mcp versions: run through the event loop.
            listed = asyncio.run(listed)
        return len(listed)
    # Fallback (documented): older mcp versions only expose the private dict.
    return len(manager._tools)


def _count_cli_commands() -> int:
    """Derive the real CLI command count.

    The typer app uses ``LazyTyperGroup`` (src/automedia/cli/app.py:22) with
    ``register_sub_app``/``register_fn`` lazy registration; ``app.commands``
    holds only ALREADY-RESOLVED commands (0 before the first lookup), so a
    naive ``len(app.commands)`` returns 0. We must count via the
    ``LazyTyperGroup.list_commands(ctx)`` override (app.py:116-120), which
    merges resolved + lazy commands. ``@app.callback()`` main() is a callback,
    NOT a command, so it is not counted.
    """
    from typing import cast

    from typer.main import get_command as typer_get_command

    # typer.main.get_command is annotated with typer's own Command stub;
    # the runtime object is our LazyTyperGroup (a click.Group subclass), so
    # cast to click.Group to get the typed list_commands() override.
    group = cast(click.Group, typer_get_command(_cli_app))
    ctx = click.Context(group)
    return len(group.list_commands(ctx))


@dataclass(frozen=True)
class Finding:
    """One stale numeric claim in a scanned file."""

    file: str
    line: int
    found: str
    expected: str


def _scan_file(path: Path, tool_count: int, command_count: int) -> list[Finding]:
    """Scan one file for numeric tool/command claims that disagree with the derived counts."""
    findings: list[Finding] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for kind, pattern in _CLAIM_PATTERNS:
            expected = tool_count if kind == "tools" else command_count
            for match in pattern.finditer(line):
                claimed = int(match.group(1))
                if claimed != expected:
                    findings.append(
                        Finding(
                            file=path.name,
                            line=lineno,
                            found=match.group(0),
                            expected=f"{expected} {kind}",
                        )
                    )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Run the consistency check; return 0 when all checks pass, 1 otherwise."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-user-docs",
        action="store_true",
        help=(
            "Also scan docs/user/cli-reference.md, docs/user/mcp-setup.md and "
            "docs/user/api-reference.md (NOT scanned by default — known limitation)."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    tool_count = _count_mcp_tools()
    command_count = _count_cli_commands()
    print(f"Derived counts: {tool_count} MCP tools, {command_count} CLI commands")

    files = list(_DEFAULT_DOC_FILES)
    if args.check_user_docs:
        files.extend(_USER_DOC_FILES)

    all_findings: list[Finding] = []
    for rel in files:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"WARNING: {rel} not found — skipped")
            continue
        for finding in _scan_file(path, tool_count, command_count):
            print(f"{finding.file}:{finding.line}: '{finding.found}' expected {finding.expected}")
            all_findings.append(finding)

    if all_findings:
        print(f"\nFAIL: {len(all_findings)} stale doc claim(s) found")
        return 1
    print("\nOK: all doc numeric claims match derived counts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
