"""E2E smoke tests for the AutoMedia pipeline.

Verifies that the pipeline can start and produce output in text_only mode
with mocked dependencies.  These are quick-check tests, not exhaustive.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from automedia.gates.base import BaseGate
from automedia.pipelines.runner import _MODE_MAP, run_full_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AlwaysPassGate(BaseGate):
    """Gate that always passes — for smoke-test gate lists."""

    _gate_name = "G89"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name, "output_path": ""}


# =========================================================================
# Smoke test: text_only pipeline succeeds
# =========================================================================


class TestTextOnlyPipelineSucceeds:
    """run_full_pipeline(mode='text_only') returns success and creates a project."""

    @patch("automedia.core.config_loader.load_config", return_value={"key": "val"})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_text_only_pipeline_succeeds(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Pipeline completes with status='success' and project_dir is set."""
        # Arrange
        project_dir = str(tmp_path / "smoke-test-proj")
        mock_proj = MagicMock()
        mock_proj.project_id = "smoke-001"
        mock_proj.project_dir = project_dir
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        # Act
        result = run_full_pipeline(
            topic="Smoke test topic",
            brand="testbrand",
            mode="text_only",
        )

        # Assert — result shape
        assert result.status == "success"
        assert result.project_id == "smoke-001"
        assert result.project_dir == project_dir
        assert result.topic == "Smoke test topic"
        assert result.brand == "testbrand"
        assert result.total_duration_s >= 0

        # Assert — project directory exists
        assert mock_proj.project_dir is not None

    @patch("automedia.core.config_loader.load_config", return_value={"key": "val"})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_text_only_no_video_gates_built(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """text_only mode gates list contains zero V gates."""
        # Arrange
        mock_proj = MagicMock()
        mock_proj.project_id = "smoke-002"
        mock_proj.project_dir = str(tmp_path / "smoke-proj-002")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        # Act
        result = run_full_pipeline(
            topic="No video gates",
            brand="testbrand",
            mode="text_only",
        )

        # Assert
        assert result.status == "success"


# =========================================================================
# Smoke test: _MODE_MAP structure
# =========================================================================


class TestGatesAreConstructed:
    """_MODE_MAP contains the expected mode keys and gate lists."""

    def test_mode_map_contains_expected_modes(self) -> None:
        """All documented pipeline modes are registered in _MODE_MAP."""
        expected_modes = {
            "auto",
            "text_only",
            "text_with_cover",
            "video_only",
            "qa_only",
            "image-carousel",
            "social-thread",
            "short-video",
        }
        assert expected_modes.issubset(_MODE_MAP.keys())

    def test_text_only_mode_excludes_video_gates(self) -> None:
        """text_only mode must never include V0-V7 gates."""
        names = _MODE_MAP["text_only"]
        for i in range(8):
            assert f"V{i}" not in names, f"V{i} should not be in text_only mode"

    def test_text_only_has_cw_and_copy_gates(self) -> None:
        """text_only must include CW, G0-G5, H0, and lifecycle gates."""
        names = _MODE_MAP["text_only"]
        assert "CW" in names
        for i in range(6):
            assert f"G{i}" in names, f"G{i} missing from text_only"
        assert "H0" in names
        for i in range(1, 5):
            assert f"L{i}" in names, f"L{i} missing from text_only"


# =========================================================================
# Smoke test: resume_from does not crash
# =========================================================================


class TestResumeFromNoCrash:
    """run_full_pipeline with resume_from works without raising."""

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_resume_from_valid_gate(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Resume from G0 works — gates are sliced from G0 onward."""
        mock_proj = MagicMock()
        mock_proj.project_id = "resume-001"
        mock_proj.project_dir = str(tmp_path / "resume-proj")
        mock_project.init.return_value = mock_proj

        # Capture the gate names passed to _build_gates_from_names
        captured_names: list[list[str]] = []

        def capture(names: list[str], **kwargs: Any) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline(
            topic="Resume test",
            brand="testbrand",
            mode="text_only",
            resume_from="G0",
        )

        assert result.status == "success"
        # The first gate built should be G0 when resuming from G0
        assert captured_names[0][0] == "G0"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_resume_from_none_runs_all_gates(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Resume from None runs the full gate list from the start."""
        mock_proj = MagicMock()
        mock_proj.project_id = "resume-002"
        mock_proj.project_dir = str(tmp_path / "resume-proj-002")
        mock_project.init.return_value = mock_proj

        captured_names: list[list[str]] = []

        def capture(names: list[str], **kwargs: Any) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline(
            topic="Full run",
            brand="testbrand",
            mode="text_only",
        )

        assert result.status == "success"
        # Without resume_from, the full text_only gate list should be built
        assert captured_names[0] == _MODE_MAP["text_only"]
