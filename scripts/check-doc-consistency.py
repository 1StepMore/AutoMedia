#!/usr/bin/env python3
"""Doc-consistency introspection check for AutoMedia.

Enforcement heart of the doc-sync plan: introspects the *real* MCP tool
count and CLI command count from the code itself (never hardcoded), then
fails (exit != 0) whenever any scanned doc file or code docstring carries
a numeric claim (``N tools`` / ``N commands`` / ``N command modules``)
that disagrees with the derived counts.

Scanned by default: README.md, AGENTS.md, docs/index.md,
docs/doc-inventory.md and the mcp module docstrings in
``src/automedia/mcp/__init__.py`` and ``src/automedia/mcp/server.py``.

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

WIRED-IN CHECKS (doc-hardening-pass2 Step 3): the pure ``scan_*`` functions
below are wired into ``main()`` and gate the build:
* ``scan_links`` (AGENTS.md only): root-relative ``docs/`` link targets must
  exist under the repo root.  A broken link is gate-failing.
* ``scan_identifiers`` (AGENTS.md, README.md, docs/index.md): backticked
  identifier candidates that survive the bounded-scope exclusion set are
  resolved against the ``automedia`` package (module import first, then
  attribute walk).  A resolver-rejected survivor is gate-failing — it is a
  stale symbol reference.  The exclusion set lives INSIDE
  ``scan_identifiers`` (before the resolver) so non-Python tokens
  (``deepseek``/``expect``/``failure_mode``, MCP tool names, CLI commands,
  env vars, YAML keys, workflow modes, scenario vocabulary, pytest markers,
  private names, SCREAMING_CASE constants, and module-level definitions that
  exist in the codebase) never reach the resolver and never gate-fail.
  Everything in the exclusion set is code-derived — never hand-maintained.
* ``scan_marker`` (docs/doc-inventory.md): the first line must be byte-equal
  to the AUTO-GENERATED marker of ``scripts/doc_inventory.py``; a missing or
  wrong marker is gate-failing.

SIZE_OK: this module deliberately exceeds the 250-line guideline — plan
W5-T3 pins the WHOLE doc gate in one step (extend the existing check, never
add a second doc step to CI), so every scan type (numeric claims, links,
identifiers, marker, doc↔reality audit) lives here; same precedent as
``automedia/validation/doc_reality.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import importlib
import inspect
import keyword
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
# docs/doc-inventory.md is scanned so its numeric table claims AND its
# AUTO-GENERATED marker are checked by default (marker check below).
_DEFAULT_DOC_FILES: tuple[str, ...] = (
    "README.md",
    "AGENTS.md",
    "docs/index.md",
    "docs/doc-inventory.md",
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

# Backticked identifier candidates in markdown. Allows the mixed-case
# ``GateEngine`` / ``PipelineResult`` style used by the public API surface
# as well as ``run_full_pipeline``. The ``{2,}`` length floor mirrors the
# ``[a-z_][a-z0-9_]{2,}`` contract in the doc-hardening-pass2 plan.
_IDENTIFIER_RE: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Single-line backticked spans only — triple-backtick code fences enclose
# whole file trees and must never yield candidates.
_BACKTICKED_RE: re.Pattern[str] = re.compile(r"`([^`\n]+)`")

# Env var names (``AUTOMEDIA_*``) appearing in docs / .env.example.
_ENV_VAR_RE: re.Pattern[str] = re.compile(r"\bAUTOMEDIA_[A-Z0-9_]+\b")

# Committed allowlist for residual false positives. One name per line; ``#``
# starts a comment. A name here suppresses a finding WITHOUT consulting the
# resolver (exclusion-set filter runs first, allowlist included). The goal
# is ZERO entries for the current corpus — the code-derived exclusion set
# must cover every non-Python token.
_ALLOWLIST_FILE = REPO_ROOT / "scripts" / "doc-identifier-allowlist.txt"

# The exact first line required on generated inventory files.  Must be
# byte-identical to the MARKER constant in tests/test_doc_consistency.py
# (which mirrors scripts/doc_inventory.py's emitted first line).
_INVENTORY_MARKER = (
    "<!-- AUTO-GENERATED: docs/doc-inventory.md — do not edit manually. "
    "Regenerate: python scripts/doc_inventory.py -->"
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


def scan_links(text: str, base: Path) -> list[Finding]:
    """Scan markdown for root-relative ``docs/`` link targets missing under ``base``.

    Pure function: ``text`` is the file content, ``base`` is the directory
    against which root-relative destinations resolve (the repo root). Only
    links whose destination starts with ``docs/`` are considered — absolute
    URLs, anchors (``#...``), and non-``docs`` relative links are ignored.
    ``Finding.found`` is the clean target string (e.g. ``docs/x.md``).
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
                        found=target,  # clean target string, e.g. docs/nonexistent-file.md
                        expected=f"existing target under {base}",
                    )
                )
    return findings


