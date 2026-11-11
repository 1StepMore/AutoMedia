"""Parked-project H0 decisions — issue #108.

``automedia hitl approve|reject`` delivers a decision through the project's
``.hitl_state.json``, so it must resolve a pause for a project whose run has
already exited after deciding to return ``awaiting_review`` (parked) — not only
for a run whose process is still blocked at the gate. ``_awaiting_gate`` reads
that fact from ``history.db`` (a ``<gate>:started`` row with no terminal row),
which is why no live process is needed.

These tests seed that history on disk and assert the CLI decides on it. They
pin the contract so a future change cannot silently reintroduce a liveness
requirement.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.hooks.pipeline_history import PipelineHistoryHook

runner = CliRunner()


def _seed_project(root: Path, project_id: str, *, settle_h0: bool = False) -> Path:
    """Create a project whose history shows a run parked at H0.

    With ``settle_h0=True`` the H0 gate also gets its terminal row, so the gate
    is no longer awaiting a decision.
    """
    project_dir = root / f"20260928_{project_id}"
    (project_dir / ".automedia").mkdir(parents=True)
    (project_dir / "00_project_info.json").write_text(
        json.dumps({"project_id": project_id, "topic": "review me", "status": "draft"}),
        encoding="utf-8",
    )
    hook = PipelineHistoryHook()
    ctx = {"project_dir": str(project_dir), "project_id": project_id}
    hook.before_gate("G6", ctx)
    hook.after_gate("G6", ctx, {"passed": True})
    hook.before_gate("H0", ctx)
    if settle_h0:
        hook.after_gate("H0", ctx, {"passed": True})
    return project_dir


def _state_file(project_dir: Path) -> Path:
    return project_dir / ".hitl_state.json"


def test_approve_accepts_a_parked_project(tmp_path: Path) -> None:
    """A run that exited after returning ``awaiting_review`` can still be approved.

    No process is waiting: the run is represented only by its history rows.
    """
    project_dir = _seed_project(tmp_path, "parked-approve")
    result = runner.invoke(
        app, ["--json", "hitl", "approve", "parked-approve", "--base-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    delivered = json.loads(_state_file(project_dir).read_text(encoding="utf-8"))
    assert delivered["decision"] == "approve"
    assert delivered["gate"] == "H0"


def test_reject_accepts_a_parked_project(tmp_path: Path) -> None:
    """A rejected parked project is recorded as ``reject`` for the next run."""
    project_dir = _seed_project(tmp_path, "parked-reject")
    result = runner.invoke(
        app, ["--json", "hitl", "reject", "parked-reject", "--base-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    delivered = json.loads(_state_file(project_dir).read_text(encoding="utf-8"))
    assert delivered["decision"] == "reject"
    assert delivered["gate"] == "H0"


def test_settled_gate_is_not_awaiting(tmp_path: Path) -> None:
    """A gate with a terminal history row must be refused, and no file written.

    This is the guard that keeps a decision from landing on an already-settled
    gate; it must survive the parked-project support.
    """
    project_dir = _seed_project(tmp_path, "settled", settle_h0=True)
    result = runner.invoke(
        app, ["--json", "hitl", "approve", "settled", "--base-dir", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert not _state_file(project_dir).exists()
    error = json.loads(result.stdout)["error"]
    assert "no gate awaiting a decision" in error
    assert "project id is right" in error


def test_unknown_project_is_refused(tmp_path: Path) -> None:
    """An unknown project id fails loudly and writes nothing anywhere."""
    result = runner.invoke(app, ["--json", "hitl", "approve", "ghost", "--base-dir", str(tmp_path)])
    assert result.exit_code != 0
    error = json.loads(result.stdout)["error"]
    assert "No project" in error
    assert not list(tmp_path.glob("*/.hitl_state.json"))


# ---------------------------------------------------------------------------
# Reruns of the same project directory — issue #507
# ---------------------------------------------------------------------------
#
# A rerun against the same directory writes a new project id into
# ``00_project_info.json`` and appends its own rows to the shared
# ``history.db``. The started/settled merge must therefore be scoped to the
# project id of the run being asked about — a terminal row from an earlier
# round must not settle a later round's ``started`` row.


def _awaiting_gate(project_dir: Path, project_id: str) -> str | None:
    from automedia.cli.commands.hitl_review import _awaiting_gate as awaiting_gate

    return awaiting_gate(str(project_dir), project_id)


def test_earlier_round_settled_h0_does_not_settle_later_round(tmp_path: Path) -> None:
    """A terminal H0 row from run A must not settle run B's H0 ``started`` row.

    This is the #507 report scenario: round one parked, was approved, settled;
    a rerun in the same directory parks again and must still be approvable.
    """
    project_dir = _seed_project(tmp_path, "round-one", settle_h0=True)
    hook = PipelineHistoryHook()
    hook.before_gate("H0", {"project_dir": str(project_dir), "project_id": "round-two"})
    assert _awaiting_gate(project_dir, "round-two") == "H0"


def test_awaiting_gate_is_none_for_a_settled_project(tmp_path: Path) -> None:
    """A project whose H0 has a terminal row and no new ``started`` is not parked."""
    project_dir = _seed_project(tmp_path, "round-one", settle_h0=True)
    assert _awaiting_gate(project_dir, "round-one") is None


def test_awaiting_gate_ignores_other_projects_completed_row(tmp_path: Path) -> None:
    """A ``H0:completed`` row belonging to another project settles nothing here."""
    project_dir = _seed_project(tmp_path, "round-one")
    hook = PipelineHistoryHook()
    hook.after_gate(
        "H0", {"project_dir": str(project_dir), "project_id": "another-project"}, {"passed": True}
    )
    assert _awaiting_gate(project_dir, "round-one") == "H0"


def test_approve_scoped_to_the_rerun_in_the_same_directory(tmp_path: Path) -> None:
    """Same directory, round one approved and settled: the rerun is approvable.

    End-to-end per #507 DoD: round one ran, parked, was approved and settled;
    the rerun rewrites the project info with a new id and parks at H0 again —
    ``hitl approve`` with the *new* id must succeed, and ``hitl pending`` must
    list it.
    """
    project_dir = _seed_project(tmp_path, "round-one", settle_h0=True)
    hook = PipelineHistoryHook()
    ctx = {"project_dir": str(project_dir), "project_id": "round-two"}
    hook.before_gate("H0", ctx)
    # The rerun rewrites the project info with the new id (same directory).
    (project_dir / "00_project_info.json").write_text(
        json.dumps({"project_id": "round-two", "topic": "review me again", "status": "draft"}),
        encoding="utf-8",
    )

    pending = runner.invoke(app, ["--json", "hitl", "pending", "--base-dir", str(tmp_path)])
    assert pending.exit_code == 0
    listed = json.loads(pending.stdout)["pending"]
    assert [(p["project_id"], p["gate"]) for p in listed] == [("round-two", "H0")]

    result = runner.invoke(
        app, ["--json", "hitl", "approve", "round-two", "--base-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    delivered = json.loads(_state_file(project_dir).read_text(encoding="utf-8"))
    assert delivered["decision"] == "approve"
    assert delivered["gate"] == "H0"
