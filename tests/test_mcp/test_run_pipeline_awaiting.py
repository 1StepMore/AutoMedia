"""Tests for the MCP ``run_pipeline`` / ``run_batch`` awaiting-review contract.

An agent driving the MCP surface must **never** block on a human.  ``run_pipeline``
therefore passes ``block_on_hitl=False`` to ``run_full_pipeline``: a run that
reaches the H0 review gate parks (``status="awaiting_review"``) and the daemon
thread finishes immediately.  The parked state is surfaced through
``active_pipelines.json`` (read by ``list_active_pipelines``) instead of being
reported as ``"completed"``.  ``run_batch`` counts parked topics separately from
success and failure, and a caller may pass ``project_id=`` to resume a parked
project (forwarded as ``resume_project_id``).

All tests stub ``run_full_pipeline`` — no LLM calls, no real pipeline.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import pytest

from automedia.mcp.tools import _shared, list_active_pipelines, run_batch, run_pipeline
from automedia.mcp.tools._shared import _read_active_pipelines
from automedia.pipelines.gate_engine import PipelineResult

_TERMINAL_STATUSES = frozenset({"completed", "failed", "awaiting_review"})
_PipelineStatus = Literal["success", "failed", "partial", "awaiting_review"]
_Stub = Callable[..., PipelineResult]


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the session tracker at a temp file and start with a clean tracker."""
    monkeypatch.setattr(_shared, "_active_pipelines_path", tmp_path / "active_pipelines.json")
    with _shared._lock:
        _shared._pipeline_tracker.clear()
    yield
    with _shared._lock:
        _shared._pipeline_tracker.clear()


def _wait_for_terminal(project_id: str, timeout: float = 5.0) -> dict[str, Any]:
    """Wait for the background run's tracker entry to reach a terminal status."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = _read_active_pipelines().get(project_id)
        if entry is not None and entry.get("status") in _TERMINAL_STATUSES:
            return entry
        time.sleep(0.01)
    raise AssertionError(f"pipeline {project_id!r} never reached a terminal state")


def _parking_stub(
    seen: dict[str, Any],
    *,
    status: _PipelineStatus = "awaiting_review",
    blocking_delay: float = 3.0,
) -> _Stub:
    """A ``run_full_pipeline`` stub that only "blocks" when told to block.

    When ``block_on_hitl`` is not explicitly ``False`` the stub simulates a
    human wait by sleeping — so a caller that fails to pass
    ``block_on_hitl=False`` is caught by the elapsed-time assertion.
    """

    def _stub(topic: str, brand: str, **kwargs: Any) -> PipelineResult:
        seen.update(kwargs)
        if kwargs.get("block_on_hitl") is not False:
            time.sleep(blocking_delay)
        return PipelineResult(project_id=f"parked-{topic}", topic=topic, status=status)

    return _stub


class TestRunPipelineParks:
    def test_run_pipeline_does_not_block_at_h0(self) -> None:
        seen: dict[str, Any] = {}
        with patch(
            "automedia.pipelines.runner.run_full_pipeline",
            side_effect=_parking_stub(seen),
        ):
            start = time.monotonic()
            result = run_pipeline(topic="park me", brand="test-brand", mode="text_only")
            assert result["success"] is True
            project_id = result["project_id"]
            entry = _wait_for_terminal(project_id)
            elapsed = time.monotonic() - start

        assert seen.get("block_on_hitl") is False
        assert elapsed < 2.0, f"run_pipeline blocked for {elapsed:.2f}s"
        assert entry["status"] == "awaiting_review"

    def test_run_pipeline_status_is_not_reported_as_completed_when_parked(self) -> None:
        seen: dict[str, Any] = {}
        with patch(
            "automedia.pipelines.runner.run_full_pipeline",
            side_effect=_parking_stub(seen),
        ):
            result = run_pipeline(topic="park me too", brand="test-brand", mode="text_only")
            project_id = result["project_id"]
            entry = _wait_for_terminal(project_id)

        assert entry["status"] != "completed"
        assert entry["status"] == "awaiting_review"

        # list_active_pipelines must surface the parked run, not hide it.
        listed = list_active_pipelines()
        assert listed["success"] is True
        parked = [p for p in listed["pipelines"] if p["project_id"] == project_id]
        assert len(parked) == 1
        assert parked[0]["status"] == "awaiting_review"

    def test_project_id_is_forwarded_as_resume_project_id(self) -> None:
        seen: dict[str, Any] = {}
        with patch(
            "automedia.pipelines.runner.run_full_pipeline",
            side_effect=_parking_stub(seen),
        ):
            result = run_pipeline(
                topic="resume me",
                brand="test-brand",
                mode="text_only",
                project_id="abc123def456",
            )
            _wait_for_terminal(result["project_id"])

        assert seen.get("resume_project_id") == "abc123def456"
        assert seen.get("block_on_hitl") is False

    def test_empty_project_id_forwards_none(self) -> None:
        seen: dict[str, Any] = {}
        with patch(
            "automedia.pipelines.runner.run_full_pipeline",
            side_effect=_parking_stub(seen),
        ):
            result = run_pipeline(topic="fresh", brand="test-brand", mode="text_only")
            _wait_for_terminal(result["project_id"])

        assert "resume_project_id" in seen
        assert seen["resume_project_id"] is None

    def test_run_pipeline_returns_started_immediately(self) -> None:
        """The tool contract stays async: it returns a run handle right away."""
        seen: dict[str, Any] = {}
        with patch(
            "automedia.pipelines.runner.run_full_pipeline",
            side_effect=_parking_stub(seen),
        ):
            result = run_pipeline(topic="async", brand="test-brand", mode="text_only")
            _wait_for_terminal(result["project_id"])

        assert result["status"] == "started"
        assert isinstance(result["project_id"], str)


class TestRunBatchParks:
    def test_run_batch_reports_awaiting_review(self) -> None:
        seen: dict[str, Any] = {}
        statuses: Iterator[_PipelineStatus] = iter(["awaiting_review", "awaiting_review"])

        def _stub(topic: str, brand: str, **kwargs: Any) -> PipelineResult:
            seen.update(kwargs)
            if kwargs.get("block_on_hitl") is not False:
                time.sleep(3.0)
            return PipelineResult(project_id=f"batch-{topic}", topic=topic, status=next(statuses))

        with patch("automedia.pipelines.runner.run_full_pipeline", side_effect=_stub):
            start = time.monotonic()
            result = run_batch(topics=["a", "b"], brand="test-brand", mode="text_only")
            elapsed = time.monotonic() - start

        assert seen.get("block_on_hitl") is False
        assert elapsed < 2.0, f"run_batch blocked for {elapsed:.2f}s"
        assert result["total"] == 2
        assert result["awaiting"] == 2
        assert result["passed"] == 0
        assert result["failed"] == 0

    def test_run_batch_awaiting_not_counted_as_failed_or_passed(self) -> None:
        statuses: Iterator[_PipelineStatus] = iter(["success", "awaiting_review", "failed"])

        def _stub(topic: str, brand: str, **kwargs: Any) -> PipelineResult:
            _ = kwargs
            return PipelineResult(project_id=f"mix-{topic}", topic=topic, status=next(statuses))

        with patch("automedia.pipelines.runner.run_full_pipeline", side_effect=_stub):
            result = run_batch(
                topics=["ok", "parked", "broken"],
                brand="test-brand",
                mode="text_only",
            )

        assert result["total"] == 3
        assert result["passed"] == 1
        assert result["awaiting"] == 1
        assert result["failed"] == 1
