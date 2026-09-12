"""Coverage audit for the agent-tester validation layer (guide §5.1, plan W3-T7/C4).

Two halves, one output:

* The STATIC half (declarative, deterministic) computes the declared/used/
  covered/missing/phantom/boundary-only sets over the committed scenario
  library as before — regex/parse over committed source and scenario files,
  never a runtime probe (guide §5.1 determinism requirement).
* The EVIDENCE half (gap T-01) defines coverage as **declared surface ∩
  surfaces actually reached by a ``passed`` step in the newest persisted
  suite run**.  It emits ``covered`` / ``unproven`` / ``missing`` per surface
  and refuses to count a mock-confidence run, an ``unconfigured`` scenario,
  an ``error_boundary`` probe, or a meta scenario as proof.  A surface can be
  excluded from ``unproven`` only while a versioned ``boundary_only``
  allowlist (owner + reason + expiry) covers it.  The CLI
  ``automedia validate coverage`` consumes this half and exits 1 while any
  non-allowlisted surface — including S3/L0 (all gates/modes) — is
  ``unproven``.

The static half is preserved verbatim for the matrix and MCP audit surfaces;
the evidence half is additive and only reads a run record when ``runs_root``
is supplied.

* ``declared`` — the surface as shipped.  MCP tools come from a regex over
  ``src/automedia/mcp/server.py`` (``mcp.tool(...)(fn)`` — the only
  registration form; there are NO ``Tool(name=...)`` declarations in the
  file; 59 registrations at lines 377-922 today).  CLI commands come from
  ``src/automedia/cli/app.py`` ``register_sub_app``/``register_fn``
  registrations (17 pre-existing; the W4 ``validate`` command is counted
  automatically because the audit reads the live file).  Gates and modes
  (issue #78) come from the pipeline source constants: ``_MODE_MAP`` keys
  in ``src/automedia/pipelines/runner.py`` name the modes, and the
  ``_<MODE>_GATE_NAMES`` lists it references define each mode's gate set;
  the declared gates are the union across all mode lists plus the
  standalone D-gates (D1-D7), whose ``_gate_name`` class attributes live in
  ``src/automedia/gates/distribution/*.py`` (never referenced by a mode
  list — the union must still include them, 33 gates / 9 modes).
* ``scenario_used`` — every tool-kind ``tool:`` name and every cli-kind
  ``command:`` subcommand declared by the loaded scenarios (including
  recovery and cleanup steps: they are declared adapter calls too).  A
  cli-kind command counts only when its first token is ``automedia`` and it
  names a subcommand (the next non-flag token, so ``automedia --json doctor``
  → ``doctor``); non-automedia commands (``python3``, ``rm``, ``ls``,
  ``find``, ``mkdir``, ...) are setup, not surface, and are ignored.  For
  the pipeline surfaces, the scenarios' declarative ``proves_gates``/
  ``proves_modes`` headers name what they prove (a gate or mode is "used"
  when any non-boundary scenario proves it; boundary-only proves are the
  third class below).
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

import ast
import json
import re
import shlex
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from automedia.validation.loader import LoadError, default_scenarios_dir, load_scenarios
from automedia.validation.persist import latest_run
from automedia.validation.schema import USER_LEVELS, Scenario, Step

_MCP_TOOL_RE = re.compile(r"mcp\.tool\((.*?)\)\((\w+)\)", re.DOTALL)
_NAME_KW_RE = re.compile(r'name\s*=\s*["\'](\w+)["\']')
_FROM_IMPORT_RE = re.compile(
    r"^\s*from\s+[\w.]+\s+import\s+(?:\(([^)]*)\)|([^\n#]+))", re.MULTILINE
)
_CLI_REG_RE = re.compile(r'register_(?:sub_app|fn)\(\s*["\']([^"\']+)["\']')
_GATE_NAME_ASSIGN_RE = re.compile(r'^\s*_gate_name\s*=\s*"([^"]+)"', re.MULTILINE)

ALLOWLIST_FILENAME = "boundary_only_allowlist.yml"
"""Versioned boundary-only allowlist read by the evidence half (gap T-01).

