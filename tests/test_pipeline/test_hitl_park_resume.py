"""H0 park/resume orchestration in the runner — issue #108.

Wave 1 taught the gate engine to *park* (``wait_for_hitl=False`` with no
delivered decision) and gave ``Project`` a way to restore a persisted identity.
The runner still (a) minted a fresh project on every call, (b) unconditionally
deleted ``.hitl_state.json`` at run start, and (c) folded a parked run into
``"success"``/``"partial"``.  These tests pin the runner-level contract that
closes those three gaps.

The module pre-imports the gate engine on purpose: it pulls in the gate
registry and the LLM client (a multi-second import), and the non-TTY test's
``elapsed < 2.0`` assertion must measure parking, not a one-off import.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import automedia.pipelines.gate_engine  # noqa: F401 — warm heavy imports before timing
from automedia.core.project import Project
from automedia.pipelines.gate_engine import PipelineResult
from automedia.pipelines.gate_types import PipelineProgress
from automedia.pipelines.runner import run_full_pipeline

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class _AwaitingGate:
    """Stub H0 gate that always pauses for review.

    Duck-typed rather than a ``BaseGate`` subclass on purpose: subclassing
    auto-registers in the global ``GateRegistry`` singleton and leaks state into
    other test files.  ``GateEngine`` only touches ``gate_name``, ``execute``
    and ``failure_mode``.
    """

    gate_name = "STUB"
    failure_mode = "stop"

    def execute(self, gate_context: Any) -> dict[str, Any]:
        return {
            "passed": True,
            "gate": self.gate_name,
            "status": "awaiting_hitl",
            "timeout_s": 10.0,
        }


def _write_decision(project_dir: str, decision: str) -> None:
    (Path(project_dir) / ".hitl_state.json").write_text(
        json.dumps({"decision": decision}), encoding="utf-8"
    )


def _run(topic: str, brand: str, **kwargs: Any) -> PipelineResult:
    """Run the real pipeline with config and gate selection stubbed.

    ``_select_gates`` is replaced (rather than ``_build_gates_from_names``) so
    the timing test never pays the multi-second ``automedia.gates`` import
    inside the measured section.  Everything under test — project resolution,
    the stale-state sweep, and the engine wiring — lives in ``_run_pipeline``.
    """
    with (
        patch("automedia.core.config_loader.load_config", return_value={}),
        patch(
            "automedia.pipelines.runner._select_gates",
            return_value=(["STUB"], [_AwaitingGate()]),
        ),
        patch("automedia.pipelines.runner.start_interactive_review_prompt"),
    ):
        return run_full_pipeline(topic, brand, **kwargs)


@pytest.fixture()
def projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the runner at an isolated projects directory (also used by Project)."""
    monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path))
    return tmp_path


# -- parking is immediate, and the parked state wins over the video downgrade --


def test_non_tty_run_parks_immediately(projects_dir: Path) -> None:
    """A parked run reports ``awaiting_review`` at once, never ``partial``.

    ``video_only`` owes a video; with no V gate the success/partial derivation
    would downgrade the run to ``partial`` — unless the parked state wins.  The
    2s bound is the load-bearing assertion: a regression that waits out the
    review budget still passes a bare status check.
    """
    start = time.monotonic()
    result = _run("park now", "testbrand", mode="video_only", block_on_hitl=False)
    elapsed = time.monotonic() - start

    assert result.status == "awaiting_review"
    assert result.status != "partial"
    assert elapsed < 2.0, f"parked run took {elapsed:.1f}s — it blocked instead of parking"

    parked_rows = [entry for entry in result.gates_log if entry.gate_name == "STUB"]
    assert parked_rows and parked_rows[0].status == "awaiting_hitl", (
        "a parked gate must not be flattened to 'passed' in gates_log"
    )


