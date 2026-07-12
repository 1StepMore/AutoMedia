"""Tests for run_full_pipeline — high-level pipeline runner."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.gates.base import BaseGate
from automedia.pipelines.runner import (
    _MODE_MAP,
    _build_gates_from_names,
    _build_gates_log,
    _collect_assets,
    run_full_pipeline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AlwaysPassGate(BaseGate):
    """Gate that always passes — for runner integration tests."""

    _gate_name = "G60"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


class _AlwaysFailGate(BaseGate):
    """Gate that always fails — for runner failure tests."""

    _gate_name = "G61"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "gate": self.gate_name, "error": "nope"}


# =========================================================================
# _MODE_MAP tests
# =========================================================================


class TestModeMap:
    """Mode map defines the correct gate lists."""

    def test_auto_mode_includes_pre_gate(self) -> None:
        assert "pre-gate" in _MODE_MAP["auto"]

    def test_auto_mode_includes_all_groups(self) -> None:
        names = _MODE_MAP["auto"]
        # G0-G5
        for i in range(6):
            assert f"G{i}" in names
        # V0-V7
        for i in range(8):
            assert f"V{i}" in names
        # L1-L3
        for i in range(1, 4):
            assert f"L{i}" in names

    def test_text_only_has_no_video_gates(self) -> None:
        names = _MODE_MAP["text_only"]
        for i in range(8):
            assert f"V{i}" not in names

    def test_video_only_has_no_text_gates(self) -> None:
        names = _MODE_MAP["video_only"]
        for i in range(6):
            assert f"G{i}" not in names

    def test_qa_only_subset(self) -> None:
        names = _MODE_MAP["qa_only"]
        assert names == ["G0", "G2", "G3", "V1", "V6"]

    def test_non_qa_modes_have_lifecycle_gates(self) -> None:
        for mode, names in _MODE_MAP.items():
            if mode == "qa_only":
                continue  # qa_only is a subset, no L1-L3
            for i in range(1, 4):
                assert f"L{i}" in names, f"L{i} missing from {mode}"


# =========================================================================
# _build_gates_from_names tests
# =========================================================================


class TestBuildGatesFromNames:
    """_build_gates_from_names instantiates from the registry."""

    def test_builds_known_gates(self) -> None:
        """Building a known gate name returns an instance."""
        # pre-gate is always registered via gates/__init__.py import
        import automedia.gates  # noqa: F401

        gates = _build_gates_from_names(["pre-gate"])
        assert len(gates) == 1
        assert isinstance(gates[0], BaseGate)
        assert gates[0].gate_name == "pre-gate"

    def test_unknown_gate_raises(self) -> None:
        with pytest.raises(KeyError, match="NONEXISTENT_XYZ"):
            _build_gates_from_names(["NONEXISTENT_XYZ"])


# =========================================================================
# _collect_assets tests
# =========================================================================


class TestCollectAssets:
    """_collect_assets extracts AssetInfo from gate context."""

    def test_empty_context(self) -> None:
        assert _collect_assets({}) == []

    def test_output_files_key(self, tmp_path: Any) -> None:
        ctx = {"output_files": [{"type": "video", "path": str(tmp_path / "v.mp4"), "platform": "bilibili"}]}
        assets = _collect_assets(ctx)
        assert len(assets) == 1
        assert assets[0].type == "video"

    def test_assets_key(self, tmp_path: Any) -> None:
        ctx = {
            "assets": [{"type": "image", "path": str(tmp_path / "i.png"), "platform": "wechat", "md5": "abc"}]
        }
        assets = _collect_assets(ctx)
        assert len(assets) == 1
        assert assets[0].md5 == "abc"

    def test_both_keys(self, tmp_path: Any) -> None:
        ctx = {
            "output_files": [{"type": "a", "path": str(tmp_path / "a")}],
            "assets": [{"type": "b", "path": str(tmp_path / "b")}],
        }
        assets = _collect_assets(ctx)
        assert len(assets) == 2


# =========================================================================
# _build_gates_log tests
# =========================================================================


class TestBuildGatesLog:
    """_build_gates_log converts result dicts to GateLogEntry."""

    def test_empty(self) -> None:
        assert _build_gates_log([]) == []

    def test_passed_result(self) -> None:
        entries = _build_gates_log([{"passed": True, "gate": "G0", "duration_s": 1.5}])
        assert len(entries) == 1
        assert entries[0].status == "passed"
        assert entries[0].duration_s == 1.5

    def test_failed_result(self) -> None:
        entries = _build_gates_log(
            [{"passed": False, "gate": "G3", "error": "bad", "duration_s": 0.5}]
        )
        assert entries[0].status == "failed"
        assert entries[0].error == "bad"

    def test_missing_gate_name(self) -> None:
        entries = _build_gates_log([{"passed": True}])
        assert entries[0].gate_name == "unknown"


# =========================================================================
# run_full_pipeline integration tests (with mocks)
# =========================================================================


class TestRunFullPipeline:
    """run_full_pipeline with mocked config and project."""

    @patch("automedia.pipelines.runner.load_config", return_value={"key": "val"})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_success_result(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "test123"
        mock_proj.project_dir = str(tmp_path / "proj")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        result = run_full_pipeline("AI topic", "testbrand", mode="auto")

        assert result.status == "success"
        assert result.project_id == "test123"
        assert result.topic == "AI topic"
        assert result.brand == "testbrand"
        assert result.total_duration_s >= 0

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_partial_result_on_failure(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "p1"
        mock_proj.project_dir = str(tmp_path / "p1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysFailGate()]

        result = run_full_pipeline("topic", "brand")
        assert result.status == "partial"

    @patch("automedia.pipelines.runner.load_config", side_effect=RuntimeError("config boom"))
    def test_failed_on_exception(self, mock_config: MagicMock) -> None:
        result = run_full_pipeline("t", "b")
        assert result.status == "failed"
        assert "config boom" in (result.error or "")

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_unknown_mode_raises(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "p"
        mock_proj.project_dir = str(tmp_path / "proj")
        mock_project.init.return_value = mock_proj

        result = run_full_pipeline("t", "b", mode="nonexistent")
        assert result.status == "failed"
        assert "nonexistent" in (result.error or "")

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_resume_from_skips_gates(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "r1"
        mock_proj.project_dir = str(tmp_path / "r1")
        mock_project.init.return_value = mock_proj

        # Capture the names passed to _build_gates_from_names
        captured_names: list[list[str]] = []

        def capture(names: list[str]) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline("t", "b", mode="auto", resume_from="V3")
        assert result.status == "success"
        # V3 should be first gate
        assert captured_names[0][0] == "V3"

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_resume_from_invalid_gate(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "r2"
        mock_proj.project_dir = str(tmp_path / "r2")
        mock_project.init.return_value = mock_proj

        result = run_full_pipeline("t", "b", mode="auto", resume_from="INVALID_GATE")
        assert result.status == "failed"
        assert "INVALID_GATE" in (result.error or "")

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_config_dir_passed_to_load_config(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "c1"
        mock_proj.project_dir = str(tmp_path / "c1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        run_full_pipeline("t", "b", config_dir="/custom/config")
        mock_config.assert_called_once_with(config_dir="/custom/config")

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_tenant_id_passed_to_project(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "t1"
        mock_proj.project_dir = str(tmp_path / "t1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        run_full_pipeline("t", "b", tenant_id="acme")
        mock_project.init.assert_called_once_with("t", "b", tenant_id="acme")


# =========================================================================
# Fallback content guard tests (Issue #14)
# =========================================================================


class TestFallbackContentGuard:
    """video_only / qa_only modes must inject fallback content when CW is skipped."""

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_video_only_has_fallback_content(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """video_only mode provides fallback text for empty content."""
        mock_proj = MagicMock()
        mock_proj.project_id = "v99"
        mock_proj.project_dir = str(tmp_path / "v99")
        mock_project.init.return_value = mock_proj

        captured: dict[str, Any] = {"content": ""}

        class _CaptureContentGate(BaseGate):
            _gate_name = "V99"
            _failure_mode = "stop"

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR6301
                captured["content"] = __gate_context.get("content", "")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureContentGate()]

        run_full_pipeline("AI topic", "testbrand", mode="video_only")

        # RED: This assertion currently FAILS because content is empty.
        # GREEN: After guard implementation, content will have placeholder text.
        content = captured["content"]
        assert content != "", (
            f"video_only mode should provide fallback content, got empty string"
        )
        assert "[content skipped" in content, (
            f"Expected placeholder marker in content, got {content!r}"
        )

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_qa_only_has_fallback_content(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """qa_only mode provides fallback text for empty content."""
        mock_proj = MagicMock()
        mock_proj.project_id = "q99"
        mock_proj.project_dir = str(tmp_path / "q99")
        mock_project.init.return_value = mock_proj

        captured: dict[str, Any] = {"content": ""}

        class _CaptureContentGate(BaseGate):
            _gate_name = "V98"
            _failure_mode = "stop"

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR6301
                captured["content"] = __gate_context.get("content", "")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureContentGate()]

        run_full_pipeline("AI topic", "testbrand", mode="qa_only")

        # RED: This assertion currently FAILS because content is empty.
        # GREEN: After guard implementation, content will have placeholder text.
        content = captured["content"]
        assert content != "", (
            f"qa_only mode should provide fallback content, got empty string"
        )
        assert "[content skipped" in content, (
            f"Expected placeholder marker in content, got {content!r}"
        )

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_auto_mode_not_affected(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """auto mode still starts with empty content (CW fills it later)."""
        mock_proj = MagicMock()
        mock_proj.project_id = "a99"
        mock_proj.project_dir = str(tmp_path / "a99")
        mock_project.init.return_value = mock_proj

        captured: dict[str, Any] = {"content": "DEFAULT"}

        class _CaptureContentGate(BaseGate):
            _gate_name = "V97"
            _failure_mode = "stop"

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR6301
                captured["content"] = __gate_context.get("content", "")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureContentGate()]

        run_full_pipeline("AI topic", "testbrand", mode="auto")

        # auto mode should NOT have fallback — CW will set content
        content = captured["content"]
        assert content == "", (
            f"auto mode should start with empty content, got {content!r}"
        )

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_text_only_mode_not_affected(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """text_only mode still starts with empty content (CW fills it later)."""
        mock_proj = MagicMock()
        mock_proj.project_id = "t99"
        mock_proj.project_dir = str(tmp_path / "t99")
        mock_project.init.return_value = mock_proj

        captured: dict[str, Any] = {"content": "DEFAULT"}

        class _CaptureContentGate(BaseGate):
            _gate_name = "V96"
            _failure_mode = "stop"

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR6301
                captured["content"] = __gate_context.get("content", "")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureContentGate()]

        run_full_pipeline("AI topic", "testbrand", mode="text_only")

        # text_only mode should NOT have fallback — CW will set content
        content = captured["content"]
        assert content == "", (
            f"text_only mode should start with empty content, got {content!r}"
        )
