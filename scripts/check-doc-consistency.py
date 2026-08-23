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

W5-T3 RECONCILIATION DECISION (plan agent-tester-validation W5-T3, pinned):
the W3-T8 doc↔reality audit (``automedia.validation.doc_reality``) runs
HERE — the existing doc-consistency step is EXTENDED, not replaced, and no
second doc step is added to CI.  Rationale: the two checks overlap on the
MCP/CLI docs-vs-code theme but each covers claim types the other cannot —
this script verifies NUMERIC claims (``59 tools``), the audit verifies
TABLE membership + gate/adapter counts — so merging them keeps one doc gate
that is a strict superset.

AUDIT SEVERITY POLICY (W5-T3, pinned, empirical): the step fails on
findings with severity high or medium; ``low`` findings are informational
and never fail the gate.  Rationale: W5-T2 zeroed every high/medium
finding, but the audit carries ONE permanent low note — the refuted
``effects_analyze_content`` allegation (recommendation "None — docs match
code", do-NOT-touch per W5-T2).  Exit-on-any-finding would keep the doc
gate red forever; the high/medium pin stays a hard gate (all real drift —
omitted tools, wrong gate/adapter counts — is high/medium) while the
informational note is shown, not blocking.

KNOWN LIMITATION (enforcement gap): ``docs/user/cli-reference.md``,
``docs/user/mcp-setup.md`` and ``docs/user/api-reference.md`` are NOT
scanned by default — they are reconciled manually in the doc-sync workflow
(Wave A4) and future drift there is un-enforced by this gate. Pass
``--check-user-docs`` to include them explicitly.

TESTABILITY SEAM (doc-hardening-pass2 Step 1): the pure ``scan_*``
functions below — ``scan_links``, ``scan_identifiers``, ``scan_marker`` —
are the testability seam this refactor introduces. They are importable,
pure, and unit-testable, but are NOT yet wired into ``main()``; Step 3 of
the same plan will wire them in. ``scan_links`` already carries the trivial
core (root-relative ``docs/`` link existence); ``scan_identifiers`` and
``scan_marker`` are stubs returning ``[]`` until Step 3.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import click

from automedia.cli.app import app as _cli_app
from automedia.mcp.server import create_server
from automedia.validation.doc_reality import doc_reality_audit

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

# Markdown link destinations that are root-relative docs paths, e.g.
# ``](docs/user/cli-reference.md#foo)``. Only the root-relative ``docs/``
# form is matched; an anchor (anything after ``#``) or the closing paren
# terminates the match, so the captured target is the bare destination path.
_LINK_TARGET_RE: re.Pattern[str] = re.compile(r"\]\(docs/[^)#]+\)")


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


def scan_links(text: str, base: Path) -> list[Finding]:
    """Scan markdown for root-relative ``docs/`` link targets missing under ``base``.

    Pure function: ``text`` is the file content, ``base`` is the directory
    against which root-relative destinations resolve (the repo root). Only
    links whose destination starts with ``docs/`` are considered — absolute
    URLs, anchors (``#...``), and non-``docs`` relative links are ignored.

    This is the testability seam for the doc-link check; it is NOT yet wired
    into ``main()`` (Step 3 of doc-hardening-pass2 does that).
    """
    findings: list[Finding] = []
    if not base.is_dir():
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _LINK_TARGET_RE.finditer(line):
            target = match.group(0)[2:-1]  # strip leading "](" and trailing ")"
            if not (base / target).exists():
                findings.append(
                    Finding(
                        file="",  # file name is unknown here (pure); caller fills it in
                        line=lineno,
                        found=f"{match.group(0)})",
                        expected=f"existing target under {base}",
                    )
                )
    return findings


def scan_identifiers(text: str, resolver: Callable[[str], bool]) -> list[Finding]:
    """Scan ``text`` for candidate symbol references, keeping those the resolver rejects.

    Pure stub (doc-hardening-pass2 Step 1): the real identifier-marker
    extraction and resolution rules land in Step 3. ``resolver(name)``
    decides whether a candidate symbol exists — return True when it does.
    Currently always returns ``[]``; must remain importable with this exact
    signature so Step 3 can fill it in and Step 2 tests can drive it.
    """
    return []


def scan_marker(text: str, marker: str) -> list[Finding]:
    """Scan ``text`` for an expected first-line marker.

    Pure stub (doc-hardening-pass2 Step 1): the real marker check lands in
    Step 3. ``text`` is the file content, ``marker`` is the expected first
    line. Currently always returns ``[]``; must remain importable with this
    exact signature so Step 3 can fill it in and Step 2 tests can drive it.
    """
    return []


def _run_doc_reality_audit() -> tuple[list[str], list[str]]:
    """Run the W3-T8 doc↔reality audit; lines split blocking vs informational.

    Blocking = findings with severity high/medium (every real drift class);
    informational = low findings (the permanent refuted-allegation note).
    See the module docstring for the pinned severity policy.
    """
    audit = doc_reality_audit()
    findings = audit.get("findings") or []
    blocking: list[str] = []
    informational: list[str] = []
    for finding in findings:
        line = (
            f"  [{finding['severity']}] {finding['doc']}: '{finding['claim']}' "
            f"— reality: {finding['reality']} (fix: {finding['recommendation']})"
        )
        (blocking if finding["severity"] != "low" else informational).append(line)
    return blocking, informational


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

    blocking, informational = _run_doc_reality_audit()
    for line in informational:
        print(f"{line}  [informational]")
    for line in blocking:
        print(line)
    if all_findings or blocking:
        total = len(all_findings) + len(blocking)
        print(f"\nFAIL: {len(all_findings)} stale numeric claim(s) + "
              f"{len(blocking)} blocking doc↔reality finding(s) = {total}")
        return 1
    print("\nOK: all doc numeric claims match derived counts; doc↔reality audit clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