def scan_identifiers(text: str, resolver: Callable[[str], bool]) -> list[Finding]:
    """Scan ``text`` for backticked identifiers the resolver rejects.

    Pure function: ``resolver(name) -> bool`` returns True when the symbol
    resolves (exists). The caller decides severity; this function only
    reports candidates that survive the exclusion filter AND are rejected
    by the resolver.

    The exclusion-set filter is applied INSIDE this function, BEFORE the
    resolver is consulted (contract pinned in tests/test_doc_consistency.py
    docstrings). Non-Python tokens — MCP tool names, CLI command names, env
    var names, ``AUTOMEDIA_*``, YAML keys from ``manifests/defaults.yaml``,
    workflow modes, validation scenario vocabulary, pytest markers, private
    names, SCREAMING_CASE constants, Python keywords, committed allowlist
    entries — never reach the resolver and never produce a finding. Only a
    candidate that survives the filter AND is rejected by the resolver
    yields one Finding per occurrence, ``line`` = 1-based source line.

    ``Finding.file`` stays ``""`` (pure function); the caller fills in the
    real path.
    """
    excluded = _build_exclusion_set()
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _BACKTICKED_RE.finditer(line):
            candidate = match.group(1)
            if not _IDENTIFIER_RE.fullmatch(candidate):
                continue
            if candidate in excluded:
                continue
            if resolver(candidate):
                continue
            findings.append(
                Finding(
                    file="",
                    line=lineno,
                    found=candidate,
                    expected="a symbol resolvable against the automedia package "
                    "or an entry in scripts/doc-identifier-allowlist.txt",
                )
            )
    return findings


def scan_marker(text: str, marker: str) -> list[Finding]:
    """Scan ``text`` for an expected first-line marker (byte equality).

    Pure function: ``marker`` must equal the exact first line of ``text``.
    A mismatch — including a missing marker — yields exactly one Finding at
    ``line == 1``. ``Finding.file`` stays ``""``; the caller fills it in.
    """
    first_line = text.splitlines()[0] if text else ""
    if first_line == marker:
        return []
    return [
        Finding(
            file="",
            line=1,
            found=first_line,
            expected=f"first line == {marker!r}",
        )
    ]


def _read_allowlist() -> set[str]:
    """Read the committed allowlist file (one name per line, ``#`` comments).

    Missing or unreadable file = empty set (the exclusion set must be
    complete on its own; the allowlist is only for residual false positives).
    """
    try:
        lines = _ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    }


def _add_yaml_keys(excluded: set[str]) -> None:
    """Add every key from ``manifests/defaults.yaml`` to ``excluded``.

    Config keys are vocabulary, not Python symbols.  YAML is an optional
    dependency of the script's runtime (the audit already imports it
    transitively), so a missing import degrades to no-op rather than crash.
    """
    try:
        import yaml
    except ImportError:
        return
    path = REPO_ROOT / "src" / "automedia" / "manifests" / "defaults.yaml"
    if not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _walk(mapping: dict) -> None:
        for key, value in mapping.items():
            excluded.add(key)
            if isinstance(value, dict):
                _walk(value)

    if isinstance(data, dict):
        _walk(data)