Deliberately ``.yml``, not ``.yaml``: the scenario loader globs ``*.yaml``
recursively across the scenarios directory, so a ``.yaml`` allowlist would be
rejected as a malformed scenario.
"""

SURFACES: tuple[str, ...] = ("mcp", "cli", "gates", "modes")
"""The four declared surfaces the evidence half reports on."""


def coverage_audit(
    scenarios_dir: str | Path | None = None,
    *,
    server_path: str | Path | None = None,
    app_path: str | Path | None = None,
    runner_path: str | Path | None = None,
    distribution_path: str | Path | None = None,
    runs_root: str | Path | None = None,
    allowlist_path: str | Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Coverage audit over the scenario library (guide §5.1, gap T-01).

    ``scenarios_dir`` defaults to the loader's default (env override
    ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` else repo-root ``scenarios/``);
    ``server_path``/``app_path`` default to the repo's ``mcp/server.py`` and
    ``cli/app.py``; ``runner_path``/``distribution_path`` default to the
    repo's ``pipelines/runner.py`` and ``gates/distribution/`` (the gate and
    mode declared surfaces, issue #78).

    ``runs_root`` enables the evidence half: when supplied, the newest
    persisted suite run under it is read and ``covered``/``unproven``/
    ``missing`` are computed from its ``passed`` steps (``covered`` requires a
    real-confidence proof; mock/unconfigured/boundary/meta proofs never count).
    ``allowlist_path`` overrides the versioned boundary-only allowlist
    (default ``<scenarios_dir>/boundary_only_allowlist.yml``); ``today`` pins
    the expiry check for deterministic tests.

    Returns the full audit dict: the static sets (declared/used/covered/
    missing/phantom/boundary-only per surface, notes, summary) PLUS the
    evidence buckets (``covered``/``unproven``/``missing``, ``allowlisted``,
    ``evidence_run``, ``evidence_confidence``, counts).
    """
    root = default_scenarios_dir() if scenarios_dir is None else Path(scenarios_dir)
    server_src = _read_declared_source(server_path, "src/automedia/mcp/server.py")
    app_src = _read_declared_source(app_path, "src/automedia/cli/app.py")
    declared_gates, declared_modes = _declared_pipeline_surfaces(runner_path, distribution_path)

    declared_mcp = _declared_mcp(server_src)
    declared_cli = _declared_cli(app_src)
    scenarios = load_scenarios(root)
    file_map = _scenario_file_map(root)

    used_mcp: set[str] = set()
    used_cli: set[str] = set()
    used_gates: set[str] = set()
    used_modes: set[str] = set()
    boundary_mcp: set[str] = set()
    boundary_cli: set[str] = set()
    boundary_gates: set[str] = set()
    boundary_modes: set[str] = set()
    boundary_files: list[str] = []
    for scenario in scenarios:
        tools, clis = _scenario_targets(scenario)
        used_mcp |= tools
        used_cli |= clis
        used_gates |= set(scenario.proves_gates)
        used_modes |= set(scenario.proves_modes)
        if scenario.error_boundary:
            boundary_mcp |= tools
            boundary_cli |= clis
            boundary_gates |= set(scenario.proves_gates)
            boundary_modes |= set(scenario.proves_modes)
            boundary_files.append(file_map.get(scenario.name, scenario.name))

    declared_mcp_set = set(declared_mcp)
    declared_cli_set = set(declared_cli)
    declared_gates_set = set(declared_gates)
    declared_modes_set = set(declared_modes)
    covered_mcp = sorted(declared_mcp_set & used_mcp - boundary_mcp)
    covered_cli = sorted(declared_cli_set & used_cli - boundary_cli)
    covered_gates = sorted(declared_gates_set & used_gates - boundary_gates)
    covered_modes = sorted(declared_modes_set & used_modes - boundary_modes)
    missing_mcp = sorted(declared_mcp_set - set(covered_mcp) - boundary_mcp)
    missing_cli = sorted(declared_cli_set - set(covered_cli) - boundary_cli)
    missing_gates = sorted(declared_gates_set - set(covered_gates) - boundary_gates)
    missing_modes = sorted(declared_modes_set - set(covered_modes) - boundary_modes)
    phantom_mcp = sorted(used_mcp - declared_mcp_set)
    phantom_cli = sorted(used_cli - declared_cli_set)
    phantom_gates = sorted(used_gates - declared_gates_set)
    phantom_modes = sorted(used_modes - declared_modes_set)

    result: dict[str, Any] = {
        "declared_mcp": declared_mcp,
        "declared_cli": declared_cli,
        "declared_gates": declared_gates,
        "declared_modes": declared_modes,
        "used_mcp": sorted(used_mcp),
        "used_cli": sorted(used_cli),
        "used_gates": sorted(used_gates),
        "used_modes": sorted(used_modes),
        "covered_mcp": covered_mcp,
        "covered_cli": covered_cli,
        "covered_gates": covered_gates,
        "covered_modes": covered_modes,
        "missing_mcp": missing_mcp,
        "missing_cli": missing_cli,
        "missing_gates": missing_gates,
        "missing_modes": missing_modes,
        "phantom_mcp": phantom_mcp,
        "phantom_cli": phantom_cli,
        "phantom_gates": phantom_gates,
        "phantom_modes": phantom_modes,
        "boundary_only_mcp": sorted(boundary_mcp),
        "boundary_only_cli": sorted(boundary_cli),
        "boundary_only_gates": sorted(boundary_gates),
        "boundary_only_modes": sorted(boundary_modes),
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
            "gates_declared": len(declared_gates),
            "gates_used": len(used_gates),
            "gates_covered": len(covered_gates),
            "gates_missing": len(missing_gates),
            "gates_phantom": len(phantom_gates),
            "gates_boundary_only": len(boundary_gates),
            "modes_declared": len(declared_modes),
            "modes_used": len(used_modes),
            "modes_covered": len(covered_modes),
            "modes_missing": len(missing_modes),
            "modes_phantom": len(phantom_modes),
            "modes_boundary_only": len(boundary_modes),
        },
    }
    result.update(
        _evidence_coverage(
            scenarios=scenarios,
            file_map=file_map,
            declared={
                "mcp": declared_mcp_set,
                "cli": declared_cli_set,
                "gates": declared_gates_set,
                "modes": declared_modes_set,
            },
            used={
                "mcp": used_mcp,
                "cli": used_cli,
                "gates": used_gates,
                "modes": used_modes,
            },
            runs_root=None if runs_root is None else Path(runs_root),
            allowlist_path=allowlist_path,
            default_allowlist=root / ALLOWLIST_FILENAME,
            today=date.today() if today is None else today,
        )
    )
    result["by_level"] = _by_user_level(scenarios)
    return result


