"""``automedia pipeline`` — DAG export and pipeline state inspection.

Wave 1 of the graph-engineering-rollout: ``export-dag`` renders the canonical
gate DAG (``automedia.pipelines.dag.AUTO_GATE_DAG``) per pipeline mode as a
Markdown gate table plus a Graphviz DOT graph. With ``--project``, gates that
appear in the project's ``history.db`` are overlaid with a run marker.

Wave 3 adds ``state``: a read-only per-gate status view (passed/failed/pending
+ asset md5) for one project, aggregated by
``automedia.pipelines.state_view.aggregate_pipeline_state``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

import typer

from automedia.cli.commands.projects import _discover_projects
from automedia.cli.output import output_error
from automedia.hooks.pipeline_history import _read_history
from automedia.pipelines.dag import AUTO_GATE_DAG, GateNode, topological_order
from automedia.pipelines.runner import _MODE_MAP, _compose_gate_list
from automedia.pipelines.state_view import aggregate_pipeline_state

app = typer.Typer(
    name="pipeline",
    help="Pipeline DAG export and state inspection.",
    no_args_is_help=True,
)

# V0 may fork off CW in parallel with the copy track (DAG metadata only).
_PARALLEL_MARK = "\u2225"
# Run-overlay marker prefix for gates present in the project's history.db.
_RAN_MARK = "\u2713"

_TRACK_ORDER = ("copy", "video", "qa", "lifecycle")


# ---------------------------------------------------------------------------
# Rendering helpers — Markdown
# ---------------------------------------------------------------------------


def _visible_parents(node: GateNode, mode_set: set[str]) -> list[str]:
    """Return a gate's depends_on restricted to parents present in the mode."""
    return [p for p in node.depends_on if p in mode_set]


def _render_markdown(mode: str, ordered: list[str], ran_gates: set[str]) -> str:
    """Render one mode's DAG as a Markdown document.

    The gate table lists every mode gate in ``ordered`` (canonical
    ``_MODE_MAP``) order, annotated with the ``∥`` async-parallel marker on V0
    and ``✓`` run markers for gates that appear in the project history.
    """
    mode_set = set(ordered)
    lines: list[str] = [f"# Pipeline DAG — mode `{mode}`", ""]
    lines.append("Gate execution order (canonical, from `AUTO_GATE_DAG` via `topological_order`).")
    lines.append("")
    lines.append("| gate | track | depends_on | failure_mode |")
    lines.append("|------|-------|------------|--------------|")
    for gate in ordered:
        node = AUTO_GATE_DAG[gate]
        name = gate
        if node.async_parallel:
            name += f" {_PARALLEL_MARK}"
        if gate in ran_gates:
            name = f"{_RAN_MARK} {name}"
        parents = _visible_parents(node, mode_set)
        lines.append(
            f"| {name} | {node.track} | {', '.join(parents) or '—'} | {node.failure_mode} |"
        )
    lines.append("")

    lines.append("## Edges")
    lines.append("")
    for gate in ordered:
        node = AUTO_GATE_DAG[gate]
        for parent in _visible_parents(node, mode_set):
            arrow = " \u2192 "
            if node.async_parallel and parent == "CW":
                arrow = f" {_PARALLEL_MARK}\u2192 "
            lines.append(f"- {parent}{arrow}{gate}")
    lines.append("")

    if ran_gates:
        overlaid = [g for g in ordered if g in ran_gates]
        lines.append("## Run overlay")
        lines.append("")
        lines.append(
            f"Gates with entries in the project history (marked {_RAN_MARK}): "
            + (", ".join(overlaid) if overlaid else "(none of this mode ran)")
            + "."
        )
        lines.append("")

    lines.append("## Mermaid flowchart")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart TD")
    for gate in ordered:
        node = AUTO_GATE_DAG[gate]
        label = f"{gate} {_PARALLEL_MARK}" if node.async_parallel else gate
        lines.append(f'    {gate}["{label}"]')
    for gate in ordered:
        node = AUTO_GATE_DAG[gate]
        lines.extend(f"    {parent} --> {gate}" for parent in _visible_parents(node, mode_set))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering helpers — DOT
# ---------------------------------------------------------------------------


def _dot_id(token: str) -> str:
    """Quote a token into a valid DOT identifier when needed.

    Handles both gate names (``pre-gate``) and graph names (``image-carousel``).
    """
    if token.isalnum():
        return token
    return f'"{token}"'