def _add_validation_vocabulary(excluded: set[str]) -> None:
    """Add the agent-tester validation scenario vocabulary to ``excluded``.

    AGENTS.md §11 documents the validation framework's schema keywords
    (scenario/step/expect fields) and run-record statuses.  These are
    declarative metadata keys, not Python symbols — they must never reach
    the resolver.  Derived from the schema dataclasses + status constants so
    the set tracks the code, not the docs.
    """
    try:
        from automedia.validation import diff as _diff
        from automedia.validation import schema as _schema
    except ImportError:
        return
    for model in (_schema.Scenario, _schema.Step, _schema.Expect):
        excluded.update(field for field in model.__dataclass_fields__)
    excluded.update(getattr(_diff, "STATUSES", ()))
    excluded.update(getattr(_schema, "STEP_KINDS", ()))  # tool/cli/file — step kinds


@functools.lru_cache(maxsize=1)
def _build_exclusion_set() -> frozenset[str]:
    """The bounded-scope exclusion set for ``scan_identifiers``.

    Everything here is code-derived — never hand-maintained drift. Sources:

    * MCP tool names + CLI command names from ``doc_reality_audit()``
      (declared-tools / declared-commands — the audit's authoritative lists).
    * Workflow / pipeline mode names from ``automedia.pipelines.runner``.
    * YAML keys from ``automedia/manifests/defaults.yaml`` (top-level and
      nested keys are configuration vocabulary, not Python symbols).
    * Env var names: ``AUTOMEDIA_*`` occurrences in the scanned docs, the
      ``.env.example`` file, and the bare ``AUTOMEDIA_`` prefix itself.
    * Validation scenario vocabulary from ``automedia.validation.schema``
      (Scenario/Step/Expect dataclass fields) and ``...diff.STATUSES``
      (passed/failed/unconfigured/recovered/partial-pass) — AGENTS.md §11
      documents these keywords, they are not Python symbols.
    * pytest markers (registered in tests/conftest.py) + ``pytest`` itself.
    * Python keywords (``None``, ``in``, …) — never resolvable as symbols.
    * Private names (``_leading`` / ``__dunder__``) — documented as
      implementation detail, intentionally not part of the public surface.
    * SCREAMING_CASE names (``LICENSE``, ``AUTOMEDIA_*``) — constants or
      file names, not Python symbols.
    * The pinned non-Python tokens ``deepseek``, ``expect``, ``failure_mode``
      (canonical provider / scenario keyword / gate attribute — contract
      pinned in tests/test_doc_consistency.py).
    * Committed allowlist entries.
    """
    audit = doc_reality_audit()
    excluded: set[str] = set(audit["mcp_tools"]["declared"])
    excluded.update(audit["cli_commands"]["declared"])

    from automedia.pipelines.runner import VALID_MODES

    excluded.update(VALID_MODES)

    _add_yaml_keys(excluded)

    env_names: set[str] = set()
    for rel in (*_DEFAULT_DOC_FILES, "docs/user/cli-reference.md",
                "docs/user/mcp-setup.md", "docs/user/api-reference.md"):
        path = REPO_ROOT / rel
        if path.is_file():
            env_names.update(_ENV_VAR_RE.findall(path.read_text(encoding="utf-8")))
    env_file = REPO_ROOT / ".env.example"
    if env_file.is_file():
        env_names.update(_ENV_VAR_RE.findall(env_file.read_text(encoding="utf-8")))
    excluded.update(env_names)
    excluded.add("AUTOMEDIA_")  # the bare prefix is vocabulary, not a symbol

    excluded.update(keyword.kwlist)

    _add_validation_vocabulary(excluded)

    excluded.update(("pytest", "e2e", "redline", "slow", "smoke", "cruel", "tmp_path"))

    # The plan's canonical non-Python tokens, pinned by
    # tests/test_doc_consistency.py: scenario keyword / gate attribute /
    # provider name.  Not in defaults.yaml (grep confirmed), so explicit.
    excluded.update(("deepseek", "expect", "failure_mode"))

    # Everything else can be re-derived cheaply and is covered by the
    # resolver; private/dunder and SCREAMING_CASE names are always excluded.
    for name in _BACKTICKED_RE.findall(
        " ".join(
            p.read_text(encoding="utf-8")
            for p in (REPO_ROOT / "AGENTS.md", REPO_ROOT / "README.md",
                      REPO_ROOT / "docs" / "index.md")
            if p.is_file()
        )
    ):
        if _IDENTIFIER_RE.fullmatch(name) and (
            name.startswith("_") or name == name.upper()
        ):
            excluded.add(name)

    excluded.update(_read_allowlist())
    return frozenset(excluded)


