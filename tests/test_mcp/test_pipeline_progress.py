"""Tests for run_pipeline → get_pipeline_progress event propagation.

Verifies that ``run_pipeline`` passes the ``progress=`` kwarg to
``run_full_pipeline()`` so that gate progress events are recorded and
retrievable via ``get_pipeline_progress``.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from automedia.mcp.tools import get_pipeline_progress, run_pipeline
from automedia.pipelines.gate_engine import PipelineResult


class TestPipelineProgressPropagation:
    """Tests that progress events are correctly propagated."""

    def test_get_pipeline_progress_returns_events(self) -> None:
        """get_pipeline_progress returns non-empty events after run_pipeline.

        This test fails (RED) before the bugfix: ``progress=`` was not
        passed to ``run_full_pipeline()``, so the PipelineProgress in
        ``_pipeline_tracker`` never receives any events.
        """

        events_captured: list[dict] = []
        captured_progress = None

        def _mock_run_full_pipeline(topic: str, brand: str, **kwargs):
            """Mock that simulates gate progress on the passed progress."""
            nonlocal captured_progress
            progress = kwargs.get("progress")
            captured_progress = progress
            if progress is not None:
                progress.set_gate_names(["G0", "G1"])
                progress.on_gate_start("G0")
                progress.on_gate_end("G0", True, 0.5)
                progress.on_gate_start("G1")
                progress.on_gate_end("G1", False, 1.2, detail="test failure")
            return PipelineResult(
                project_id="mock_proj",
                topic=topic,
                success=True,
                outputs={},
            )

        with patch(
            "automedia.pipelines.runner.run_full_pipeline",
            side_effect=_mock_run_full_pipeline,
        ):
            result = run_pipeline(
                topic="Test progress topic",
                brand="test-brand",
                mode="text_only",
            )

        assert result["success"] is True
        project_id = result["project_id"]
        assert isinstance(project_id, str)
        assert len(project_id) > 0

        # Wait for the daemon background thread to finish
        time.sleep(0.3)

        progress_result = get_pipeline_progress(project_id)
        assert progress_result["success"] is True

        events = progress_result.get("events", [])
        assert len(events) > 0, (
            f"Expected at least 1 progress event, got {len(events)}. "
            "This likely means progress= was not passed to run_full_pipeline()."
        )

        # Verify event structure
        event = events[0]
        assert "gate_name" in event
        assert "status" in event
        assert "timestamp" in event

    def test_progress_events_have_gate_names_and_statuses(self) -> None:
        """Progress events contain expected gate names and statuses."""
        events_captured: list[dict] = []

        def _mock_run_full_pipeline(topic: str, brand: str, **kwargs):
            progress = kwargs.get("progress")
            if progress is not None:
                progress.set_gate_names(["G0", "G1"])
                progress.on_gate_start("G0")
                progress.on_gate_end("G0", True, 0.5)
            return PipelineResult(
                project_id="mock_proj",
                topic=topic,
                success=True,
                outputs={},
            )

        with patch(
            "automedia.pipelines.runner.run_full_pipeline",
            side_effect=_mock_run_full_pipeline,
        ):
            result = run_pipeline(
                topic="Test events detail",
                brand="test-brand",
                mode="text_only",
            )

        project_id = result["project_id"]
        time.sleep(0.3)

        progress_result = get_pipeline_progress(project_id)
        events = progress_result.get("events", [])

        # Find the G0 start event
        g0_starts = [e for e in events if e.get("gate_name") == "G0" and e.get("status") == "running"]
        assert len(g0_starts) >= 1, "Expected at least one G0 running event"

        # Find the G0 end event
        g0_ends = [e for e in events if e.get("gate_name") == "G0" and e.get("status") == "passed"]
        assert len(g0_ends) >= 1, "Expected at least one G0 passed event"

    def test_get_pipeline_progress_unknown_project(self) -> None:
        """get_pipeline_progress returns error for unknown project_id."""
        result = get_pipeline_progress("nonexistent")
        assert result["success"] is False
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"
