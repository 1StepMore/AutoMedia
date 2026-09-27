"""CLI surface for H0 review delivery — issue #105.

Covers the three ways a paused H0 gate is resolved from a terminal:
``automedia run --wait-for-review`` (same process), and
``automedia hitl pending|approve|reject`` (a separate process), plus the
mutual exclusion and validation rules on the new ``run`` flags.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.hooks.pipeline_history import PipelineHistoryHook
from automedia.pipelines.gate_types import PipelineProgress
from automedia.pipelines.review_prompt import start_interactive_review_prompt

runner = CliRunner()


def _seed_parked_project(root: Path, project_id: str = "cli105") -> Path:
    """Create a project whose history shows a run parked at H0."""
    project_dir = root / f"20260927_{project_id}"
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
    return project_dir


# -- automedia hitl pending --------------------------------------------------


def test_pending_lists_a_parked_project(tmp_path: Path) -> None:
    """Given a run parked at H0, `hitl pending` reports it."""
    _seed_parked_project(tmp_path)
    result = runner.invoke(app, ["--json", "hitl", "pending", "--base-dir", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 1
    assert data["pending"][0]["project_id"] == "cli105"
    assert data["pending"][0]["gate"] == "H0"


def test_pending_is_empty_when_nothing_is_parked(tmp_path: Path) -> None:
    """Given no paused run, `hitl pending` reports an empty list, not an error."""
    result = runner.invoke(app, ["--json", "hitl", "pending", "--base-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["count"] == 0


def test_pending_ignores_a_settled_gate(tmp_path: Path) -> None:
    """A gate with a terminal history row is not reported as parked."""
    project_dir = _seed_parked_project(tmp_path)
    PipelineHistoryHook().after_gate(
        "H0", {"project_dir": str(project_dir), "project_id": "cli105"}, {"passed": True}
    )
    result = runner.invoke(app, ["--json", "hitl", "pending", "--base-dir", str(tmp_path)])
    assert json.loads(result.stdout)["count"] == 0


# -- automedia hitl approve / reject -----------------------------------------


def test_approve_writes_a_decision_the_waiter_consumes(tmp_path: Path) -> None:
    """An approval from one process is honoured by the waiting process."""
    project_dir = _seed_parked_project(tmp_path)
    result = runner.invoke(
        app, ["--json", "hitl", "approve", "cli105", "--base-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["decision"] == "approve"

    progress = PipelineProgress(project_id="cli105")
    progress.on_gate_awaiting_hitl("H0")
    assert progress.wait_for_hitl(project_dir=str(project_dir), timeout=5.0) is True
    assert not (project_dir / ".hitl_state.json").exists()


def test_reject_is_delivered_to_the_waiter(tmp_path: Path) -> None:
    """A rejection from one process halts the waiting process."""
    project_dir = _seed_parked_project(tmp_path)
    result = runner.invoke(app, ["--json", "hitl", "reject", "cli105", "--base-dir", str(tmp_path)])
    assert result.exit_code == 0

    progress = PipelineProgress(project_id="cli105")
    progress.on_gate_awaiting_hitl("H0")
    assert progress.wait_for_hitl(project_dir=str(project_dir), timeout=5.0) is False


def test_approve_refuses_when_the_project_is_not_parked(tmp_path: Path) -> None:
    """No decision file may be planted for a run that is not waiting."""
    project_dir = tmp_path / "20260927_idle"
    (project_dir / ".automedia").mkdir(parents=True)
    (project_dir / "00_project_info.json").write_text(
        json.dumps({"project_id": "idle1", "topic": "t", "status": "draft"}), encoding="utf-8"
    )
    result = runner.invoke(app, ["--json", "hitl", "approve", "idle1", "--base-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert not (project_dir / ".hitl_state.json").exists()


def test_approve_refuses_a_second_undelivered_decision(tmp_path: Path) -> None:
    """A second decision must not overwrite one the waiter has not consumed."""
    project_dir = _seed_parked_project(tmp_path)
    first = runner.invoke(app, ["--json", "hitl", "approve", "cli105", "--base-dir", str(tmp_path)])
    assert first.exit_code == 0
    second = runner.invoke(app, ["--json", "hitl", "reject", "cli105", "--base-dir", str(tmp_path)])
    assert second.exit_code == 1
    delivered = json.loads((project_dir / ".hitl_state.json").read_text(encoding="utf-8"))
    assert delivered["decision"] == "approve"


def test_approve_reports_an_unknown_project(tmp_path: Path) -> None:
    """An unknown project id fails loudly instead of writing anywhere."""
    result = runner.invoke(app, ["--json", "hitl", "approve", "nope", "--base-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_decision_file_records_the_actor(tmp_path: Path) -> None:
    """The audit trail can tell a CLI decision from an MCP one."""
    project_dir = _seed_parked_project(tmp_path)
    runner.invoke(app, ["--json", "hitl", "approve", "cli105", "--base-dir", str(tmp_path)])
    delivered = json.loads((project_dir / ".hitl_state.json").read_text(encoding="utf-8"))
    assert delivered["actor"] == "cli"
    assert delivered["gate"] == "H0"
    assert delivered["at"]


# -- automedia run flag validation -------------------------------------------


def test_skip_review_and_wait_for_review_are_mutually_exclusive() -> None:
    """The two flags contradict, so the run must refuse before doing any work."""
    result = runner.invoke(
        app, ["run", "--topic", "t", "--brand", "b", "--skip-review", "--wait-for-review"]
    )
    assert result.exit_code == 1


def test_hitl_on_timeout_rejects_an_unknown_policy() -> None:
    """A typo in the timeout policy must fail loudly, not silently misconfigure."""
    result = runner.invoke(
        app, ["run", "--topic", "t", "--brand", "b", "--hitl-on-timeout", "aprove"]
    )
    assert result.exit_code == 1


def test_hitl_timeout_rejects_a_non_positive_value() -> None:
    """A zero or negative pause budget is a configuration error."""
    result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--hitl-timeout", "0"])
    assert result.exit_code == 1


# -- interactive prompt ------------------------------------------------------


def test_prompt_is_not_started_without_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A piped/CI stdin must never block on a read it cannot satisfy."""

    class _NotATty:
        @staticmethod
        def isatty() -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", _NotATty())
    assert start_interactive_review_prompt(PipelineProgress(project_id="p"), "H0", "p") is None