def _by_user_level(scenarios: list[Scenario]) -> dict[str, Any]:
    """Data-driven stage×user matrix from the scenarios' declared levels (T-10).

    The stage dimension is the scenario's committed ``category`` grouping (the
    library's own declarative row key); the user dimension is the closed
    ``USER_LEVELS`` enum.  Cells are scenario counts, so the matrix is derived
    entirely from the loaded library — never from auditor judgment.  Every
    level column is always present (a zero column is honest), and the cell
    total equals the library size.
    """
    distribution: dict[str, int] = dict.fromkeys(USER_LEVELS, 0)
    matrix: dict[str, dict[str, int]] = {}
    for scenario in scenarios:
        level = scenario.user_level if scenario.user_level in USER_LEVELS else "L0"
        distribution[level] += 1
        row = matrix.setdefault(scenario.category, dict.fromkeys(USER_LEVELS, 0))
        row[level] += 1
    return {
        "levels": list(USER_LEVELS),
        "distribution": distribution,
        "matrix": {row: matrix[row] for row in sorted(matrix)},
        "total": len(scenarios),
    }


def _read_declared_source(explicit: str | Path | None, rel: str) -> str:
    """Read a declared-surface source file: explicit path or repo default."""
    path = Path(explicit) if explicit is not None else _repo_root() / rel
    return path.read_text(encoding="utf-8")


def _record_confidence(record: dict[str, Any]) -> str:
    """A run/scenario record's confidence: ``mock`` or ``real`` (absent = real)."""
    value = record.get("confidence")
    return value if value in ("real", "mock") else "real"


def _is_meta(scenario: Scenario | None, rel_path: str) -> bool:
    """True when the scenario is harness/meta, never product-surface evidence.

    Meta detection is category-first (``category: meta``) with a file-path
    fallback (``meta/`` dir, ``*-meta`` stems, the validation self-listing),
    because the committed meta scenarios do not all carry ``category: meta``.
    """
    if scenario is not None and scenario.category == "meta":
        return True
    rel = rel_path.replace("\\", "/")
    if rel.startswith("meta/"):
        return True
    return Path(rel).stem.endswith("-meta") or rel == "list-validation-scenarios.yaml"


