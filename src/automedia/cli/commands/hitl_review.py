"""``automedia hitl`` review delivery — resolve a pause from another process.

Split out of ``hitl.py`` so the preset/configuration surface and the review
delivery surface can each be read on their own.

A decision is delivered through the project's ``.hitl_state.json``, so it
reaches the run no matter where that run is. A process actively blocked at the
H0 human-review gate picks the file up on its next poll, and a process that has
already exited — a *parked* run that chose to return ``awaiting_review`` instead
of waiting — leaves the decision behind for the next run against that project to
consume.

These commands therefore only need the project's ``history.db`` to confirm a
gate is still awaiting a decision; they never require a live process. An
in-process approval from a second shell is unreachable, which is the gap this
module bridges.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import typer

from automedia.cli.commands.hitl import app
from automedia.cli.output import output_error, output_text

# ---------------------------------------------------------------------------
# hitl pending / approve / reject  (cross-process delivery, issue #105)
# ---------------------------------------------------------------------------


def _resolve_project_dir(project_id: str, base_dir: str | None) -> str | None:
    """Return the directory of *project_id* under *base_dir*, or ``None``."""
    from automedia.cli.commands.projects import _discover_projects

    root = base_dir or os.environ.get("AUTOMEDIA_PROJECTS_DIR", "") or os.getcwd()
    for project in _discover_projects(root):
        if project.get("project_id") == project_id:
            return project.get("_dir")
    return None


def _awaiting_gate(project_dir: str) -> str | None:
    """Return the gate a run is parked at, or ``None`` if it is not paused.

    A paused run has a ``<gate>:started`` history row with no terminal row for
    the same gate, because ``after_gate`` only fires once the decision resolves.
    That makes ``history.db`` a reliable cross-process "is a decision pending?"
    signal — an in-flight run holds the pause only in memory, and a parked run
    that has already exited holds nothing at all.
    """
    from automedia.hooks.pipeline_history import _read_history

    try:
        rows = _read_history(project_dir)
    except (OSError, ValueError):
        return None
    started: set[str] = set()
    settled: set[str] = set()
    for row in rows:
        action = str(row.get("action", ""))
        if ":" not in action:
            continue
        gate, _, status = action.partition(":")
        if status == "started":
            started.add(gate)
        elif status in ("completed", "failed"):
            settled.add(gate)
    pending = sorted(started - settled)
    return pending[-1] if pending else None


def _deliver(decision: str, project_id: str, base_dir: str | None) -> None:
    project_dir = _resolve_project_dir(project_id, base_dir)
    if project_dir is None:
        output_error(
            f"No project {project_id!r} found. Pass --base-dir if it lives "
            "outside the current projects directory."
        )
        raise typer.Exit(code=1)

    gate = _awaiting_gate(project_dir)
    if gate is None:
        output_error(
            f"Project {project_id!r} has no gate awaiting a decision, so there "
            f"is nothing to {decision}. Check the project id is right, then run "
            "`automedia hitl pending` to see which projects are paused."
        )
        raise typer.Exit(code=1)

    state_file = Path(project_dir) / ".hitl_state.json"
    if state_file.is_file():
        # The previous decision has not been consumed yet (by the blocked run,
        # or by the next run for a parked project). Overwriting it would
        # silently turn an approve into a reject (or vice versa) depending on
        # which consumer lands last.
        output_error(
            f"A decision for project {project_id!r} was already delivered and has "
            "not been consumed yet. Wait for the run to pick it up before "
            f"{decision}ing again."
        )
        raise typer.Exit(code=1)

    try:
        state_file.write_text(
            json.dumps(
                {
                    "decision": decision,
                    "gate": gate,
                    "actor": "cli",
                    "at": datetime.now(UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        output_error(f"Could not write {state_file}: {exc}")
        raise typer.Exit(code=1) from exc

    payload = {
        "status": "ok",
        "decision": decision,
        "project_id": project_id,
        "gate": gate,
        "state_file": str(state_file),
    }
    if output_text(None, data=payload):
        return
    typer.echo(f"{decision}d {gate} for project {project_id} ({project_dir})")


@app.command("pending")
def hitl_pending(
    base_dir: str | None = typer.Option(None, "--base-dir", help="Directory to scan for projects."),
) -> None:
    """List pipelines currently parked waiting for a human decision."""
    from automedia.cli.commands.projects import _discover_projects

    root = base_dir or os.environ.get("AUTOMEDIA_PROJECTS_DIR", "") or os.getcwd()
    waiting: list[dict[str, str]] = []
    for project in _discover_projects(root):
        project_dir = project.get("_dir")
        if not project_dir:
            continue
        gate = _awaiting_gate(project_dir)
        if gate is not None:
            waiting.append(
                {
                    "project_id": project.get("project_id", ""),
                    "gate": gate,
                    "topic": project.get("topic", ""),
                    "project_dir": project_dir,
                }
            )

    if output_text(None, data={"status": "ok", "count": len(waiting), "pending": waiting}):
        return
    if not waiting:
        typer.echo("No pipeline is waiting for a human decision.")
        return
    typer.echo(f"{'Project':<16} {'Gate':<6} Topic")
    typer.echo("-" * 60)
    for row in waiting:
        typer.echo(f"  {row['project_id']:<14} {row['gate']:<6} {row['topic'][:40]}")


@app.command("approve")
def hitl_approve(
    project_id: str = typer.Argument(..., help="Project ID parked at a review gate."),
    base_dir: str | None = typer.Option(
        None, "--base-dir", help="Directory to scan for the project."
    ),
) -> None:
    """Approve a pipeline paused at a review gate."""
    _deliver("approve", project_id, base_dir)


@app.command("reject")
def hitl_reject(
    project_id: str = typer.Argument(..., help="Project ID parked at a review gate."),
    base_dir: str | None = typer.Option(
        None, "--base-dir", help="Directory to scan for the project."
    ),
) -> None:
    """Reject a pipeline paused at a review gate."""
    _deliver("reject", project_id, base_dir)