def test_block_on_hitl_true_still_blocks(projects_dir: Path) -> None:
    """``block_on_hitl=True`` honours a pre-delivered approve decision."""
    parked = _run("block true", "testbrand", mode="text_only", block_on_hitl=False)
    assert parked.status == "awaiting_review"

    _write_decision(parked.project_dir, "approve")
    result = _run(
        "block true",
        "testbrand",
        mode="text_only",
        resume_project_id=parked.project_id,
        block_on_hitl=True,
        progress=PipelineProgress(project_id=parked.project_id),
    )

    assert result.status == "success"
    assert not (Path(parked.project_dir) / ".hitl_state.json").exists()


# -- resume reuses the parked project's identity (Blocker A) ------------------


def test_resume_project_reuses_existing_identity(projects_dir: Path) -> None:
    """Resuming must not mint a fresh ``project_id`` or a fresh directory."""
    parked = _run("reuse id", "testbrand", mode="text_only", block_on_hitl=False)

    resumed = _run(
        "reuse id",
        "testbrand",
        mode="text_only",
        resume_project_id=parked.project_id,
        block_on_hitl=False,
    )

    assert resumed.project_id == parked.project_id
    assert resumed.project_dir == parked.project_dir


# -- resume does not wipe a delivered decision (Blocker B) --------------------


def test_resume_preserves_a_delivered_decision(projects_dir: Path) -> None:
    """The stale-state sweep must not run on resume, or H0 re-parks forever."""
    parked = _run("preserve decision", "testbrand", mode="text_only", block_on_hitl=False)
    _write_decision(parked.project_dir, "approve")

    result = _run(
        "preserve decision",
        "testbrand",
        mode="text_only",
        resume_project_id=parked.project_id,
        block_on_hitl=False,
    )

    assert result.status == "success"
    assert not (Path(parked.project_dir) / ".hitl_state.json").exists()


def test_resume_without_a_decision_parks_again(projects_dir: Path) -> None:
    """With nothing delivered, resuming parks the run again."""
    parked = _run("park again", "testbrand", mode="text_only", block_on_hitl=False)

    resumed = _run(
        "park again",
        "testbrand",
        mode="text_only",
        resume_project_id=parked.project_id,
        block_on_hitl=False,
    )

    assert resumed.status == "awaiting_review"


def test_resume_with_reject_halts(projects_dir: Path) -> None:
    """A delivered rejection fails H0; the run is not reported as awaiting."""
    parked = _run("reject halts", "testbrand", mode="text_only", block_on_hitl=False)
    _write_decision(parked.project_dir, "reject")

    result = _run(
        "reject halts",
        "testbrand",
        mode="text_only",
        resume_project_id=parked.project_id,
        block_on_hitl=False,
    )

    assert result.status != "awaiting_review"
    assert result.status == "partial"
    assert not (Path(parked.project_dir) / ".hitl_state.json").exists()


def test_resume_unknown_project_id_raises_clear_error(projects_dir: Path) -> None:
    """An unknown id surfaces a failure whose message names the id.

    The runner converts unexpected errors to a ``status="failed"`` result
    instead of raising (see ``run_full_pipeline``'s contract), so the actionable
    message lands in ``result.error``.
    """
    result = _run(
        "unknown id",
        "testbrand",
        mode="text_only",
        resume_project_id="deadbeefcafe",
    )

    assert result.status == "failed"
    assert "deadbeefcafe" in (result.error or "")


# -- wait_for_review still implies blocking -----------------------------------


def test_wait_for_review_implies_blocking(projects_dir: Path) -> None:
    """``wait_for_review=True`` blocks and consumes a decision delivered mid-run.

    A ``threading.Timer`` writes the decision after the stale-state sweep has
    already run, so this exercises the blocking wait rather than the non-blocking
    poll.
    """
    project = Project.init("wait review", "testbrand")
    timer = threading.Timer(0.4, _write_decision, args=(project.project_dir, "approve"))
    timer.start()
    try:
        result = _run("wait review", "testbrand", mode="text_only", wait_for_review=True)
    finally:
        timer.join()

    assert result.status == "success"
    assert not (Path(project.project_dir) / ".hitl_state.json").exists()
