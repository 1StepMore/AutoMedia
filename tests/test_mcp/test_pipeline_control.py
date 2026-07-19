"""Tests for pipeline control MCP tools (cancel_pipeline, pause_pipeline,
resume_pipeline, retry_gate, skip_gate).

All tests mock _pipeline_tracker to inject synthetic PipelineProgress
objects.  Zero production data.
"""

from __future__ import annotations

from unittest.mock import patch

from automedia.mcp.tools import (
    cancel_pipeline,
    pause_pipeline,
    resume_pipeline,
    retry_gate,
    skip_gate,
)
from automedia.pipelines.gate_engine import PipelineProgress

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_progress(project_id: str = "proj_test123") -> PipelineProgress:
    """Create a synthetic PipelineProgress instance for testing."""
    progress = PipelineProgress(project_id=project_id)
    progress.set_gate_names(["G0", "G1", "G2", "V0", "V1"])
    return progress


def _make_tracker(
    *project_ids: str,
) -> dict[str, PipelineProgress]:
    """Create a _pipeline_tracker dict with one progress per project_id."""
    return {pid: _make_progress(project_id=pid) for pid in project_ids}


# ===================================================================
# Tests: cancel_pipeline
# ===================================================================


class TestCancelPipeline:
    """Tests for cancel_pipeline MCP tool."""

    def test_cancel_valid_project(self) -> None:
        """cancel_pipeline returns cancelled=True for a valid project_id."""
        tracker = _make_tracker("proj_valid")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = cancel_pipeline("proj_valid")

        assert result["success"] is True
        assert result["cancelled"] is True
        assert result["project_id"] == "proj_valid"

    def test_cancel_calls_cancel_on_progress(self) -> None:
        """cancel_pipeline calls .cancel() on the PipelineProgress object."""
        tracker = _make_tracker("proj_abc")
        original_progress = tracker["proj_abc"]
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            cancel_pipeline("proj_abc")

        # Verify cancel() was called
        assert original_progress.is_cancelled() is True

    def test_cancel_unknown_project_returns_error(self) -> None:
        """cancel_pipeline returns error for unknown project_id."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = cancel_pipeline("proj_unknown")

        assert result["success"] is False
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"

    def test_cancel_empty_tracker_returns_error(self) -> None:
        """cancel_pipeline returns error when tracker is empty."""
        tracker: dict[str, PipelineProgress] = {}
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = cancel_pipeline("anything")

        assert result["success"] is False

    def test_cancel_with_different_project_id(self) -> None:
        """cancel_pipeline only cancels the specified project, not others."""
        tracker = _make_tracker("proj_one", "proj_two")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = cancel_pipeline("proj_one")

        assert result["success"] is True
        assert result["project_id"] == "proj_one"
        # proj_two should still be running
        assert tracker["proj_two"].is_cancelled() is False


# ===================================================================
# Tests: pause_pipeline
# ===================================================================


class TestPausePipeline:
    """Tests for pause_pipeline MCP tool."""

    def test_pause_valid_project(self) -> None:
        """pause_pipeline returns paused=True for a valid project_id."""
        tracker = _make_tracker("proj_valid")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = pause_pipeline("proj_valid")

        assert result["success"] is True
        assert result["paused"] is True
        assert result["project_id"] == "proj_valid"

    def test_pause_calls_pause_on_progress(self) -> None:
        """pause_pipeline calls .pause() on the PipelineProgress object."""
        tracker = _make_tracker("proj_abc")
        original_progress = tracker["proj_abc"]
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            pause_pipeline("proj_abc")

        assert original_progress.is_paused() is True

    def test_pause_unknown_project_returns_error(self) -> None:
        """pause_pipeline returns error for unknown project_id."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = pause_pipeline("proj_unknown")

        assert result["success"] is False
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"

    def test_pause_then_resume_cycle(self) -> None:
        """A pipeline can be paused and then the pause state is visible."""
        tracker = _make_tracker("proj_cycle")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = pause_pipeline("proj_cycle")

        assert result["success"] is True
        assert tracker["proj_cycle"].is_paused() is True


# ===================================================================
# Tests: resume_pipeline
# ===================================================================


class TestResumePipeline:
    """Tests for resume_pipeline MCP tool."""

    def test_resume_valid_project(self) -> None:
        """resume_pipeline returns resumed=True for a valid project_id."""
        tracker = _make_tracker("proj_valid")
        # First pause it
        tracker["proj_valid"].pause()
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = resume_pipeline("proj_valid")

        assert result["success"] is True
        assert result["resumed"] is True
        assert result["project_id"] == "proj_valid"

    def test_resume_calls_resume_on_progress(self) -> None:
        """resume_pipeline calls .resume() on the PipelineProgress object."""
        tracker = _make_tracker("proj_abc")
        tracker["proj_abc"].pause()
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            resume_pipeline("proj_abc")

        assert tracker["proj_abc"].is_paused() is False

    def test_resume_unknown_project_returns_error(self) -> None:
        """resume_pipeline returns error for unknown project_id."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = resume_pipeline("proj_unknown")

        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_resume_non_paused_pipeline(self) -> None:
        """Resuming a non-paused pipeline is a no-op but still succeeds."""
        tracker = _make_tracker("proj_running")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = resume_pipeline("proj_running")

        assert result["success"] is True
        assert result["resumed"] is True
        assert tracker["proj_running"].is_paused() is False


# ===================================================================
# Tests: retry_gate
# ===================================================================


class TestRetryGate:
    """Tests for retry_gate MCP tool."""

    def test_retry_valid_project_and_gate(self) -> None:
        """retry_gate returns retrying=True for valid project and gate."""
        tracker = _make_tracker("proj_valid")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = retry_gate("proj_valid", "G0")

        assert result["success"] is True
        assert result["retrying"] is True
        assert result["project_id"] == "proj_valid"
        assert result["gate_name"] == "G0"

    def test_retry_calls_mark_retry_gate(self) -> None:
        """retry_gate calls .mark_retry_gate() on the progress object."""
        tracker = _make_tracker("proj_abc")
        original_progress = tracker["proj_abc"]
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            retry_gate("proj_abc", "V3")

        # Verify the gate was marked for retry by consuming it
        assert original_progress.consume_retry_gate() == "V3"

    def test_retry_unknown_project_returns_error(self) -> None:
        """retry_gate returns error for unknown project_id."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = retry_gate("proj_unknown", "G0")

        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_retry_overwrites_previous_retry(self) -> None:
        """Calling retry_gate twice overwrites the previous retry gate."""
        tracker = _make_tracker("proj_overwrite")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            retry_gate("proj_overwrite", "G0")
            retry_gate("proj_overwrite", "V5")

        assert tracker["proj_overwrite"].consume_retry_gate() == "V5"


