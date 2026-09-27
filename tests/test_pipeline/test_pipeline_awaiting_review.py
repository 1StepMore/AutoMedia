"""H0 "park instead of block" — issue #108 regression coverage.

Historically a gate returning ``awaiting_hitl`` could only *block*: the engine
called ``progress.wait_for_hitl`` and, when progress was ``None`` (the CLI
``--json`` path), the guard ``and progress`` skipped the pause entirely — the
run continued to success with the review never happening.

Issue #108 splits the two concerns:

* ``wait_for_hitl=True`` (default) — block until a human decides, exactly as
  before, so every existing caller/test is unchanged;
* ``wait_for_hitl=False`` — never block: consume an already-delivered decision
  if there is one, otherwise *park* the pipeline (``status="awaiting_review"``)
  so an external reviewer can decide later.

The elapsed assertions are load-bearing: a parked run must return at once, not
ride out the gate's own timeout budget.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from automedia.pipelines.gate_engine import GateEngine
from automedia.pipelines.gate_types import PipelineProgress

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _write_decision(project_dir: Path, decision: str) -> None:
    (project_dir / ".hitl_state.json").write_text(
        json.dumps({"decision": decision}), encoding="utf-8"
    )


class _AwaitingGate:
    """Stub gate that always pauses for review, like H0 does.

    Duck-typed rather than a ``BaseGate`` subclass on purpose: subclassing
    auto-registers in the global ``GateRegistry`` singleton, which would leak
    state into other test files.  ``GateEngine`` only ever touches
    ``gate_name``, ``execute`` and ``failure_mode``.
    """

    gate_name = "STUB"
    failure_mode = "stop"

    def __init__(self, on_timeout: str | None = None) -> None:
        self._on_timeout = on_timeout

    def execute(self, gate_context: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "passed": True,
            "gate": self.gate_name,
            "status": "awaiting_hitl",
            "timeout_s": 10.0,
        }
        if self._on_timeout is not None:
            result["on_timeout"] = self._on_timeout
        return result


def _context(tmp_path: Path) -> dict[str, Any]:
    return {"project_dir": str(tmp_path), "topic": "t", "brand": "b"}


# -- parking is immediate ----------------------------------------------------


def test_non_tty_park_returns_immediately(tmp_path: Path) -> None:
    """wait_for_hitl=False parks at once instead of blocking for the budget."""
    engine = GateEngine([_AwaitingGate()], wait_for_hitl=False)
    progress = PipelineProgress(project_id="park1")

    start = time.monotonic()
    _ok, results = engine.run(_context(tmp_path), progress=progress)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, "engine blocked instead of parking the gate"
    assert engine.hitl_awaiting is True
    assert results[0]["_hitl_awaiting"] is True
    assert results[0]["passed"] is True


def test_default_engine_still_waits(tmp_path: Path) -> None:
    """With the default wait_for_hitl=True the engine blocks and consumes a decision."""
    _write_decision(tmp_path, "approve")
    engine = GateEngine([_AwaitingGate()])
    progress = PipelineProgress(project_id="default-wait")

    _ok, results = engine.run(_context(tmp_path), progress=progress)

    assert engine.hitl_awaiting is False
    assert results[0].get("_hitl_awaiting") is not True
    assert results[0]["_hitl_approved"] is True
    assert not (tmp_path / ".hitl_state.json").exists(), "wait_for_hitl did not consume the file"


# -- a pre-delivered decision is honoured without waiting --------------------


def test_delivered_approval_is_consumed_without_waiting(tmp_path: Path) -> None:
    """wait_for_hitl=False + an approve file passes instantly."""
    _write_decision(tmp_path, "approve")
    engine = GateEngine([_AwaitingGate()], wait_for_hitl=False)
    progress = PipelineProgress(project_id="delivered-approve")

    start = time.monotonic()
    _ok, results = engine.run(_context(tmp_path), progress=progress)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0
    assert results[0]["passed"] is True
    assert results[0]["_hitl_approved"] is True
    assert engine.hitl_awaiting is False
    assert not (tmp_path / ".hitl_state.json").exists()


def test_delivered_rejection_is_consumed_without_waiting(tmp_path: Path) -> None:
    """wait_for_hitl=False + a reject file halts without waiting."""
    _write_decision(tmp_path, "reject")
    engine = GateEngine([_AwaitingGate()], wait_for_hitl=False)
    progress = PipelineProgress(project_id="delivered-reject")

    start = time.monotonic()
    _ok, results = engine.run(_context(tmp_path), progress=progress)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0
    assert results[0]["passed"] is False
    assert results[0]["_hitl_approved"] is False
    assert engine.hitl_awaiting is False
    assert not (tmp_path / ".hitl_state.json").exists()


# -- the `and progress` bug: progress=None must still park -------------------


def test_park_survives_progress_none(tmp_path: Path) -> None:
    """Regression: progress=None used to skip the pause and let the run succeed."""
    engine = GateEngine([_AwaitingGate()], wait_for_hitl=False)

    _ok, results = engine.run(_context(tmp_path), progress=None)

    assert engine.hitl_awaiting is True
    assert results[0]["_hitl_awaiting"] is True
    assert results[0]["passed"] is True
