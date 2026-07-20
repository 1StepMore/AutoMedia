"""Tests for structured error wrapping in MCP tool functions.

Verifies that public tool functions in tools.py return dicts with proper
error shape on failure, and use success_response / error_response helpers.
All tests use mocks — zero production data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.exceptions import AutoMediaError
from automedia.mcp.tools import (
    archive_project,
    batch_run,
    cancel_pipeline,
    get_pipeline_progress,
    get_pipeline_status,
    list_projects,
    pause_pipeline,
    resume_pipeline,
    retry_gate,
    run_pipeline,
    run_pipeline_from_strategy,
    search_assets,
    skip_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_success_shape(result: dict[str, object]) -> None:
    """Assert that *result* has the expected success response shape."""
    assert "success" in result, "Success response should have 'success' key"
    # Success responses should have success=True or already have success in data


def _assert_error_shape(result: dict[str, object]) -> None:
    """Assert that *result* has the expected error response shape."""
    assert result["success"] is False
    assert "error" in result, "Error response should have 'error' key"
    error = result["error"]
    assert isinstance(error, dict), "Error should be a dict"
    assert "code" in error, "Error should have 'code'"
    assert "message" in error, "Error should have 'message'"
    assert "resolution" in error, "Error should have 'resolution'"
    assert "error_message" not in result


# ===================================================================
# Tests: error paths via parameter validation
# ===================================================================


class TestRunPipelineErrors:
    """Tests for run_pipeline error paths."""

    def test_invalid_mode_returns_error_shape(self) -> None:
        """run_pipeline with invalid mode returns proper error shape."""
        result = run_pipeline(topic="test", brand="brand", mode="bogus_mode")

        _assert_error_shape(result)
        assert result["error"]["code"] == "INVALID_PARAM"

    def test_empty_topic_returns_success(self) -> None:
        """run_pipeline with empty topic still starts (error is async).

        The pipeline starts in a background thread even with empty topic;
        the error occurs asynchronously in that thread.
        """
        with patch("automedia.pipelines.runner.run_full_pipeline") as mock_run:
            mock_run.return_value = MagicMock()
            result = run_pipeline(topic="", brand="brand")

        assert result["success"] is True

    def test_error_path_does_not_call_pipeline(self) -> None:
        """run_pipeline error path does not invoke run_full_pipeline."""
        with patch("automedia.pipelines.runner.run_full_pipeline") as mock_run:
            result = run_pipeline(topic="test", brand="brand", mode="invalid")

        _assert_error_shape(result)
        mock_run.assert_not_called()


class TestRunPipelineFromStrategyErrors:
    """Tests for run_pipeline_from_strategy error paths."""

    def test_invalid_mode_returns_unknown_error(self) -> None:
        """run_pipeline_from_strategy wraps errors with UNKNOWN code."""
        with (
            patch(
                "automedia.pipelines.runner.run_full_pipeline",
                side_effect=ValueError("Unknown pipeline mode 'bogus'"),
            ),
            patch(
                "automedia.core.llm_client.llm_complete_structured_safe", return_value=MagicMock()
            ),
            patch("automedia.prompts.load_prompt", return_value="prompt"),
        ):
            result = run_pipeline_from_strategy(topic="test", brand="brand", mode="bogus")

        _assert_error_shape(result)
        assert result["error"]["code"] == "UNKNOWN"


class TestGetPipelineProgressErrors:
    """Tests for get_pipeline_progress error paths."""

    def test_unknown_project_returns_error_shape(self) -> None:
        """get_pipeline_progress with unknown project returns error."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = get_pipeline_progress("nonexistent")

        _assert_error_shape(result)
        assert result["error"]["code"] == "NOT_FOUND"

    def test_empty_project_id_returns_error_shape(self) -> None:
        """get_pipeline_progress with empty id returns error."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = get_pipeline_progress("")

        _assert_error_shape(result)


class TestGetPipelineStatusErrors:
    """Tests for get_pipeline_status error paths."""

    def test_unknown_project_returns_error_shape(self) -> None:
        """get_pipeline_status with unknown project returns error."""
        with (
            patch("automedia.mcp.tools._require_allowed"),
            patch("automedia.mcp.tools._discover_projects", return_value=[]),
        ):
            result = get_pipeline_status(project_id="nonexistent", base_dir="/tmp")

        _assert_error_shape(result)
        assert result["error"]["code"] == "NOT_FOUND"

    def test_allowlist_denied_returns_error_shape(self) -> None:
        """get_pipeline_status with denied path returns error."""
        with patch(
            "automedia.mcp.tools._require_allowed",
            side_effect=PermissionError("Path not allowed"),
        ):
            result = get_pipeline_status(project_id="test", base_dir="/restricted")

        _assert_error_shape(result)
        assert result["error"]["code"] == "UNKNOWN"


class TestListProjectsErrors:
    """Tests for list_projects error paths."""

    def test_allowlist_denied_returns_error(self) -> None:
        """list_projects with denied path returns error."""
        with patch(
            "automedia.mcp.tools._require_allowed",
            side_effect=PermissionError("Path not allowed"),
        ):
            result = list_projects(base_dir="/restricted")

        _assert_error_shape(result)


class TestArchiveProjectErrors:
    """Tests for archive_project error paths."""

    def test_project_not_found_returns_error_shape(self) -> None:
        """archive_project with missing project returns error."""
        with (
            patch("automedia.mcp.tools._require_allowed"),
            patch("automedia.mcp.tools._discover_projects", return_value=[]),
        ):
            result = archive_project(project_id="nonexistent", base_dir="/tmp")

        _assert_error_shape(result)
        assert result["error"]["code"] == "NOT_FOUND"

    def test_allowlist_denied_returns_error(self) -> None:
        """archive_project with denied path returns error."""
        with patch(
            "automedia.mcp.tools._require_allowed",
            side_effect=PermissionError("Path not allowed"),
        ):
            result = archive_project(project_id="test", base_dir="/restricted")

        _assert_error_shape(result)


# ===================================================================
# Tests: pipeline control error paths
# ===================================================================


class TestPipelineControlErrors:
    """Tests for pipeline control tool error paths."""

    @pytest.mark.parametrize(
        "tool_func, args",
        [
            (cancel_pipeline, ("unknown",)),
            (pause_pipeline, ("unknown",)),
            (resume_pipeline, ("unknown",)),
            (retry_gate, ("unknown", "G0")),
            (skip_gate, ("unknown", "G0")),
        ],
    )
    def test_pipeline_control_unknown_project_error_shape(
        self, tool_func: Callable[..., dict[str, Any]], args: tuple[str, ...]
    ) -> None:
        """All pipeline control tools return error shape for unknown project."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            result = tool_func(*args)

        assert isinstance(result, dict)
        _assert_error_shape(result)
        assert result["error"]["code"] == "NOT_FOUND"


