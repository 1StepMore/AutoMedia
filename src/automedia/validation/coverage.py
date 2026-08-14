"""Coverage audit for the agent-tester validation layer (guide §5.1, plan W3-T7/C4).

Computes the coverage sets over the committed scenario library, purely
statically — regex/parse over committed source and scenario files, never a
runtime probe (guide §5.1 determinism requirement):

* ``declared`` — the surface as shipped.  MCP tools come from a regex over
  ``src/automedia/mcp/server.py`` (``mcp.tool(...)(fn)`` — the only
  registration form; there are NO ``Tool(name=...)`` declarations in the
  file; 59 registrations at lines 377-922 today).  CLI commands come from
  ``src/automedia/cli/app.py`` ``register_sub_app``/``register_fn``
  registrations (17 pre-existing; the W4 ``validate`` command is counted
  automatically because the audit reads the live file).
* ``scenario_used`` — every tool-kind ``tool:`` name and every cli-kind
  ``command:`` subcommand declared by the loaded scenarios (including
  recovery and cleanup steps: they are declared adapter calls too).  A
  cli-kind command counts only when its first token is ``automedia`` and it
  names a subcommand (the next non-flag token, so ``automedia --json doctor``
  → ``doctor``); non-automedia commands (``python3``, ``rm``, ``ls``,
  ``find``, ``mkdir``, ...) are setup, not surface, and are ignored.
* derived sets — ``covered`` = declared ∩ used, ``missing`` = declared −
  covered, ``phantom`` = used − declared.

Two policy classes shape the output (both pinned in the plan):

* BOUNDARY-ONLY (third class, review fix C1).  Scenarios with scenario-level
  ``error_boundary: true`` probe the dispatcher, not the surface (guide
  §5.1: "never silently counted as coverage"), so their tool/command targets
  are classified ``boundary_only_*``: listed loudly, excluded from
  ``covered_*`` AND from ``missing_*``.  ``missing = ∅`` in the committed
  output means "∅ excluding boundary-only (listed)" — the output carries a
  ``director_waiver_note``.  Step-level ``error_boundary`` (inside a
  non-boundary scenario) does NOT reclassify: the audit reads the scenario
  level only.
* PHANTOM POLICY (documented decision): phantom detection is PURE — used
  minus declared, no allowlist.  The committed meta scenarios
  (``list-validation-scenarios.yaml`` → tool ``list_validation_scenarios``;
  ``cli/validate-list-meta.yaml`` → command ``validate``) reference the W4
  validation surface before it ships, so they appear as expected-phantom
  until W4-T1/W4-T2 land; ``phantom_note`` states this.  When W4 registers
  the tools, the same run flips them to covered and phantom → ∅ — the meta
  scenarios ARE the registration mechanism (guide §3.1).  A
  ``KNOWN_FUTURE_SURFACE`` allowlist was deliberately NOT adopted: it would
  silently absorb permanent drift if W4 never landed, and phantom is a smell
  that must stay visible.

Static wrinkle: ``server.py`` imports ``analyze_content`` under the alias
``effects_analyze_content`` (line 46) and registers the imported name;
FastMCP keys ``fn.__name__``, so the callable surface is ``analyze_content``.
The declared set therefore resolves import aliases statically (the analogue
of ``fn.__name__``) and honors explicit ``name=`` kwargs when present
(pool_add_topic, batch_run, engine_health, mcp_help — today identical to the
function names).

The scenarios are loaded through ``automedia.validation.loader``, so a
scenario file that fails to load fails the audit loudly (schema conformance
is a precondition of coverage).  Run it directly::

    python -m automedia.validation.coverage   # prints deterministic JSON

The committed output lives at ``scenarios/baseline/coverage-audit.json``
(the tracked home for versioned audit artifacts, alongside the W2-T4
pre-flight baseline).
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

import yaml

from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario, Step

_MCP_TOOL_RE = re.compile(r"mcp\.tool\((.*?)\)\((\w+)\)", re.DOTALL)
_NAME_KW_RE = re.compile(r'name\s*=\s*["\'](\w+)["\']')
_FROM_IMPORT_RE = re.compile(
    r"^\s*from\s+[\w.]+\s+import\s+(?:\(([^)]*)\)|([^\n#]+))", re.MULTILINE
)
_CLI_REG_RE = re.compile(r'register_(?:sub_app|fn)\(\s*["\']([^"\']+)["\']')


def coverage_audit(
    scenarios_dir: str | Path | None = None,
    *,
    server_path: str | Path | None = None,
    app_path: str | Path | None = None,
) -> dict[str, Any]:
    """Deterministic coverage audit over the scenario library (guide §5.1).

    ``scenarios_dir`` defaults to the loader's default (env override
    ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` else repo-root ``scenarios/``);
    ``server_path``/``app_path`` default to the repo's ``mcp/server.py`` and
    ``cli/app.py``.  Returns the full audit dict (declared/used/covered/
    missing/phantom/boundary-only sets, boundary scenario files, waiver and
    phantom notes, and a numeric summary).
    """
    root = default_scenarios_dir() if scenarios_dir is None else Path(scenarios_dir)
    server_src = _read_declared_source(server_path, "src/automedia/mcp/server.py")
    app_src = _read_declared_source(app_path, "src/automedia/cli/app.py")

    declared_mcp = _declared_mcp(server_src)
    declared_cli = _declared_cli(app_src)
    scenarios = load_scenarios(root)
    file_map = _scenario_file_map(root)

    used_mcp: set[str] = set()
    used_cli: set[str] = set()
    boundary_mcp: set[str] = set()
    boundary_cli: set[str] = set()
    boundary_files: list[str] = []
    for scenario in scenarios:
        tools, clis = _scenario_targets(scenario)
        used_mcp |= tools
        used_cli |= clis
        if scenario.error_boundary:
            boundary_mcp |= tools
            boundary_cli |= clis
            boundary_files.append(file_map.get(scenario.name, scenario.name))

    declared_mcp_set = set(declared_mcp)
    declared_cli_set = set(declared_cli)
    covered_mcp = sorted(declared_mcp_set & used_mcp - boundary_mcp)
    covered_cli = sorted(declared_cli_set & used_cli - boundary_cli)
    missing_mcp = sorted(declared_mcp_set - set(covered_mcp) - boundary_mcp)
    missing_cli = sorted(declared_cli_set - set(covered_cli) - boundary_cli)
    phantom_mcp = sorted(used_mcp - declared_mcp_set)
    phantom_cli = sorted(used_cli - declared_cli_set)

    return {
        "declared_mcp": declared_mcp,
        "declared_cli": declared_cli,
        "used_mcp": sorted(used_mcp),
        "used_cli": sorted(used_cli),
        "covered_mcp": covered_mcp,
        "covered_cli": covered_cli,
        "missing_mcp": missing_mcp,
        "missing_cli": missing_cli,
        "phantom_mcp": phantom_mcp,
        "phantom_cli": phantom_cli,
        "boundary_only_mcp": sorted(boundary_mcp),
        "boundary_only_cli": sorted(boundary_cli),
        "error_boundary_scenarios": sorted(boundary_files),
        "director_waiver_note": _director_waiver_note(sorted(boundary_mcp)),
        "phantom_note": _phantom_note(phantom_mcp, phantom_cli),
        "summary": {
            "mcp_declared": len(declared_mcp),
            "mcp_used": len(used_mcp),
            "mcp_covered": len(covered_mcp),
            "mcp_missing": len(missing_mcp),
            "mcp_phantom": len(phantom_mcp),
            "mcp_boundary_only": len(boundary_mcp),
            "cli_declared": len(declared_cli),
            "cli_used": len(used_cli),
            "cli_covered": len(covered_cli),
            "cli_missing": len(missing_cli),
            "cli_phantom": len(phantom_cli),
            "cli_boundary_only": len(boundary_cli),
        },
    }


def _read_declared_source(explicit: str | Path | None, rel: str) -> str:
    """Read a declared-surface source file: explicit path or repo default."""
    path = Path(explicit) if explicit is not None else _repo_root() / rel
    return path.read_text(encoding="utf-8")


def _repo_root() -> Path:
    """Repo root from this module's location (same trick as the loader)."""
    return Path(__file__).resolve().parents[3]


def _import_aliases(src: str) -> dict[str, str]:
    """Map ``as`` import aliases to their real names (``from X import y as z``
    and parenthesized variants) — the static analogue of ``fn.__name__``."""
    aliases: dict[str, str] = {}
    for match in _FROM_IMPORT_RE.finditer(src):
        body = match.group(1) or match.group(2) or ""
        for item in body.split(","):
            parts = [part.strip() for part in item.split(" as ")]
            if len(parts) == 2 and parts[0] and parts[1]:
                aliases[parts[1]] = parts[0]
    return aliases


def _declared_mcp(src: str) -> list[str]:
    """Extract registered tool names from a server module source.

    Matches every ``mcp.tool(...)(fn)`` registration (no ``Tool(name=...)``
    declarations exist in server.py); the callable name is the ``name=``
    kwarg when present, else ``fn`` resolved through import aliases.
    """
    aliases = _import_aliases(src)
    names: list[str] = []
    for match in _MCP_TOOL_RE.finditer(src):
        kw = _NAME_KW_RE.search(match.group(1) or "")
        fn = match.group(2) or ""
        names.append(kw.group(1) if kw else aliases.get(fn, fn))
    return sorted(set(names))


def _declared_cli(src: str) -> list[str]:
    """Extract command names from app.py ``register_sub_app``/``register_fn``
    registrations (the string-literal first argument)."""
    return sorted(set(_CLI_REG_RE.findall(src)))


def _scenario_targets(scenario: Scenario) -> tuple[set[str], set[str]]:
    """Tool and CLI targets named by a scenario's steps, recursing into
    recovery steps; cleanup steps included (declared adapter calls too)."""
    tools: set[str] = set()
    clis: set[str] = set()

    def walk(step: Step) -> None:
        if step.kind == "tool" and step.tool:
            tools.add(step.tool)
        elif step.kind == "cli" and step.command:
            sub = _cli_subcommand(step.command)
            if sub is not None:
                clis.add(sub)
        for recovery in step.recovery_steps:
            walk(recovery)

    for step in [*scenario.steps, *scenario.cleanup_steps]:
        walk(step)
    return tools, clis


def _cli_subcommand(command: str) -> str | None:
    """Subcommand named by a cli-kind command, or None when it is not an
    ``automedia <sub>`` invocation (setup commands like ``python3``/``rm``/
    ``find`` are ignored).  Flags before the subcommand (``automedia --json
    doctor``) are skipped."""
    tokens = shlex.split(command)
    if not tokens or tokens[0] != "automedia":
        return None
    for token in tokens[1:]:
        if not token.startswith("-"):
            return token
    return None


def _scenario_file_map(root: Path) -> dict[str, str]:
    """Map scenario name → path relative to the scenarios root, so
    ``error_boundary_scenarios`` names files (deterministic across hosts)."""
    mapping: dict[str, str] = {}
    if not root.is_dir():
        return mapping
    for path in sorted(root.rglob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        name = doc.get("name") if isinstance(doc, dict) else None
        if isinstance(name, str):
            mapping[name] = str(path.relative_to(root))
    return mapping


def _director_waiver_note(boundary_mcp: list[str]) -> str:
    """Loud note for the boundary-only third class (review fix C1)."""
    names = ", ".join(boundary_mcp) if boundary_mcp else "(none)"
    return (
        "Boundary-only allowlist (third coverage class, review fix C1): "
        f"scenario-level error_boundary: true scenarios probe the dispatcher, "
        f"not the surface, so their targets ({names}) are listed loudly here "
        "and EXCLUDED from covered_* AND from missing_*. missing = ∅ means "
        "'∅ excluding boundary-only (listed)'. Director waiver required for "
        "this classification (guide §5.1: error-boundary probes are never "
        "silently counted as coverage)."
    )


def _phantom_note(phantom_mcp: list[str], phantom_cli: list[str]) -> str:
    """Note documenting the pure-phantom policy and expected W4 phantom."""
    return (
        "Phantom = used minus declared, computed purely (no KNOWN_FUTURE_"
        "SURFACE allowlist — phantom must stay visible or real drift is "
        "silently absorbed). Expected-phantom today: the committed meta "
        "scenarios reference the W4 validation surface before it ships "
        f"(MCP: {', '.join(phantom_mcp) or '(none)'}; CLI: "
        f"{', '.join(phantom_cli) or '(none)'}). When W4-T1/W4-T2 register "
        "those surfaces, the same audit flips them to covered and phantom → ∅."
    )


def main() -> None:
    """Print the audit as deterministic JSON (``python -m
    automedia.validation.coverage``)."""
    print(json.dumps(coverage_audit(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
