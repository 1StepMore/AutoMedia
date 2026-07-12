"""``automedia solution`` — Decision-layer workflow state management.

Subcommands
-----------
complete-node       Mark a node as completed in .solution-state.yaml
approve-node        Record a human approval for a node
next-node           Show the next pending node in the dependency graph
validate-artifact   Validate an artifact file against a JSON schema
preflight-check     Check whether all prerequisites for the next phase are complete
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
import yaml

from automedia.cli.output import OutputMode, get_output_mode, output_error_json, output_json
from automedia.decision import dependency
from automedia.decision.preflight import check as _preflight_check
from automedia.decision.schema_validator import validate_artifact as validate_schema

app = typer.Typer(name="solution", help="Manage decision-layer workflow state.")

_STATE_FILE = Path(".solution-state.yaml")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_state() -> dict[str, Any]:
    return {
        "brand": None,
        "completed_nodes": [],
        "completions": [],
    }


def _load_state() -> dict[str, Any]:
    """Load .solution-state.yaml or return a default empty state."""
    if _STATE_FILE.is_file():
        with open(_STATE_FILE, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or _default_state()
    return _default_state()


def _write_state(state: dict[str, Any]) -> None:
    """Write state dict to .solution-state.yaml."""
    with open(_STATE_FILE, "w", encoding="utf-8") as fh:
        yaml.dump(state, fh, default_flow_style=False, sort_keys=False)


def _resolve_node_id(node_name: str) -> int | None:
    """Return node_id for a node *name*, or ``None`` if not found."""
    for n in dependency.list_all_nodes():
        if n.get("name") == node_name:
            return n.get("node_id")
    return None


def _resolve_name_from_id(node_id: int) -> str | None:
    """Return node name for a node *id*, or ``None``."""
    n = dependency.get_node(node_id)
    return n.get("name") if n else None


def _validate_mode(mode: str) -> None:
    """Exit with error if *mode* is not supported."""
    if mode not in ("build", "scale"):
        typer.secho(
            f"Invalid mode: {mode!r}. Use 'build' or 'scale'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# solution complete-node
# ---------------------------------------------------------------------------


@app.command("complete-node")
def complete_node(
    node: str = typer.Option(
        ...,
        "--node",
        "-n",
        help="Node name (e.g. brand_questionnaire).",
    ),
    brand: str = typer.Option(
        ...,
        "--brand",
        "-b",
        help="Brand identifier.",
    ),
) -> None:
    """Mark a node as completed in .solution-state.yaml.

    Validates the node exists in the dependency graph (IDs 1–27),
    appends it to ``completed_nodes`` (with deduplication), and writes
    the updated state back to disk.
    """
    is_json = get_output_mode() == OutputMode.JSON
    node_id = _resolve_node_id(node)
    if node_id is None:
        all_names = sorted(n.get("name", "?") for n in dependency.list_all_nodes())
        msg = f"Unknown node: {node!r}.\nValid nodes: {', '.join(all_names)}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not (1 <= node_id <= 27):
        msg = f"Invalid node ID {node_id} for {node!r} — expected 1-27."
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        state = _load_state()
    except Exception as exc:
        msg = f"Failed to read state file: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    state["brand"] = brand

    completed = state.setdefault("completed_nodes", [])
    already_done = node in completed
    if not already_done:
        completed.append(node)

    try:
        _write_state(state)
    except Exception as exc:
        msg = f"Failed to write state file: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if is_json:
        output_json({
            "status": "ok",
            "node": node,
            "node_id": node_id,
            "already_completed": already_done,
        })
    elif already_done:
        typer.echo(f"Node {node!r} already in completed_nodes (no change).")
    else:
        typer.secho(
            f"Node {node!r} (id={node_id}) marked as completed.",
            fg=typer.colors.GREEN,
        )


# ---------------------------------------------------------------------------
# solution approve-node
# ---------------------------------------------------------------------------


@app.command("approve-node")
def approve_node(
    node: str = typer.Option(
        ...,
        "--node",
        "-n",
        help="Node name to approve.",
    ),
    by: str = typer.Option(
        ...,
        "--by",
        help="User identifier (who approved).",
    ),
) -> None:
    """Record a human approval for a node in .solution-state.yaml.

    Adds or updates an approval record with the current UTC timestamp
    and also ensures the node is listed in ``completed_nodes``.
    """
    is_json = get_output_mode() == OutputMode.JSON
    node_id = _resolve_node_id(node)
    if node_id is None:
        msg = f"Unknown node: {node!r}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        state = _load_state()
    except Exception as exc:
        msg = f"Failed to read state file: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    timestamp = datetime.now(UTC).isoformat()
    completions = state.setdefault("completions", [])

    # Update existing approval record for this node
    updated = False
    for rec in completions:
        if rec.get("node") == node:
            rec["by"] = by
            rec["timestamp"] = timestamp
            updated = True
            break

    if not updated:
        completions.append({"node": node, "by": by, "timestamp": timestamp})

    # Also ensure it's in completed_nodes
    if node not in state.setdefault("completed_nodes", []):
        state["completed_nodes"].append(node)

    try:
        _write_state(state)
    except Exception as exc:
        msg = f"Failed to write state file: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if is_json:
        output_json({
            "status": "ok",
            "node": node,
            "approved_by": by,
            "timestamp": timestamp,
        })
    else:
        typer.secho(
            f"Approval recorded for node {node!r} by {by!r} at {timestamp}.",
            fg=typer.colors.GREEN,
        )


# ---------------------------------------------------------------------------
# solution next-node
# ---------------------------------------------------------------------------


@app.command("next-node")
def next_node(
    mode: str = typer.Option(
        "build",
        "--mode",
        "-m",
        help="Pipeline mode: 'build' or 'scale'.",
    ),
    block_on_hitl: bool = typer.Option(
        False,
        "--block-on-hitl",
        help="Exit 1 if the next node requires human intervention per HITL config.",
    ),
) -> None:
    """Show the next pending node in the dependency graph.

    Scans all nodes for the selected *mode*, finds the first node
    whose dependencies are satisfied but which has not yet been
    completed, and prints its name and phase.

    When ``--block-on-hitl`` is passed and the next node is classified
    as ``"human"`` by the active HITL preset, the command exits with
    code 1 (useful for CI gating).
    """
    is_json = get_output_mode() == OutputMode.JSON
    _validate_mode(mode)

    try:
        state = _load_state()
    except Exception as exc:
        msg = f"Failed to read state file: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    completed_names: set[str] = set(state.get("completed_nodes", []))

    # Build a name → node_id lookup
    name_to_id: dict[str, int] = {}
    for n in dependency.list_all_nodes():
        name = n.get("name")
        nid = n.get("node_id")
        if name and nid:
            name_to_id[name] = nid

    # Collect nodes for this mode (including "both")
    mode_nodes = [n for n in dependency.list_all_nodes() if n.get("mode") in (mode, "both")]

    # Find the first pending node with all deps satisfied
    next_node_info: dict[str, Any] | None = None
    for n in sorted(mode_nodes, key=lambda x: x.get("node_id", 999)):
        name = n.get("name", "")
        if name in completed_names:
            continue

        # Resolve dependency IDs to names and check coverage
        dep_ids: list[int] = n.get("dependencies", [])
        dep_names: set[str] = set()
        for did in dep_ids:
            dep_name = _resolve_name_from_id(did)
            if dep_name:
                dep_names.add(dep_name)

        if dep_names and not dep_names.issubset(completed_names):
            continue

        next_node_info = n
        break

    if next_node_info is None:
        if is_json:
            output_json({"status": "ok", "next_node": None, "message": "All nodes completed."})
        else:
            typer.echo("All nodes completed. No pending node.")
        return

    # --block-on-hitl gating
    _is_human = False
    if block_on_hitl:
        try:
            from automedia.hitl.config import HITLConfig

            _preset_name = "test_automated"
            _active_path = Path.home() / ".automedia" / "hitl" / "active_preset.yaml"
            if _active_path.is_file():
                import yaml as _yaml

                with open(_active_path, encoding="utf-8") as _fh:
                    _data = _yaml.safe_load(_fh)
                if isinstance(_data, dict) and _data.get("active_preset"):
                    _preset_name = _data["active_preset"]

            _config = HITLConfig(preset_name=_preset_name)
            _is_human = _config.get_executor(next_node_info["name"]) == "human"
        except Exception:  # noqa: S110, BLE001 — HITL module unavailable, assume agent
            pass  # HITL module unavailable or node not configured — assume agent

    if is_json:
        data: dict[str, Any] = {
            "status": "ok",
            "next_node": {
                "name": next_node_info["name"],
                "node_id": next_node_info["node_id"],
                "phase": next_node_info.get("phase", "?"),
                "mode": next_node_info.get("mode", "?"),
                "requires_human": _is_human,
            },
        }
        output_json(data)
        if _is_human and block_on_hitl:
            raise typer.Exit(code=1)
        return

    typer.echo(f"Next node: {next_node_info['name']!r} (id={next_node_info['node_id']})")
    typer.echo(f"  Phase : {next_node_info.get('phase', '?')}")
    typer.echo(f"  Mode  : {next_node_info.get('mode', '?')}")

    if _is_human:
        typer.secho(
            f"Next node {next_node_info['name']!r} requires human intervention (HITL).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# solution validate-artifact
# ---------------------------------------------------------------------------


@app.command("validate-artifact")
def validate_artifact(
    schema: str = typer.Option(
        ...,
        "--schema",
        "-s",
        help="Schema name (without .json extension, e.g. brand_dna).",
    ),
    path: str = typer.Argument(
        ...,
        help="Path to the artifact JSON or YAML file.",
    ),
) -> None:
    """Validate an artifact file against a named JSON schema.

    Supports both ``.json`` and ``.yaml`` / ``.yml`` input files.
    Prints a detailed validation report and exits with code 1 on
    failure.
    """
    is_json = get_output_mode() == OutputMode.JSON
    data_path = Path(path)
    if not data_path.is_file():
        msg = f"File not found: {path}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Parse the artifact file
    try:
        raw = data_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) if data_path.suffix in (".yaml", ".yml") else json.loads(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        msg = f"Failed to parse {path}: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if not isinstance(data, dict):
        msg = "Artifact data must be a JSON object / dictionary."
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Run schema validation
    try:
        result = validate_schema(schema, data)
    except Exception as exc:
        msg = f"Validation error: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if result.get("valid"):
        if is_json:
            output_json({"status": "ok", "valid": True, "schema": schema, "path": path})
        else:
            typer.secho(
                f"Artifact '{path}' is valid against schema '{schema}'.",
                fg=typer.colors.GREEN,
            )
    else:
        errors = result.get("errors", [])
        if is_json:
            output_json({"status": "error", "valid": False, "schema": schema, "errors": errors})
        else:
            typer.secho(
                f"Artifact '{path}' is INVALID against schema '{schema}':",
                fg=typer.colors.RED,
            )
            for err in errors:
                typer.secho(f"  - {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# solution preflight-check
# ---------------------------------------------------------------------------


@app.command("preflight-check")
def preflight_check(
    next_phase: str = typer.Option(
        ...,
        "--next-phase",
        help="Target phase to transition to (e.g. '2', '3', '4').",
    ),
    mode: str = typer.Option(
        "build",
        "--mode",
        "-m",
        help="Pipeline mode: 'build' or 'scale'.",
    ),
) -> None:
    """Check whether all prerequisites for the next phase are complete.

    Reads the current state from ``.solution-state.yaml`` and delegates
    to ``automedia.decision.preflight.check()``.  Exits with code 1
    and lists any missing nodes.
    """
    is_json = get_output_mode() == OutputMode.JSON
    _validate_mode(mode)

    try:
        state = _load_state()
    except Exception as exc:
        msg = f"Failed to read state file: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    # Map completed node names to IDs for the preflight check API
    completed_names: set[str] = set(state.get("completed_nodes", []))
    completed_ids: set[int] = set()
    for n in dependency.list_all_nodes():
        if n.get("name") in completed_names:
            nid = n.get("node_id")
            if nid is not None:
                completed_ids.add(nid)

    try:
        warnings = _preflight_check(next_phase, mode, completed_ids)
    except Exception as exc:
        msg = f"Preflight check error: {exc}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if not warnings:
        if is_json:
            output_json({
                "status": "ok",
                "phase": next_phase,
                "mode": mode,
                "warnings": [],
            })
        else:
            typer.secho(
                f"Preflight OK — all prerequisites for phase {next_phase} ({mode}) are complete.",
                fg=typer.colors.GREEN,
            )
        return

    if is_json:
        output_json({
            "status": "error",
            "phase": next_phase,
            "mode": mode,
            "warnings": warnings,
        })
    else:
        typer.secho(
            f"Preflight WARNINGS for phase {next_phase} ({mode} mode):",
            fg=typer.colors.YELLOW,
        )
        for w in warnings:
            typer.echo(f"  - {w}")
    raise typer.Exit(code=1)
