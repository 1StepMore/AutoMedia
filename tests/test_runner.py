"""Tests for run_full_pipeline — high-level pipeline runner."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.gates.base import BaseGate
from automedia.manifests.brand_profile_schema import BrandProfile
from automedia.pipelines.runner import (
    _IMAGE_CAROUSEL_GATE_NAMES,
    _MODE_MAP,
    _PLATFORM_CATEGORIES,
    _TEXT_WITH_COVER_GATE_NAMES,
    _build_gates_from_names,
    _build_gates_log,
    _collect_assets,
    _derive_mode_from_platforms,
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

    def test_image_carousel_mode_in_map(self) -> None:
        """image-carousel mode is registered in _MODE_MAP."""
        assert "image-carousel" in _MODE_MAP

    def test_image_carousel_has_correct_gates(self) -> None:
        """image-carousel has CW → G0-G5 → L1-L4, no video gates."""
        names = _MODE_MAP["image-carousel"]
        # Has CW
        assert "CW" in names
        # Has G0-G5
        for i in range(6):
            assert f"G{i}" in names, f"G{i} missing from image-carousel"
        # Has L1-L4
        for i in range(1, 5):
            assert f"L{i}" in names, f"L{i} missing from image-carousel"
        # No video gates
        for i in range(8):
            assert f"V{i}" not in names, f"V{i} should not be in image-carousel"

    def test_image_carousel_gate_list_constant_matches(self) -> None:
        """_IMAGE_CAROUSEL_GATE_NAMES matches _MODE_MAP entry."""
        assert _MODE_MAP["image-carousel"] is _IMAGE_CAROUSEL_GATE_NAMES

    # ------------------------------------------------------------------
    # text_with_cover mode tests
    # ------------------------------------------------------------------

    def test_text_with_cover_mode_in_map(self) -> None:
        """text_with_cover mode is registered in _MODE_MAP."""
        assert "text_with_cover" in _MODE_MAP

    def test_text_with_cover_has_no_video_gates(self) -> None:
        """text_with_cover mode has no V gates (text only mode)."""
        names = _MODE_MAP["text_with_cover"]
        for i in range(8):
            assert f"V{i}" not in names

    def test_text_with_cover_has_CW_and_G0_G5(self) -> None:
        """text_with_cover has CW, G0-G5, lifecycle gates."""
        names = _MODE_MAP["text_with_cover"]
        assert "CW" in names
        for i in range(6):
            assert f"G{i}" in names, f"G{i} missing from text_with_cover"
        for i in range(1, 5):
            assert f"L{i}" in names, f"L{i} missing from text_with_cover"

    def test_text_with_cover_gate_list_constant_matches(self) -> None:
        """_TEXT_WITH_COVER_GATE_NAMES matches _MODE_MAP entry."""
        assert _MODE_MAP["text_with_cover"] is _TEXT_WITH_COVER_GATE_NAMES

    def test_text_with_cover_matches_text_only_gates(self) -> None:
        """text_with_cover has same gate list as text_only."""
        assert _MODE_MAP["text_with_cover"] == _MODE_MAP["text_only"]


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
        ctx = {
            "output_files": [
                {"type": "video", "path": str(tmp_path / "v.mp4"), "platform": "bilibili"}
            ]
        }
        assets = _collect_assets(ctx)
        assert len(assets) == 1
        assert assets[0].type == "video"

    def test_assets_key(self, tmp_path: Any) -> None:
        ctx = {
            "assets": [
                {
                    "type": "image",
                    "path": str(tmp_path / "i.png"),
                    "platform": "wechat",
                    "md5": "abc",
                }
            ]
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

    @patch("automedia.pipelines.runner.HITLConfig")
    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_hitl_config_in_context(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        mock_hitl: MagicMock,
        tmp_path: Any,
    ) -> None:
        """run_full_pipeline injects hitl_config dict into gate_context."""
        mock_proj = MagicMock()
        mock_proj.project_id = "hitl-ctx"
        mock_proj.project_dir = str(tmp_path / "hitl-ctx")
        mock_project.init.return_value = mock_proj

        mock_cfg = MagicMock()
        mock_cfg.list_nodes.return_value = [
            {"name": "brand_questionnaire", "autoset": "human"},
            {"name": "build_scale_routing", "autoset": "agent"},
        ]
        mock_hitl.return_value = mock_cfg

        captured: dict = {}

        class _CaptureHITLConfigGate(BaseGate):
            _gate_name = "H99"
            _failure_mode = "stop"

            def execute(  # noqa: PLR6301
                self, gate_context: dict[str, Any]
            ) -> dict[str, Any]:
                captured["hitl_config"] = gate_context.get("hitl_config", {})
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureHITLConfigGate()]

        result = run_full_pipeline("HITL test topic", "testbrand", mode="auto")

        assert result.status == "success"
        hc = captured["hitl_config"]
        assert "enabled_nodes" in hc, f"hitl_config missing enabled_nodes, got keys: {list(hc)}"
        assert "default_executor" in hc
        assert "timeout_s" in hc
        assert {"name": "brand_questionnaire", "autoset": "human"} in hc["enabled_nodes"]
        assert {"name": "build_scale_routing", "autoset": "agent"} not in hc["enabled_nodes"]
        assert hc["default_executor"] == "agent"
        assert hc["timeout_s"] == 86400

    # ------------------------------------------------------------------
    # text_with_cover mode — cover image generation
    # ------------------------------------------------------------------

    @patch("automedia.pipelines.runner.ImagePipeline")
    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_text_with_cover_generates_cover(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        mock_image_pipeline: MagicMock,
        tmp_path: Any,
    ) -> None:
        """text_with_cover mode calls ImagePipeline.generate_single_cover."""
        mock_proj = MagicMock()
        mock_proj.project_id = "tcv1"
        mock_proj.project_dir = str(tmp_path / "tcv1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        mock_pipeline = MagicMock()
        mock_pipeline.generate_single_cover.return_value = "/path/to/cover.png"
        mock_image_pipeline.return_value = mock_pipeline

        result = run_full_pipeline(
            "AI topic",
            "testbrand",
            mode="text_with_cover",
        )

        assert result.status == "success"
        mock_pipeline.generate_single_cover.assert_called_once_with(
            topic="AI topic",
            brand="testbrand",
            project_dir=mock_proj.project_dir,
        )


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
        assert content != "", "video_only mode should provide fallback content, got empty string"
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
        assert content != "", "qa_only mode should provide fallback content, got empty string"
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
        assert content == "", f"auto mode should start with empty content, got {content!r}"

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
        assert content == "", f"text_only mode should start with empty content, got {content!r}"


# =========================================================================
# Platform-based mode auto-derivation tests
# =========================================================================


class TestPlatformCategories:
    """_PLATFORM_CATEGORIES maps known platforms to content categories."""

    def test_wechat_is_text_first(self) -> None:
        assert _PLATFORM_CATEGORIES["wechat"] == "text-first"

    def test_zhihu_is_text_first(self) -> None:
        assert _PLATFORM_CATEGORIES["zhihu"] == "text-first"

    def test_xiaohongshu_is_mixed_social(self) -> None:
        assert _PLATFORM_CATEGORIES["xiaohongshu"] == "mixed-social"

    def test_feishu_is_notification_only(self) -> None:
        assert _PLATFORM_CATEGORIES["feishu"] == "notification-only"


class TestDeriveModeFromPlatforms:
    """_derive_mode_from_platforms() returns the correct mode."""

    def test_empty_list_returns_empty(self) -> None:
        assert _derive_mode_from_platforms([]) == ""

    def test_text_only_platforms_return_text_only(self) -> None:
        assert _derive_mode_from_platforms(["wechat"]) == "text_only"
        assert _derive_mode_from_platforms(["zhihu"]) == "text_only"
        assert _derive_mode_from_platforms(["wechat", "zhihu"]) == "text_only"

    def test_mixed_social_returns_auto(self) -> None:
        assert _derive_mode_from_platforms(["xiaohongshu"]) == "auto"

    def test_notification_only_returns_text_only(self) -> None:
        assert _derive_mode_from_platforms(["feishu"]) == "text_only"

    def test_mixed_text_and_notification_returns_text_only(self) -> None:
        assert _derive_mode_from_platforms(["wechat", "feishu"]) == "text_only"

    def test_mixed_text_and_social_returns_auto(self) -> None:
        assert _derive_mode_from_platforms(["wechat", "xiaohongshu"]) == "auto"
        assert _derive_mode_from_platforms(["zhihu", "xiaohongshu"]) == "auto"
        assert _derive_mode_from_platforms(["wechat", "zhihu", "xiaohongshu"]) == "auto"

    def test_unknown_platform_treated_as_text_first(self) -> None:
        assert _derive_mode_from_platforms(["unknown_platform"]) == "text_only"

    def test_unknown_with_mixed_social_returns_auto(self) -> None:
        assert _derive_mode_from_platforms(["unknown", "xiaohongshu"]) == "auto"

    def test_all_notification_returns_text_only(self) -> None:
        assert _derive_mode_from_platforms(["feishu", "feishu"]) == "text_only"


class TestRunFullPipelineModeDerivation:
    """run_full_pipeline auto-derives mode from brand platforms."""

    def _make_mock_profile(
        self,
        platforms: list[str] | None = None,
    ) -> BrandProfile:
        return BrandProfile(
            brand_name="testbrand",
            platforms=platforms or [],
        )

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    def test_text_only_platforms_derive_text_only(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Brand with wechat+zhihu derives text_only mode."""
        mock_proj = MagicMock()
        mock_proj.project_id = "md1"
        mock_proj.project_dir = str(tmp_path / "md1")
        mock_project.init.return_value = mock_proj

        mock_load_profiles.return_value = {
            "testbrand": self._make_mock_profile(platforms=["wechat", "zhihu"]),
        }

        # Capture gate names built
        captured_names: list[list[str]] = []

        def capture(names: list[str]) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"

        # Should use text_only gate list (no V gates)
        built = captured_names[0]
        assert "CW" in built
        assert "V0" not in built, "text_only mode should not include V0"
        assert built == _MODE_MAP["text_only"]

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    def test_mixed_social_platforms_derive_auto(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Brand with xiaohongshu derives auto mode."""
        mock_proj = MagicMock()
        mock_proj.project_id = "md2"
        mock_proj.project_dir = str(tmp_path / "md2")
        mock_project.init.return_value = mock_proj

        mock_load_profiles.return_value = {
            "testbrand": self._make_mock_profile(platforms=["xiaohongshu"]),
        }

        captured_names: list[list[str]] = []

        def capture(names: list[str]) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"

        # Should use auto gate list (includes V gates)
        built = captured_names[0]
        assert "V0" in built, "auto mode should include V0"
        assert built == _MODE_MAP["auto"]

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    def test_explicit_mode_overrides_derivation(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Explicit --mode=text_only stays text_only even with mixed-social platforms."""
        mock_proj = MagicMock()
        mock_proj.project_id = "md3"
        mock_proj.project_dir = str(tmp_path / "md3")
        mock_project.init.return_value = mock_proj

        # Brand has xiaohongshu (mixed-social → would derive "auto")
        mock_load_profiles.return_value = {
            "testbrand": self._make_mock_profile(platforms=["xiaohongshu"]),
        }

        captured_names: list[list[str]] = []

        def capture(names: list[str]) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        # Explicitly pass text_only — should NOT be overridden
        result = run_full_pipeline("t", "testbrand", mode="text_only")
        assert result.status == "success"

        built = captured_names[0]
        # Should use text_only gate list despite xiaohongshu
        assert "V0" not in built, "explicit text_only mode should not include V0"
        assert built == _MODE_MAP["text_only"]

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    def test_no_platforms_keeps_default_mode(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Brand with no platforms keeps default auto mode."""
        mock_proj = MagicMock()
        mock_proj.project_id = "md4"
        mock_proj.project_dir = str(tmp_path / "md4")
        mock_project.init.return_value = mock_proj

        mock_load_profiles.return_value = {
            "testbrand": self._make_mock_profile(platforms=[]),
        }

        captured_names: list[list[str]] = []

        def capture(names: list[str]) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"

        built = captured_names[0]
        assert built == _MODE_MAP["auto"]

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    def test_brand_platforms_in_gate_context(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """gate_context has brand_platforms key listing the platforms."""
        mock_proj = MagicMock()
        mock_proj.project_id = "md5"
        mock_proj.project_dir = str(tmp_path / "md5")
        mock_project.init.return_value = mock_proj

        mock_load_profiles.return_value = {
            "testbrand": self._make_mock_profile(platforms=["wechat", "xiaohongshu"]),
        }

        captured_ctx: dict[str, Any] = {}

        class _CaptureCtxGate(BaseGate):
            _gate_name = "H98"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR6301
                captured_ctx["brand_platforms"] = gate_context.get("brand_platforms", [])
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureCtxGate()]

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"
        assert captured_ctx["brand_platforms"] == ["wechat", "xiaohongshu"]

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    def test_no_brand_platforms_empty_list_in_context(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """gate_context has empty brand_platforms when brand has no platforms."""
        mock_proj = MagicMock()
        mock_proj.project_id = "md6"
        mock_proj.project_dir = str(tmp_path / "md6")
        mock_project.init.return_value = mock_proj

        mock_load_profiles.return_value = {
            "testbrand": self._make_mock_profile(platforms=[]),
        }

        captured_ctx: dict[str, Any] = {"brand_platforms": "UNSET"}

        class _CaptureCtxGate(BaseGate):
            _gate_name = "H97"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR6301
                captured_ctx["brand_platforms"] = gate_context.get("brand_platforms", "MISSING")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureCtxGate()]

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"
        assert captured_ctx["brand_platforms"] == []