@functools.lru_cache(maxsize=1)
def _package_symbols() -> frozenset[str]:
    """Every module-level symbol defined in the ``automedia`` package.

    AST-based: walks ``src/automedia/**/*.py`` and collects function/class
    definitions plus assignments at module level.  A backticked identifier
    that names one of these symbols is a REAL reference (the class/function
    exists), even when it is not re-exported at the package top level
    (``BaseGate``, ``app``, …).  Cached; resolution errors are swallowed
    only here, at the boundary, never converted into findings.
    """
    import ast

    symbols: set[str] = set()
    src = REPO_ROOT / "src" / "automedia"
    if not src.is_dir():
        return frozenset()
    for path in src.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        symbols.add(target.id)
    return frozenset(symbols)


def _resolver(name: str) -> bool:
    """Resolve ``name`` against the ``automedia`` package.

    Tries ``automedia.<name>`` as a module import, then an attribute walk on
    the ``automedia`` package, then the AST symbol table of the whole
    ``src/automedia/`` tree.  A candidate that fails all three is a resolver
    False — a genuine stale reference.  Import errors are never swallowed
    into findings.
    """
    try:
        importlib.import_module(f"automedia.{name}")
        return True
    except ImportError:
        pass
    try:
        import automedia

        if hasattr(automedia, name):
            return True
    except Exception:  # noqa: S110, BLE001 — resolver boundary; never a finding
        pass
    return name in _package_symbols()


def _print_findings(findings: list[Finding], file_label: str) -> None:
    """Print findings as ``file:line: ...``; return nothing (mutates only stdout)."""
    for finding in findings:
        print(
            f"{file_label}:{finding.line}: '{finding.found}' "
            f"expected {finding.expected}"
        )


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

    # Link check: AGENTS.md only (its table-driven docs/ references are the
    # contract; README links are overwhelmingly external/anchored and the
    # README is regenerated manually — AGENTS.md is the agent-facing source).
    agents_path = REPO_ROOT / "AGENTS.md"
    if agents_path.is_file():
        for finding in scan_links(
            agents_path.read_text(encoding="utf-8"), REPO_ROOT
        ):
            print(
                f"AGENTS.md:{finding.line}: link '{finding.found}' "
                f"expected {finding.expected}"
            )
            all_findings.append(finding)

    # Identifier check: AGENTS.md + README.md + docs/index.md. Resolver
    # rejections are gate-failing (a stale symbol reference in agent-facing
    # docs). Non-Python tokens never reach the resolver (exclusion set).
    for rel in ("AGENTS.md", "README.md", "docs/index.md"):
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for finding in scan_identifiers(text, _resolver):
            print(
                f"{rel}:{finding.line}: '{finding.found}' "
                f"expected {finding.expected}"
            )
            all_findings.append(finding)

    # Marker check: the committed docs/doc-inventory.md must carry the exact
    # AUTO-GENERATED marker on its first line (plan item 1c/3).
    inventory_path = REPO_ROOT / "docs" / "doc-inventory.md"
    if inventory_path.is_file():
        for finding in scan_marker(
            inventory_path.read_text(encoding="utf-8"), _INVENTORY_MARKER
        ):
            print(
                f"docs/doc-inventory.md:{finding.line}: '{finding.found}' "
                f"expected {finding.expected}"
            )
            all_findings.append(finding)

    blocking, informational = _run_doc_reality_audit()
    for line in informational:
        print(f"{line}  [informational]")
    for line in blocking:
        print(line)
    if all_findings or blocking:
        total = len(all_findings) + len(blocking)
        print(f"\nFAIL: {len(all_findings)} stale doc finding(s) + "
              f"{len(blocking)} blocking doc↔reality finding(s) = {total}")
        return 1
    print("\nOK: all doc numeric claims match derived counts; doc↔reality audit clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