def _render_dot(mode: str, ordered: list[str], ran_gates: set[str]) -> str:
    """Render one mode's DAG as a Graphviz DOT graph.

    Gates are grouped into per-track ``cluster_*`` subgraphs; edges are the
    DAG's ``depends_on`` edges restricted to the mode's gate set.
    """
    mode_set = set(ordered)
    out: list[str] = [f"digraph {_dot_id(mode)} {{"]

    by_track: dict[str, list[str]] = {track: [] for track in _TRACK_ORDER}
    for gate in ordered:
        by_track.setdefault(AUTO_GATE_DAG[gate].track, []).append(gate)

    for track in _TRACK_ORDER:
        gates = by_track.get(track)
        if not gates:
            continue
        out.append(f"    subgraph cluster_{track} {{")
        out.append(f'        label="{track}";')
        for gate in gates:
            node = AUTO_GATE_DAG[gate]
            label = f"{gate} {_PARALLEL_MARK}" if node.async_parallel else gate
            attrs = [f'label="{label}"']
            if gate in ran_gates:
                attrs.append("style=filled")
                attrs.append("fillcolor=lightgreen")
                attrs.append(f"comment=ran {gate}")
            out.append(f"        {_dot_id(gate)} [{', '.join(attrs)}];")
        out.append("    }")
    out.append("")

    for gate in ordered:
        node = AUTO_GATE_DAG[gate]
        for parent in _visible_parents(node, mode_set):
            mark = f" // async-parallel {_PARALLEL_MARK}" if node.async_parallel else ""
            out.append(f"    {_dot_id(parent)} -> {_dot_id(gate)};{mark}")
    out.append("}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# export-dag command
# ---------------------------------------------------------------------------


@app.callback()  # type: ignore[misc, unused-ignore]  # typer's decorator is untyped
def pipeline_root() -> None:
    """Pipeline DAG export and state inspection commands.

    Defining a callback promotes the single-command Typer app to a proper
    command group, so ``automedia pipeline export-dag ...`` resolves as a
    nested subcommand (the ``onboard`` module uses the same pattern).
    """


def _resolve_modes(mode: str | None, render_all: bool) -> list[str]:
    """Resolve ``--mode``/``--all`` into the list of modes to render.

    Reuses ``_compose_gate_list`` for validation so the error message is the
    exact ValueError the runner produces ("Unknown pipeline mode 'X'. Choose
    from: [...]").
    """
    if render_all:
        return list(_MODE_MAP)
    if mode is None:
        typer.echo(
            "Specify --mode <name> or --all. Valid modes: " + ", ".join(_MODE_MAP),
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        _compose_gate_list(mode)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    return [mode]


def _overlay_history_gates(project: str | None) -> set[str]:
    """Collect gate names recorded in a project's history.db (``--project``).

    History actions use the ``<gate>:<status>`` shape (e.g. ``"CW:completed"``);
    the gate name is the prefix before the first ``:``.
    """
    if not project:
        return set()
    rows: list[dict[str, Any]] = _read_history(project)
    return {str(row.get("action", "")).split(":", 1)[0] for row in rows if row.get("action")}


@app.command("export-dag")  # type: ignore[misc, unused-ignore]  # typer's decorator is untyped
def export_dag(
    mode: str | None = typer.Option(
        None,
        "--mode",
        "-m",
        help="Pipeline mode to render (see --all for the full list).",
    ),
    render_all: bool = typer.Option(False, "--all", help="Render all pipeline modes."),
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project directory; overlays gates recorded in its history.db.",
    ),
    out: str = typer.Option(".", "--out", "-o", help="Output directory for the rendered files."),
) -> None:
    """Export pipeline-mode gate DAGs as Markdown tables and DOT graphs."""
    if mode is not None and render_all:
        typer.echo("--mode and --all are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    modes = _resolve_modes(mode, render_all)
    ran_gates = _overlay_history_gates(project)
    os.makedirs(out, exist_ok=True)

    for mode_name in modes:
        ordered = topological_order(AUTO_GATE_DAG, _MODE_MAP[mode_name])
        with open(os.path.join(out, f"{mode_name}.md"), "w", encoding="utf-8") as fh:
            fh.write(_render_markdown(mode_name, ordered, ran_gates))
        with open(os.path.join(out, f"{mode_name}.dot"), "w", encoding="utf-8") as fh:
            fh.write(_render_dot(mode_name, ordered, ran_gates))
        typer.echo(f"Wrote {mode_name}.md and {mode_name}.dot to {out}")


# ---------------------------------------------------------------------------
# state command
# ---------------------------------------------------------------------------


def _resolve_project_dir(project_id: str, base_dir: str) -> str:
    """Find the project directory for *project_id* under *base_dir*.

    Mirrors ``history_cmd``: scan with ``_discover_projects`` and match on
    ``project_id``.  Exits 1 with an error message when not found.
    """
    try:
        projects = _discover_projects(base_dir)
    except (OSError, ValueError) as exc:
        output_error(f"Error scanning projects: {exc}", code=0)
        raise typer.Exit(code=1) from exc
    match = [p for p in projects if p.get("project_id") == project_id]
    if not match:
        typer.echo(f"Project {project_id!r} not found under {base_dir!r}.", err=True)
        raise typer.Exit(code=1)
    return str(match[0]["_dir"])


def _render_state_table(rows: list[dict[str, Any]]) -> str:
    """Render per-gate state rows as a track-grouped plain-text table."""
    tracks: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        tracks.setdefault(str(row["track"]), []).append(row)

    lines: list[str] = []
    for track in _TRACK_ORDER:
        track_rows = tracks.get(track)
        if not track_rows:
            continue
        lines.append(f"[{track}]")
        for row in track_rows:
            md5 = row["md5"] or "—"
            lines.append(f"  {row['gate']:<10} {row['status']:<8} md5={md5}")
        lines.append("")
    return "\n".join(lines).rstrip()


@app.command("state")  # type: ignore[misc, unused-ignore]  # typer's decorator is untyped
def pipeline_state(
    project_id: str = typer.Argument(..., help="Project ID (12-char hex)."),
    base_dir: str = typer.Option(
        ".", "--base-dir", "-d", help="Base directory to scan for projects."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Show the per-gate state (passed/failed/pending + md5) for a project."""
    project_dir = _resolve_project_dir(project_id, base_dir)
    rows = [asdict(r) for r in aggregate_pipeline_state(project_dir, "auto")]

    if json_output:
        typer.echo(json.dumps({"project_id": project_id, "gates": rows}, indent=2))
        return

    has_history = any(row["status"] != "pending" for row in rows)
    if not has_history:
        typer.echo("No history recorded for this project; all gates pending.")
    typer.echo(_render_state_table(rows))