# ===================================================================
# Tests: success paths
# ===================================================================


class TestSuccessPaths:
    """Tests that success paths use proper response shape."""

    def test_run_pipeline_success(self) -> None:
        """run_pipeline success uses success_response."""
        mock_result = MagicMock()
        mock_result.project_id = "proj_abc123"
        mock_result.status = "started"
        mock_result.exists.return_value = True

        with (
            patch("automedia.pipelines.runner.run_full_pipeline", return_value=mock_result),
            patch("automedia.mcp.tools.time.sleep"),  # sleep to allow thread to start
        ):
            result = run_pipeline(topic="test topic", brand="TestBrand", mode="auto")

        # Success response
        assert result["success"] is True
        assert "project_id" in result

    def test_cancel_pipeline_success(self) -> None:
        """cancel_pipeline success uses success_response."""
        progress = MagicMock()
        tracker = {"proj_valid": progress}
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = cancel_pipeline("proj_valid")

        _assert_success_shape(result)
        assert result["cancelled"] is True
        assert result["project_id"] == "proj_valid"
        progress.cancel.assert_called_once()

    def test_pause_pipeline_success(self) -> None:
        """pause_pipeline success uses success_response."""
        progress = MagicMock()
        tracker = {"proj_valid": progress}
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = pause_pipeline("proj_valid")

        _assert_success_shape(result)
        assert result["paused"] is True
        progress.pause.assert_called_once()

    def test_resume_pipeline_success(self) -> None:
        """resume_pipeline success uses success_response."""
        progress = MagicMock()
        tracker = {"proj_valid": progress}
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = resume_pipeline("proj_valid")

        _assert_success_shape(result)
        assert result["resumed"] is True
        progress.resume.assert_called_once()

    def test_retry_gate_success(self) -> None:
        """retry_gate success uses success_response."""
        progress = MagicMock()
        tracker = {"proj_valid": progress}
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = retry_gate("proj_valid", "G0")

        _assert_success_shape(result)
        assert result["retrying"] is True
        progress.mark_retry_gate.assert_called_once_with("G0")

    def test_skip_gate_success(self) -> None:
        """skip_gate success uses success_response."""
        progress = MagicMock()
        tracker = {"proj_valid": progress}
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = skip_gate("proj_valid", "G0")

        _assert_success_shape(result)
        assert result["skipping"] is True
        progress.mark_skip_gate.assert_called_once_with("G0")

    def test_get_pipeline_progress_success(self) -> None:
        """get_pipeline_progress success uses success_response."""
        progress = MagicMock()
        progress.get_progress.return_value = {
            "project_id": "proj_valid",
            "current_gate": None,
            "gates_done": ["G0"],
            "gates_remaining": ["G1", "G2"],
            "total_gates": 3,
            "events": [],
            "error": None,
        }
        tracker = {"proj_valid": progress}
        with patch("automedia.mcp.tools._pipeline_tracker", tracker):
            result = get_pipeline_progress("proj_valid")

        assert result["success"] is True
        assert result["project_id"] == "proj_valid"
        assert result["gates_done"] == ["G0"]

    def test_list_projects_success(self) -> None:
        """list_projects success uses success_response."""
        from automedia.mcp.tools import list_projects

        with (
            patch("automedia.mcp.tools._require_allowed"),
            patch(
                "automedia.mcp.tools._discover_projects",
                return_value=[
                    {"project_id": "p1", "topic": "t1"},
                    {"project_id": "p2", "topic": "t2"},
                ],
            ),
        ):
            result = list_projects(base_dir="/tmp")

        assert result["success"] is True
        assert "projects" in result
        assert len(result["projects"]) == 2