def _load_run_record(path: Path) -> dict[str, Any] | None:
    """Read a persisted suite record, best-effort (None on absent/corrupt)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _collect_reached(
    record: dict[str, Any],
    library: dict[str, Scenario],
    file_map: dict[str, str],
    reached: dict[str, set[str]],
) -> None:
    """Accumulate the surfaces a real-confidence, passed proof reached.

    mcp/cli surfaces count a ``passed`` step's target; gates/modes count a
    ``passed`` scenario's declarative ``proves_gates``/``proves_modes``.
    Mock-confidence records, boundary probes, unconfigured scenarios, and meta
    scenarios are never proof.
    """
    records = record.get("scenarios")
    if not isinstance(records, list):
        return
    for rec in records:
        if not isinstance(rec, dict) or _record_confidence(rec) == "mock":
            continue
        name = str(rec.get("scenario") or "")
        scenario = library.get(name)
        if rec.get("error_boundary") is True or (scenario is not None and scenario.error_boundary):
            continue
        if _is_meta(scenario, file_map.get(name, "")):
            continue
        steps = rec.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict) or step.get("passed") is not True:
                    continue
                surface = step.get("surface")
                target = step.get("target")
                if not isinstance(target, str):
                    continue
                if surface == "tool":
                    reached["mcp"].add(target)
                elif surface == "cli":
                    sub = _cli_subcommand(target)
                    if sub is not None:
                        reached["cli"].add(sub)
        if rec.get("status") == "passed" and scenario is not None:
            reached["gates"] |= set(scenario.proves_gates)
            reached["modes"] |= set(scenario.proves_modes)


def _load_allowlist(path: Path, today: date) -> tuple[dict[str, set[str]], dict[str, Any]]:
    """Load the versioned boundary-only allowlist (gap T-01).

    Every entry must name a known surface, a ``name``, an ``owner``, and a
    ``reason``; an optional ISO ``expires`` date drops the entry once past
    (per-release review, max one release).  A malformed file is a loud
    :class:`LoadError` — the audit never silently waives coverage.
    """
    allow: dict[str, set[str]] = {surface: set() for surface in SURFACES}
    meta: dict[str, Any] = {
        "path": str(path),
        "version": None,
        "reviewed": None,
        "release": None,
        "active": [],
        "expired": [],
    }
    if not path.is_file():
        return allow, meta
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LoadError(f"{path}: boundary-only allowlist is unreadable: {exc}") from exc
    if not isinstance(doc, dict):
        raise LoadError(f"{path}: boundary-only allowlist must be a mapping")
    if "version" not in doc:
        raise LoadError(f"{path}: boundary-only allowlist requires a 'version' field")
    meta["version"] = doc.get("version")
    meta["reviewed"] = doc.get("reviewed")
    meta["release"] = doc.get("release")
    entries = doc.get("entries", [])
    if not isinstance(entries, list):
        raise LoadError(f"{path}: 'entries' must be a list")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise LoadError(f"{path}: entries[{index}] must be a mapping")
        surface = entry.get("surface")
        name = entry.get("name")
        owner = entry.get("owner")
        reason = entry.get("reason")
        if surface not in SURFACES:
            raise LoadError(f"{path}: entries[{index}].surface {surface!r} not in {list(SURFACES)}")
        for field, value in (("name", name), ("owner", owner), ("reason", reason)):
            if not isinstance(value, str) or not value.strip():
                raise LoadError(f"{path}: entries[{index}].{field} is required")
        row = {
            "surface": surface,
            "name": name,
            "owner": owner,
            "reason": reason,
            "expires": entry.get("expires"),
        }
        expires = entry.get("expires")
        active = True
        if expires is not None:
            try:
                active = date.fromisoformat(str(expires)) >= today
            except ValueError as err:
                raise LoadError(
                    f"{path}: entries[{index}].expires must be ISO YYYY-MM-DD: {err}"
                ) from err
        meta["active" if active else "expired"].append(row)
        if active:
            allow[surface].add(name)
    return allow, meta


def _evidence_coverage(
    *,
    scenarios: list[Scenario],
    file_map: dict[str, str],
    declared: dict[str, set[str]],
    used: dict[str, set[str]],
    runs_root: Path | None,
    allowlist_path: str | Path | None,
    default_allowlist: Path,
    today: date,
) -> dict[str, Any]:
    """Compute the evidence-backed ``covered``/``unproven``/``missing`` buckets.

    Coverage = declared surface ∩ surfaces reached by a ``passed`` step in the
    newest persisted suite run (gap T-01).  ``unproven`` = referenced but not
    proven (and not allowlisted); ``missing`` = declared but referenced by no
    scenario (Absent).  Only real-confidence proofs count.
    """
    library = {scenario.name: scenario for scenario in scenarios}
    reached: dict[str, set[str]] = {surface: set() for surface in SURFACES}
    evidence_run: str | None = None
    confidence: str | None = None
    if runs_root is not None:
        evidence_run = latest_run(runs_root)
        if evidence_run is not None:
            record = _load_run_record(runs_root / evidence_run / "scenarios.json")
            if record is not None:
                confidence = _record_confidence(record)
                _collect_reached(record, library, file_map, reached)
    allow_path = Path(allowlist_path) if allowlist_path is not None else default_allowlist
    allow, allowlist_meta = _load_allowlist(allow_path, today)
    covered: dict[str, list[str]] = {}
    unproven: dict[str, list[str]] = {}
    missing: dict[str, list[str]] = {}
    allowlisted: dict[str, list[str]] = {}
    for surface in SURFACES:
        decl = declared[surface]
        proven = decl & reached[surface]
        absent = decl - used[surface]
        waived = decl & allow[surface]
        unproven[surface] = sorted((used[surface] & decl) - proven - waived)
        covered[surface] = sorted(proven)
        missing[surface] = sorted(absent)
        allowlisted[surface] = sorted(waived)
    return {
        "covered": covered,
        "unproven": unproven,
        "missing": missing,
        "allowlisted": allowlisted,
        "evidence_run": evidence_run,
        "evidence_confidence": confidence,
        "covered_count": sum(len(names) for names in covered.values()),
        "unproven_count": sum(len(names) for names in unproven.values()),
        "missing_count": sum(len(names) for names in missing.values()),
        "allowlist": allowlist_meta,
    }


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


def _parse_mode_map(runner_src: str) -> dict[str, list[str]]:
    """Extract ``_MODE_MAP`` (mode → gate-name list) from runner.py source.

    The module is read as text and parsed with :mod:`ast` — never imported —
    so the audit stays a static pass (guide §5.1) with no pipeline side
    effects; the constants are the single source of truth, so the declared
    surfaces cannot drift from the real mode definitions.  Gate-name list
    constants (``_<MODE>_GATE_NAMES: list[str] = [...]``) are resolved by
    name from the same module body.
    """
    tree = ast.parse(runner_src)
    gate_lists: dict[str, list[str]] = {}
    mode_map: dict[str, list[str]] = {}
    for node in tree.body:
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        if not isinstance(target, ast.Name):
            continue
        value = getattr(node, "value", None)
        if target.id.endswith("_GATE_NAMES") and isinstance(value, ast.List):
            gate_lists[target.id] = [
                element.value
                for element in value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
        elif target.id == "_MODE_MAP" and isinstance(value, ast.Dict):
            for key, val in zip(value.keys, value.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and isinstance(val, ast.Name)
                ):
                    mode_map[key.value] = gate_lists.get(val.id, [])
    return mode_map


def _declared_pipeline_surfaces(
    runner_path: str | Path | None,
    distribution_path: str | Path | None,
) -> tuple[list[str], list[str]]:
    """Declared gate and mode names from the pipeline source constants.

    Modes are the ``_MODE_MAP`` keys; gates are the union across that map's
    per-mode lists.  D-gates (D1-D7) are standalone distribution gates never
    referenced by a mode list, so the union is completed with the
    ``_gate_name`` class attributes in ``src/automedia/gates/distribution/*.py``
    — the declared set is 33 gates / 9 modes and drifts automatically with
    the source constants (issue #78 A2).
    """
    runner_src = _read_declared_source(runner_path, "src/automedia/pipelines/runner.py")
    mode_map = _parse_mode_map(runner_src)
    gates = set().union(*mode_map.values()) if mode_map else set()
    dist_dir = (
        _repo_root() / "src/automedia/gates/distribution"
        if distribution_path is None
        else Path(distribution_path)
    )
    if dist_dir.is_dir():
        for path in sorted(dist_dir.glob("*.py")):
            gates.update(_GATE_NAME_ASSIGN_RE.findall(path.read_text(encoding="utf-8")))
    return sorted(gates), sorted(mode_map)


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