def test_prompt_approves_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answering 'a' resolves the pause in the same process."""

    class _Tty:
        @staticmethod
        def isatty() -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "a")
    progress = PipelineProgress(project_id="p")
    thread = start_interactive_review_prompt(progress, "H0", "p")
    assert thread is not None
    thread.join(timeout=5)
    assert progress._in_memory_decision() is True


def test_prompt_rejects_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answering 'r' rejects the pause in the same process."""

    class _Tty:
        @staticmethod
        def isatty() -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "r")
    progress = PipelineProgress(project_id="p")
    thread = start_interactive_review_prompt(progress, "H0", "p")
    assert thread is not None
    thread.join(timeout=5)
    assert progress._in_memory_decision() is False


def test_prompt_reasks_on_an_unrecognised_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo must not be read as approval; the prompt asks again."""

    class _Tty:
        @staticmethod
        def isatty() -> bool:
            return True

    answers: list[str] = ["maybe", "a"]
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: answers.pop(0))
    progress = PipelineProgress(project_id="p")
    thread = start_interactive_review_prompt(progress, "H0", "p")
    assert thread is not None
    thread.join(timeout=5)
    assert answers == []
    assert progress._in_memory_decision() is True


def test_prompt_gives_up_on_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """EOF ends the prompt without deciding, so the timeout policy applies."""

    class _Tty:
        @staticmethod
        def isatty() -> bool:
            return True

    def _raise_eof(*_a: Any, **_k: Any) -> str:
        raise EOFError

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("builtins.input", _raise_eof)
    progress = PipelineProgress(project_id="p")
    thread = start_interactive_review_prompt(progress, "H0", "p")
    assert thread is not None
    thread.join(timeout=5)
    assert progress._in_memory_decision() is None