# ===================================================================
# Tests: batch_run error paths
# ===================================================================


class TestBatchRunErrors:
    """Tests for batch_run error paths."""

    def test_invalid_mode_returns_with_errors_in_results(self) -> None:
        """batch_run with invalid mode includes error in each result entry."""
        result = batch_run(
            topics=["topic1", "topic2"],
            brand="brand",
            mode="invalid_mode",
        )

        assert result["success"] is True
        assert "results" in result
        for r in result["results"]:
            assert r["status"] == "failed"

    def test_empty_topics_list_returns_empty_results(self) -> None:
        """batch_run with empty topics returns success with no results."""
        result = batch_run(
            topics=[],
            brand="brand",
        )

        assert result["success"] is True
        assert result["results"] == []
        assert result["total"] == 0

    def test_success_path(self) -> None:
        """batch_run success uses success_response."""
        mock_result = MagicMock()
        mock_result.project_id = "proj_abc"
        mock_result.status = "success"
        mock_result.error = None

        with patch("automedia.pipelines.runner.run_full_pipeline", return_value=mock_result):
            result = batch_run(
                topics=["topic1"],
                brand="brand",
                mode="auto",
            )

        assert result["success"] is True
        assert "results" in result
        assert len(result["results"]) == 1


# ===================================================================
# Tests: search_assets error paths
# ===================================================================


class TestSearchAssetsErrors:
    """Tests for search_assets error paths."""

    def test_error_returns_proper_shape(self) -> None:
        """search_assets returns proper error shape on failure."""
        with patch(
            "automedia.asset_library.search_assets",
            side_effect=AutoMediaError("DB connection failed"),
        ):
            result = search_assets(query="test", brand="brand")

        _assert_error_shape(result)

    def test_empty_query_handled(self) -> None:
        """search_assets with empty query may succeed or error gracefully."""
        with patch("automedia.asset_library.search_assets") as mock_sa:
            mock_sa.return_value = []
            result = search_assets(query="", brand="brand")

        # Should still return a valid response shape
        assert isinstance(result, dict)


# ===================================================================
# Tests: error shape consistency across all tools
# ===================================================================


class TestErrorShapeConsistency:
    """Tests that error responses from different tools share the same shape."""

    def test_error_shape_has_consistent_keys(self) -> None:
        """All error responses have the same top-level keys."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            error_results = [
                cancel_pipeline("x"),
                pause_pipeline("x"),
                resume_pipeline("x"),
                retry_gate("x", "G0"),
                skip_gate("x", "G0"),
                get_pipeline_progress("x"),
            ]

        for result in error_results:
            _assert_error_shape(result)

    def test_error_resolution_is_non_empty_string(self) -> None:
        """Error resolution is always a non-empty string."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            error_results = [
                cancel_pipeline("x"),
                pause_pipeline("x"),
                resume_pipeline("x"),
                get_pipeline_progress("x"),
            ]

        for result in error_results:
            resolution = result["error"]["resolution"]
            assert isinstance(resolution, str) and len(resolution) > 0, (
                f"Resolution should be non-empty, got {resolution!r}"
            )

    def test_no_error_message_key_in_errors(self) -> None:
        """Error responses do NOT include the redundant error_message key."""
        with patch("automedia.mcp.tools._pipeline_tracker", {}):
            error_results = [
                cancel_pipeline("x"),
                pause_pipeline("x"),
                resume_pipeline("x"),
                retry_gate("x", "G0"),
                skip_gate("x", "G0"),
                get_pipeline_progress("x"),
            ]

        for result in error_results:
            assert "error_message" not in result, (
                "error_message was removed; use error['message'] instead"
            )