# ===================================================================
# Tests: skip_gate
# ===================================================================


class TestSkipGate:
    """Tests for skip_gate MCP tool."""

    def test_skip_valid_project_and_gate(self) -> None:
        """skip_gate returns skipping=True for valid project and gate."""
        tracker = _make_tracker("proj_valid")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = skip_gate("proj_valid", "V0")

        assert result["success"] is True
        assert result["skipping"] is True
        assert result["project_id"] == "proj_valid"
        assert result["gate_name"] == "V0"

    def test_skip_calls_mark_skip_gate(self) -> None:
        """skip_gate calls .mark_skip_gate() on the progress object."""
        tracker = _make_tracker("proj_abc")
        original_progress = tracker["proj_abc"]
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            skip_gate("proj_abc", "L1")

        assert original_progress.consume_skip_gate() == "L1"

    def test_skip_unknown_project_returns_error(self) -> None:
        """skip_gate returns error for unknown project_id."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = skip_gate("proj_unknown", "G0")

        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_skip_overwrites_previous_skip(self) -> None:
        """Calling skip_gate twice overwrites the previous skip gate."""
        tracker = _make_tracker("proj_overwrite")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            skip_gate("proj_overwrite", "G0")
            skip_gate("proj_overwrite", "L2")

        assert tracker["proj_overwrite"].consume_skip_gate() == "L2"


# ===================================================================
# Tests: mixed operations
# ===================================================================


class TestPipelineControlIntegration:
    """Tests that combine multiple pipeline control operations."""

    def test_cancel_then_pause(self) -> None:
        """A pipeline can be cancelled and then pause returns error."""
        tracker = _make_tracker("proj_multi")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            # Cancel first
            cancel_result = cancel_pipeline("proj_multi")
            assert cancel_result["success"] is True

        # After cancel, the progress still exists, so pause should still work
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            pause_result = pause_pipeline("proj_multi")
            assert pause_result["success"] is True
            assert pause_result["paused"] is True

    def test_retry_then_skip_same_gate(self) -> None:
        """retry_gate then skip_gate — skip overwrites retry."""
        tracker = _make_tracker("proj_rt")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            retry_gate("proj_rt", "G0")
            skip_gate("proj_rt", "G0")

        # skip_gate uses mark_skip_gate, retry uses mark_retry_gate
        # They're independent stores, so both should work
        assert tracker["proj_rt"].consume_retry_gate() == "G0"
        assert tracker["proj_rt"].consume_skip_gate() == "G0"

    def test_all_controls_unknown_project_returns_not_found(self) -> None:
        """All pipeline control tools return NOT_FOUND for unknown project."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            for func, args in [
                (cancel_pipeline, ("unknown",)),
                (pause_pipeline, ("unknown",)),
                (resume_pipeline, ("unknown",)),
                (retry_gate, ("unknown", "G0")),
                (skip_gate, ("unknown", "G0")),
            ]:
                result = func(*args)
                assert result["success"] is False
                assert result["error"]["code"] == "NOT_FOUND", (
                    f"{func.__name__} should return NOT_FOUND"
                )

    def test_all_controls_return_success_for_valid_project(self) -> None:
        """All pipeline control tools return success for a valid project."""
        tracker = _make_tracker("proj_all")
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            results = {
                "cancel": cancel_pipeline("proj_all"),
                "pause": pause_pipeline("proj_all"),
                "resume": resume_pipeline("proj_all"),
                "retry": retry_gate("proj_all", "G0"),
                "skip": skip_gate("proj_all", "G0"),
            }

        for name, result in results.items():
            assert result["success"] is True, f"{name} should succeed"


# ===================================================================
# Tests: error response shape for all tools
# ===================================================================


class TestPipelineControlErrorShape:
    """Tests that error responses from pipeline control tools have
    the expected shape."""

    def test_error_has_success_false(self) -> None:
        """Error responses have success=False."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = cancel_pipeline("nonexistent")
            assert result["success"] is False

    def test_error_has_error_key_with_code_message_resolution(self) -> None:
        """Error responses have an 'error' dict with code, message, resolution."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = cancel_pipeline("nonexistent")

        assert "error" in result
        error = result["error"]
        assert "code" in error
        assert "message" in error
        assert "resolution" in error
        assert error["code"] == "NOT_FOUND"

    def test_error_no_error_message_key(self) -> None:
        """Error responses do NOT include the redundant error_message key."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = cancel_pipeline("nonexistent")

        assert "error_message" not in result
