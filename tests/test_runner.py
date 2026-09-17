"""Tests for run_full_pipeline — high-level pipeline runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.gates.base import BaseGate
from automedia.manifests.brand_profile_schema import BrandProfile
from automedia.pipelines.runner import (
    _AUTO_GATE_NAMES,
    _IMAGE_CAROUSEL_GATE_NAMES,
    _MODE_MAP,
    _PLATFORM_CATEGORIES,
    _TEXT_ONLY_GATE_NAMES,
    _TEXT_WITH_COVER_GATE_NAMES,
    _VIDEO_PRODUCING_MODES,
    _build_gates_from_names,
    _build_gates_log,
    _collect_assets,
    _compose_gate_list,
    _derive_mode_from_platforms,
    _select_gates,
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


class _GateWithChecksGate(BaseGate):
    """Gate whose result carries per-check detail — proves LIVE report render."""

    _gate_name = "V62"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "passed": True,
            "gate": self.gate_name,
            "checks": [{"name": "always_ok", "passed": True, "detail": "synthetic ok"}],
        }


# =========================================================================
# _MODE_MAP tests
# =========================================================================


class TestModeMap:
    """Mode map defines the correct gate lists."""

    def test_auto_mode_includes_pre_gate(self) -> None:
        assert "pre-gate" in _MODE_MAP["auto"]

    def test_auto_mode_includes_all_groups(self) -> None:
        names = _MODE_MAP["auto"]
        # G0-G3 + G6 (G4/G5 are produced by no preset any more)
        for i in (0, 1, 2, 3, 6):
            assert f"G{i}" in names
        # V0-V7
        for i in range(8):
            assert f"V{i}" in names
        # H0 joins the copy and video tracks
        assert "H0" in names

    def test_no_preset_contains_unproducible_gates(self) -> None:
        """No preset carries G4/G5/L1-L4: no preset produces their inputs.

        G4/G5 (WeChat checklist / HTML lint) consume assets no preset
        produces, and L1-L4 are lifecycle gates driven by their standalone
        publish/archive/distribute/localize commands, not by a preset.
        """
        banned = ("G4", "G5", "L1", "L2", "L3", "L4")
        for mode, names in _MODE_MAP.items():
            for gate in banned:
                assert gate not in names, f"{gate} must not be in preset {mode!r}"

    def test_video_and_p_gate_membership_pinned(self) -> None:
        """V0-V7 / P1-P4 membership per preset is pinned to HEAD (unchanged).

        This is the non-regression half of the preset realignment: the todo
        removes G4/G5/L1-L4 only, so every V/P occurrence stays byte-identical.
        The expected mapping is a LITERAL set (not derived from _MODE_MAP), and
        a mode added without updating it must fail here rather than drift.
        """
        expected_by_mode: dict[str, tuple[str, ...]] = {
            "auto": ("V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"),
            "text_only": (),
            "text_with_cover": (),
            "video_only": ("V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"),
            "qa_only": ("V1", "V6"),
            "image-carousel": (),
            "social-thread": (),
            "short-video": ("V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"),
            "repurpose": (
                "V0",
                "V1",
                "V2",
                "V3",
                "V4",
                "V5",
                "V6",
                "V7",
                "P1",
                "P2",
                "P3",
                "P4",
            ),
        }
        assert set(expected_by_mode) == set(_MODE_MAP)
        for mode, expected in expected_by_mode.items():
            present = tuple(g for g in _MODE_MAP[mode] if g[:1] in ("V", "P"))
            assert present == expected, f"{mode}: {present} != {expected}"

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

    def test_content_only_modes_have_no_lifecycle_gates(self) -> None:
        for mode in ("text_only", "text_with_cover", "image-carousel", "social-thread"):
            names = _MODE_MAP[mode]
            for i in range(1, 5):
                assert f"L{i}" not in names, f"L{i} should not be in {mode}"

    def test_image_carousel_mode_in_map(self) -> None:
        """image-carousel mode is registered in _MODE_MAP."""
        assert "image-carousel" in _MODE_MAP

    def test_image_carousel_has_correct_gates(self) -> None:
        """image-carousel has CW → G0-G3 + G6, no lifecycle and no video gates."""
        names = _MODE_MAP["image-carousel"]
        assert "CW" in names
        for i in range(4):
            assert f"G{i}" in names, f"G{i} missing from image-carousel"
        assert "G6" in names
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

    def test_text_with_cover_has_cw_and_copy_gates(self) -> None:
        """text_with_cover has CW and G0-G3 + G6 — no lifecycle gates."""
        names = _MODE_MAP["text_with_cover"]
        assert "CW" in names
        for i in range(4):
            assert f"G{i}" in names, f"G{i} missing from text_with_cover"
        assert "G6" in names

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

    # ------------------------------------------------------------------
    # override_failure_mode per-instance tests
    # ------------------------------------------------------------------

    def test_override_single_gate(self) -> None:
        """Override failure mode for a single gate."""
        import automedia.gates  # noqa: F401

        # G1 (humanizer) defaults to "retry"
        gates = _build_gates_from_names(["G1"], override_failure_mode={"G1": "stop"})
        assert len(gates) == 1
        assert gates[0].gate_name == "G1"
        assert gates[0]._failure_mode == "stop"
        assert gates[0].failure_mode == "stop"  # property access

    def test_override_multiple_gates(self) -> None:
        """Override failure mode for multiple gates."""
        import automedia.gates  # noqa: F401

        gates = _build_gates_from_names(
            ["G1", "G2"],
            override_failure_mode={"G1": "stop", "G2": "stop"},
        )
        assert len(gates) == 2
        assert gates[0].gate_name == "G1"
        assert gates[0].failure_mode == "stop"
        assert gates[1].gate_name == "G2"
        assert gates[1].failure_mode == "stop"

    def test_override_noop_with_empty_dict(self) -> None:
        """Empty override dict does not alter gate failure modes."""
        import automedia.gates  # noqa: F401

        gates = _build_gates_from_names(["G1"], override_failure_mode={})
        assert len(gates) == 1
        assert gates[0].failure_mode == "retry"  # unchanged default

    def test_override_unaffected_gates_retain_class_level(self) -> None:
        """Gates not listed in overrides keep their class-level failure mode."""
        import automedia.gates  # noqa: F401

        gates = _build_gates_from_names(
            ["G1", "G2"],
            override_failure_mode={"G1": "stop"},  # only override G1
        )
        assert gates[0].gate_name == "G1"
        assert gates[0].failure_mode == "stop"  # overridden
        assert gates[1].gate_name == "G2"
        assert gates[1].failure_mode == "retry"  # unchanged

    def test_override_does_not_affect_class_attribute(self) -> None:
        """Instance override does not mutate the class-level ClassVar."""
        import automedia.gates  # noqa: F401
        from automedia.gates.humanizer import G1Humanizer

        class_before = G1Humanizer._failure_mode
        assert class_before == "retry"

        gates = _build_gates_from_names(["G1"], override_failure_mode={"G1": "stop"})
        assert gates[0].failure_mode == "stop"

        # Class-level must remain untouched
        assert G1Humanizer._failure_mode == "retry"

    def test_override_none_is_noop(self) -> None:
        """Passing None as override_failure_mode is the default — no-op."""
        import automedia.gates  # noqa: F401

        gates = _build_gates_from_names(["G1"])
        assert gates[0].failure_mode == "retry"

    def test_override_subsequent_calls_isolated(self) -> None:
        """Each call to _build_gates_from_names produces fresh instances."""
        import automedia.gates  # noqa: F401

        g1 = _build_gates_from_names(["G1"], override_failure_mode={"G1": "stop"})
        g2 = _build_gates_from_names(["G1"], override_failure_mode={"G1": "retry"})
        assert g1[0].failure_mode == "stop"
        assert g2[0].failure_mode == "retry"


# =========================================================================
# _collect_assets tests
# =========================================================================


class TestCollectAssets:
    """_collect_assets extracts AssetInfo from gate context."""

    def test_empty_context(self) -> None:
        assert _collect_assets({}) == []

    def test_output_files_key(self, tmp_path: Path) -> None:
        ctx = {
            "output_files": [
                {"type": "video", "path": str(tmp_path / "v.mp4"), "platform": "bilibili"}
            ]
        }
        assets = _collect_assets(ctx)
        assert len(assets) == 1
        assert assets[0].type == "video"

    def test_assets_key(self, tmp_path: Path) -> None:
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

    def test_both_keys(self, tmp_path: Path) -> None:
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

    def test_skipped_status_is_preserved(self) -> None:
        """A gate that reports ``status="skipped"`` keeps that status in the log.

        中文说明：这是健康度报告 P0-1 的根因——跳过曾被折成 ``passed``，于是
        一条完全没有视频产出的流水线在报告和 CLI 里看起来全绿。
        """
        entries = _build_gates_log(
            [
                {
                    "passed": True,
                    "gate": "V0",
                    "status": "skipped",
                    "duration_s": 0.0,
                }
            ]
        )
        assert entries[0].status == "skipped"

    def test_reported_status_overrides_passed_flag(self) -> None:
        """An explicit ``status`` wins over the ``passed`` flag."""
        entries = _build_gates_log([{"passed": True, "gate": "V1", "status": "error"}])
        assert entries[0].status == "error"

    def test_unknown_reported_status_falls_back_to_passed_flag(self) -> None:
        """A bogus ``status`` value does not corrupt the log."""
        entries = _build_gates_log([{"passed": True, "gate": "V1", "status": "weird"}])
        assert entries[0].status == "passed"


# =========================================================================
# run_full_pipeline integration tests (with mocks)
# =========================================================================


class TestRunFullPipeline:
    """run_full_pipeline with mocked config and project."""

    @patch("automedia.core.config_loader.load_config", return_value={"key": "val"})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_success_result(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_partial_result_on_failure(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "p1"
        mock_proj.project_dir = str(tmp_path / "p1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysFailGate()]

        result = run_full_pipeline("topic", "brand")
        assert result.status == "partial"

    @patch("automedia.core.config_loader.load_config", side_effect=RuntimeError("config boom"))
    def test_failed_on_exception(self, mock_config: MagicMock) -> None:
        result = run_full_pipeline("t", "b")
        assert result.status == "failed"
        assert "config boom" in (result.error or "")

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_gate_report_written_on_success(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Every production run writes a gate report under 05_review/gate-report/."""
        import json

        mock_proj = MagicMock()
        mock_proj.project_id = "gr1"
        mock_proj.project_dir = str(tmp_path / "gr1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_GateWithChecksGate()]

        result = run_full_pipeline("t", "b", mode="auto")
        assert result.status == "success"

        report_dir = tmp_path / "gr1" / "05_review" / "gate-report"
        json_files = list(report_dir.glob("gate-report-*.json"))
        assert json_files, "gate report JSON must exist after a successful run"
        md_files = list(report_dir.glob("gate-report-*.md"))
        assert md_files, "gate report Markdown must exist after a successful run"

        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert data["summary"]["total"] >= 1
        # LIVE render (gate_results passed): per-check detail present in the JSON.
        row = next(g for g in data["gates"] if g["gate"] == "V62")
        assert row["checks"] is not None and row["checks"][0]["name"] == "always_ok"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_gate_report_written_on_gate_failure(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A failing-gate run still produces the report AND still returns
        failed/partial — the report write never masks the failure."""
        import json

        mock_proj = MagicMock()
        mock_proj.project_id = "gr2"
        mock_proj.project_dir = str(tmp_path / "gr2")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysFailGate()]

        result = run_full_pipeline("t", "b", mode="auto")
        assert result.status == "partial"

        report_dir = tmp_path / "gr2" / "05_review" / "gate-report"
        json_files = list(report_dir.glob("gate-report-*.json"))
        assert json_files, "gate report JSON must exist even when a gate fails"

        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert data["blocked_by_gate"] == "G61"
        assert data["gates"][0]["verdict"] == "fail"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_gate_report_write_failure_never_fails_pipeline(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A report-write error is swallowed (logged + skipped), mirroring the
        MetricsHook write-error discipline."""
        from unittest.mock import patch as _patch

        mock_proj = MagicMock()
        mock_proj.project_id = "gr3"
        mock_proj.project_dir = str(tmp_path / "gr3")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        with _patch(
            "automedia.pipelines.gate_report.write_gate_report",
            side_effect=OSError("disk full"),
        ):
            result = run_full_pipeline("t", "b", mode="auto")

        assert result.status == "success"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_unknown_mode_raises(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "p"
        mock_proj.project_dir = str(tmp_path / "proj")
        mock_project.init.return_value = mock_proj

        result = run_full_pipeline("t", "b", mode="nonexistent")
        assert result.status == "failed"
        assert "nonexistent" in (result.error or "")

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_resume_from_skips_gates(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "r1"
        mock_proj.project_dir = str(tmp_path / "r1")
        mock_project.init.return_value = mock_proj

        # Capture the names passed to _build_gates_from_names
        captured_names: list[list[str]] = []

        def capture(names: list[str], **kwargs: object) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline("t", "b", mode="auto", resume_from="V3")
        assert result.status == "success"
        # V3 should be first gate
        assert captured_names[0][0] == "V3"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_resume_from_invalid_gate(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "r2"
        mock_proj.project_dir = str(tmp_path / "r2")
        mock_project.init.return_value = mock_proj

        result = run_full_pipeline("t", "b", mode="auto", resume_from="INVALID_GATE")
        assert result.status == "failed"
        assert "INVALID_GATE" in (result.error or "")

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_config_dir_passed_to_load_config(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "c1"
        mock_proj.project_dir = str(tmp_path / "c1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        run_full_pipeline("t", "b", config_dir="/custom/config")
        mock_config.assert_called_once_with(config_dir="/custom/config")

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_tenant_id_passed_to_project(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "t1"
        mock_proj.project_dir = str(tmp_path / "t1")
        mock_project.init.return_value = mock_proj

        mock_build.return_value = [_AlwaysPassGate()]

        run_full_pipeline("t", "b", tenant_id="acme")
        mock_project.init.assert_called_once_with("t", "b", base_dir=None, tenant_id="acme")

    @patch("automedia.hitl.config.HITLConfig")
    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_hitl_config_in_context(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        mock_hitl: MagicMock,
        tmp_path: Path,
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

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
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

    @patch("automedia.pipelines.image_pipeline.ImagePipeline")
    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_text_with_cover_generates_cover(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        mock_image_pipeline: MagicMock,
        tmp_path: Path,
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

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_video_only_has_fallback_content(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:
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

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_qa_only_has_fallback_content(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:
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

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_auto_mode_not_affected(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:
                captured["content"] = __gate_context.get("content", "")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureContentGate()]

        run_full_pipeline("AI topic", "testbrand", mode="auto")

        # auto mode should NOT have fallback — CW will set content
        content = captured["content"]
        assert content == "", f"auto mode should start with empty content, got {content!r}"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_text_only_mode_not_affected(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

            def execute(self, __gate_context: dict[str, Any]) -> dict[str, Any]:
                captured["content"] = __gate_context.get("content", "")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureContentGate()]

        run_full_pipeline("AI topic", "testbrand", mode="text_only")

        # text_only mode should NOT have fallback — CW will set content
        content = captured["content"]
        assert content == "", f"text_only mode should start with empty content, got {content!r}"


# =========================================================================
# Video-mode honesty tests (health remediation P0-1)
# =========================================================================


class TestVideoModeStatusDowngrade:
    """A video mode with no video artifact must not report ``success``.

    中文说明：这些模式的门预设里含 V 门，而 V 门在没有产出视频时会显式记为
    ``skipped``（``gates/_result.missing_input_result``）。整条视频轨都被跳过
    的运行是**未完成**，不是成功——否则无人值守的运行会以退出码 0 收场，而
    实际上没有交付任何视频。``auto`` 是刻意的例外：它是显式的混合兜底，文本
    轨本身即合法交付物。
    """

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_video_only_without_video_is_partial(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """video_only + no ``video_path`` in context → status ``partial``."""
        mock_proj = MagicMock()
        mock_proj.project_id = "vd01"
        mock_proj.project_dir = str(tmp_path / "vd01")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]

        result = run_full_pipeline("AI topic", "testbrand", mode="video_only")

        assert result.status == "partial"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_short_video_without_video_is_partial(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """short-video + no ``video_path`` in context → status ``partial``."""
        mock_proj = MagicMock()
        mock_proj.project_id = "vd02"
        mock_proj.project_dir = str(tmp_path / "vd02")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]

        result = run_full_pipeline("AI topic", "testbrand", mode="short-video")

        assert result.status == "partial"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_auto_without_video_stays_success(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """auto + no video → still ``success`` (mixed fallback, text track delivers)."""
        mock_proj = MagicMock()
        mock_proj.project_id = "vd03"
        mock_proj.project_dir = str(tmp_path / "vd03")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]

        result = run_full_pipeline("AI topic", "testbrand", mode="auto")

        assert result.status == "success"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_text_only_without_video_stays_success(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """text_only has no V gates in its preset → never downgraded."""
        mock_proj = MagicMock()
        mock_proj.project_id = "vd04"
        mock_proj.project_dir = str(tmp_path / "vd04")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]

        result = run_full_pipeline("AI topic", "testbrand", mode="text_only")

        assert result.status == "success"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_qa_only_without_video_stays_success(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """qa_only 预设含 V1/V6，但从不跑视频产出阶段 → 不得被降级。

        中文说明：这是 §5 降级规则的边界。qa_only 的 V1/V6 在没有视频输入时
        记为 ``skipped``，而该模式本身不产出视频——若把它也算作"欠一个视频"，
        每次运行都会以 partial/退出码 1 收场，那是假失败。
        """
        mock_proj = MagicMock()
        mock_proj.project_id = "vd05"
        mock_proj.project_dir = str(tmp_path / "vd05")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]

        result = run_full_pipeline("AI topic", "testbrand", mode="qa_only")

        assert result.status == "success"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_repurpose_without_video_stays_success(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """repurpose 预设含 V0-V7，但从不跑视频产出阶段 → 不得被降级。"""
        mock_proj = MagicMock()
        mock_proj.project_id = "vd06"
        mock_proj.project_dir = str(tmp_path / "vd06")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]

        result = run_full_pipeline("AI topic", "testbrand", mode="repurpose")

        assert result.status == "success"

    def test_video_producing_modes_are_a_subset_of_v_gate_modes(self) -> None:
        """不变量：欠视频的模式必然在预设里含 V 门。

        中文说明：``_VIDEO_PRODUCING_MODES`` 与视频产出阶段共用同一集合，
        这个断言防止将来编辑 ``_MODE_MAP`` 后两者悄悄脱钩。
        """
        assert _VIDEO_PRODUCING_MODES
        for mode in _VIDEO_PRODUCING_MODES:
            assert mode in _MODE_MAP, f"{mode} 不在 _MODE_MAP 中"
            assert any(name.startswith("V") for name in _MODE_MAP[mode]), (
                f"{mode} 被声明为欠视频的模式，但预设里没有 V 门"
            )

    def test_qa_only_and_repurpose_are_not_video_producing(self) -> None:
        """边界：含 V 门但无视频产出阶段的模式不得进入欠视频集合。"""
        assert "qa_only" not in _VIDEO_PRODUCING_MODES
        assert "repurpose" not in _VIDEO_PRODUCING_MODES
        assert "auto" not in _VIDEO_PRODUCING_MODES


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

    def test_youtube_is_video_first(self) -> None:
        assert _PLATFORM_CATEGORIES["youtube"] == "video-first"

    def test_twitter_is_text_first(self) -> None:
        assert _PLATFORM_CATEGORIES["twitter"] == "text-first"

    def test_bilibili_is_video_first(self) -> None:
        assert _PLATFORM_CATEGORIES["bilibili"] == "video-first"


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

    def test_video_first_returns_auto(self) -> None:
        assert _derive_mode_from_platforms(["youtube"]) == "auto"
        assert _derive_mode_from_platforms(["bilibili"]) == "auto"

    def test_notification_only_returns_text_only(self) -> None:
        assert _derive_mode_from_platforms(["feishu"]) == "text_only"

    def test_mixed_text_and_notification_returns_text_only(self) -> None:
        assert _derive_mode_from_platforms(["wechat", "feishu"]) == "text_only"

    def test_mixed_text_and_social_returns_auto(self) -> None:
        assert _derive_mode_from_platforms(["wechat", "xiaohongshu"]) == "auto"
        assert _derive_mode_from_platforms(["zhihu", "xiaohongshu"]) == "auto"
        assert _derive_mode_from_platforms(["wechat", "zhihu", "xiaohongshu"]) == "auto"

    def test_text_and_video_first_returns_auto(self) -> None:
        assert _derive_mode_from_platforms(["wechat", "youtube"]) == "auto"
        assert _derive_mode_from_platforms(["zhihu", "bilibili"]) == "auto"
        assert _derive_mode_from_platforms(["twitter", "youtube"]) == "auto"

    def test_unknown_platform_treated_as_text_first(self) -> None:
        assert _derive_mode_from_platforms(["unknown_platform"]) == "text_only"

    def test_unknown_with_multimedia_returns_auto(self) -> None:
        assert _derive_mode_from_platforms(["unknown", "xiaohongshu"]) == "auto"
        assert _derive_mode_from_platforms(["unknown", "youtube"]) == "auto"
        assert _derive_mode_from_platforms(["unknown", "bilibili"]) == "auto"

    def test_text_first_platforms_return_text_only(self) -> None:
        assert _derive_mode_from_platforms(["twitter"]) == "text_only"
        assert _derive_mode_from_platforms(["wechat", "twitter"]) == "text_only"

    def test_all_notification_returns_text_only(self) -> None:
        assert _derive_mode_from_platforms(["feishu", "feishu"]) == "text_only"


class TestRunFullPipelineModeDerivation:
    """run_full_pipeline auto-derives mode from brand platforms."""

    @pytest.fixture(autouse=True)
    def _no_tier_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """These tests assert full mode gate lists — tier override must be off."""
        monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)

    def _make_mock_profile(
        self,
        platforms: list[str] | None = None,
    ) -> BrandProfile:
        return BrandProfile(
            brand_name="testbrand",
            platforms=platforms or [],
        )

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_text_only_platforms_derive_text_only(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

        def capture(names: list[str], **kwargs: object) -> list[BaseGate]:
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

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_mixed_social_platforms_derive_auto(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

        def capture(names: list[str], **kwargs: object) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"

        # Should use auto gate list (includes V gates)
        built = captured_names[0]
        assert "V0" in built, "auto mode should include V0"
        assert built == _MODE_MAP["auto"]

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_explicit_mode_overrides_derivation(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

        def capture(names: list[str], **kwargs: object) -> list[BaseGate]:
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

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_no_platforms_keeps_default_mode(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

        def capture(names: list[str], **kwargs: object) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"

        built = captured_names[0]
        assert built == _MODE_MAP["auto"]

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_brand_platforms_in_gate_context(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                captured_ctx["brand_platforms"] = gate_context.get("brand_platforms", [])
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureCtxGate()]

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"
        assert captured_ctx["brand_platforms"] == ["wechat", "xiaohongshu"]

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_no_brand_platforms_empty_list_in_context(
        self,
        mock_load_profiles: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
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

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                captured_ctx["brand_platforms"] = gate_context.get("brand_platforms", "MISSING")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureCtxGate()]

        result = run_full_pipeline("t", "testbrand")
        assert result.status == "success"
        assert captured_ctx["brand_platforms"] == []


class TestPreLockBehavior:
    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_returns_pipeline_result(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        from automedia.pipelines.gate_engine import PipelineResult

        mock_proj = MagicMock()
        mock_proj.project_id = "pre1"
        mock_proj.project_dir = str(tmp_path / "pre1")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]
        result = run_full_pipeline("topic", "brand")
        assert isinstance(result, PipelineResult)

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_topic_brand_mode_passed_through(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "pre2"
        mock_proj.project_dir = str(tmp_path / "pre2")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]
        result = run_full_pipeline("My Topic", "my-brand", mode="text_only")
        assert result.topic == "My Topic"
        assert result.brand == "my-brand"

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_project_dir_created(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "pre3"
        mock_proj.project_dir = str(tmp_path / "pre3")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_AlwaysPassGate()]
        run_full_pipeline("t", "b", tenant_id="acme")
        mock_project.init.assert_called_once_with("t", "b", base_dir=None, tenant_id="acme")

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_gate_engine_receives_correct_gates(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_proj = MagicMock()
        mock_proj.project_id = "pre4"
        mock_proj.project_dir = str(tmp_path / "pre4")
        mock_project.init.return_value = mock_proj
        captured_names: list[list[str]] = []

        def capture(names: list[str], **kwargs: object) -> list[BaseGate]:
            captured_names.append(names)
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture
        result = run_full_pipeline("t", "b", mode="auto")
        assert result.status == "success"
        assert captured_names[0][0] == "pre-gate"
        assert len(captured_names[0]) > 10

    @patch("automedia.core.config_loader.load_config", side_effect=RuntimeError("fail"))
    def test_error_returns_failed_result(
        self,
        mock_config: MagicMock,
    ) -> None:
        from automedia.pipelines.gate_engine import PipelineResult

        result = run_full_pipeline("t", "b")
        assert isinstance(result, PipelineResult)
        assert result.status == "failed"
        assert "fail" in (result.error or "")


# =========================================================================
# Override gate rules integration tests
# =========================================================================


def _setup_override_rules(tmp_path: Path, home: str | Path | None = None) -> Path:
    """Create ``~/.automedia/overrides/rules/`` layout and return the home dir."""
    home = Path(tmp_path / "home") if home is None else Path(home)
    rules_dir = home / ".automedia" / "overrides" / "rules"
    rules_dir.mkdir(parents=True)
    return home


class TestOverrideGateRules:
    """YAML override rules affect final gate list via _select_gates."""

    @pytest.fixture
    def mock_progress(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def brand_profile_none(self) -> None:
        return None

    def _patch_home(self, monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
        monkeypatch.setattr("os.path.expanduser", lambda p: str(home) if p == "~" else p)

    def test_override_adds_gate(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """YAML override rule adding V0 to text_only mode appears in final gate list."""
        home = _setup_override_rules(tmp_path)
        (home / ".automedia" / "overrides" / "rules" / "add_v0.yaml").write_text(
            "gates:\n  include:\n    - V0\n"
        )
        self._patch_home(monkeypatch, home)

        gate_names, _gates = _select_gates(
            mode="text_only",
            brand_profile=None,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=mock_progress,
            workflow_obj=None,
            brand="my-brand",
        )
        assert "V0" in gate_names, "V0 should be included by override rule"

    def test_override_excludes_gate(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """YAML override rule excluding V0 from auto mode removes it."""
        home = _setup_override_rules(tmp_path)
        (home / ".automedia" / "overrides" / "rules" / "exclude_v0.yaml").write_text(
            "gates:\n  exclude:\n    - V0\n"
        )
        self._patch_home(monkeypatch, home)

        gate_names, _gates = _select_gates(
            mode="auto",
            brand_profile=None,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=mock_progress,
            workflow_obj=None,
            brand="my-brand",
        )
        assert "V0" not in gate_names, "V0 should be excluded by override rule"

    def test_brand_scoped_override_ignores_other_brand(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """Brand-scoped override only affects the matching brand."""
        home = _setup_override_rules(tmp_path)
        (home / ".automedia" / "overrides" / "rules" / "acme_only.yaml").write_text(
            "brand: Acme\ngates:\n  include:\n    - V0\n"
        )
        self._patch_home(monkeypatch, home)

        # Other brand should NOT get V0
        gate_names, _gates = _select_gates(
            mode="text_only",
            brand_profile=None,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=mock_progress,
            workflow_obj=None,
            brand="other-brand",
        )
        assert "V0" not in gate_names, "V0 should not appear for non-matching brand"

    def test_brand_scoped_override_affects_matching_brand(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """Brand-scoped override includes gate for the matching brand."""
        home = _setup_override_rules(tmp_path)
        (home / ".automedia" / "overrides" / "rules" / "acme_only.yaml").write_text(
            "brand: Acme\ngates:\n  include:\n    - V0\n"
        )
        self._patch_home(monkeypatch, home)

        gate_names, _gates = _select_gates(
            mode="text_only",
            brand_profile=None,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=mock_progress,
            workflow_obj=None,
            brand="Acme",
        )
        assert "V0" in gate_names, "V0 should appear for matching brand Acme"

    def test_multiple_override_rules_merge(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """Multiple YAML rule files have their gate modifiers merged (union)."""
        home = _setup_override_rules(tmp_path)
        (home / ".automedia" / "overrides" / "rules" / "add_v0.yaml").write_text(
            "gates:\n  include:\n    - V0\n"
        )
        (home / ".automedia" / "overrides" / "rules" / "add_v7.yaml").write_text(
            "gates:\n  include:\n    - V7\n"
        )
        self._patch_home(monkeypatch, home)

        gate_names, _gates = _select_gates(
            mode="text_only",
            brand_profile=None,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=mock_progress,
            workflow_obj=None,
            brand="my-brand",
        )
        assert "V0" in gate_names, "V0 should be included from first rule"
        assert "V7" in gate_names, "V7 should be included from second rule"

    def test_override_rules_merge_with_brand_profile_modifiers(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """Override rules stack on top of brand profile platform modifiers."""
        import automedia.gates  # noqa: F401

        home = _setup_override_rules(tmp_path)
        (home / ".automedia" / "overrides" / "rules" / "add_v0.yaml").write_text(
            "gates:\n  include:\n    - V0\n"
        )
        self._patch_home(monkeypatch, home)

        brand_profile = BrandProfile(platforms=["wechat"])

        gate_names, _gates = _select_gates(
            mode="text_only",
            brand_profile=brand_profile,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=mock_progress,
            workflow_obj=None,
            brand="my-brand",
        )
        assert "V0" in gate_names, "V0 should be included by override rule on top of brand profile"

    def test_override_validates_unknown_gate_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """Override rule referencing unknown gate raises ValueError via validate_gate_modifiers."""
        import automedia.gates  # noqa: F401

        home = _setup_override_rules(tmp_path)
        (home / ".automedia" / "overrides" / "rules" / "bad_gate.yaml").write_text(
            "gates:\n  include:\n    - NONEXISTENT_GATE_99\n"
        )
        self._patch_home(monkeypatch, home)

        with pytest.raises(ValueError, match="NONEXISTENT_GATE_99"):
            _select_gates(
                mode="text_only",
                brand_profile=None,
                resume_from=None,
                project_dir=str(tmp_path / "proj"),
                progress=mock_progress,
                workflow_obj=None,
                brand="my-brand",
            )

    def test_no_overrides_dir_no_change(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_progress: MagicMock,
    ) -> None:
        """When no overrides dir exists, gate list is unchanged."""
        monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)
        empty_home = tmp_path / "empty_home"
        empty_home.mkdir()
        self._patch_home(monkeypatch, empty_home)

        gate_names, _gates = _select_gates(
            mode="text_only",
            brand_profile=None,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=mock_progress,
            workflow_obj=None,
            brand="my-brand",
        )
        assert gate_names == list(_TEXT_ONLY_GATE_NAMES)


# =========================================================================
# Tier enforcement at gate-list composition points (plan todo 17)
# =========================================================================


class TestTierEnforcementComposeGateList:
    """_compose_gate_list drops tier-restricted gates when an override is set."""

    def test_no_override_gate_list_byte_identical(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no tier override, every mode's gate list is unchanged."""
        monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)
        for mode, expected in _MODE_MAP.items():
            gate_names, override_fm = _compose_gate_list(mode)
            assert gate_names == list(expected), f"mode {mode} changed with no override"
            assert override_fm == {}

    def test_core_override_drops_pro_gates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOMEDIA_FEATURE_TIER=core drops pro/enterprise gates from the list."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        gate_names, _ = _compose_gate_list("auto")
        assert "V7" not in gate_names
        assert "G1" not in gate_names
        # Core gates stay
        assert "CW" in gate_names
        assert "G0" in gate_names

    def test_pro_override_drops_enterprise_gates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOMEDIA_FEATURE_TIER=pro drops enterprise gates (L3), keeps pro."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "pro")
        gate_names, _ = _compose_gate_list("auto")
        assert "L3" not in gate_names
        assert "V7" in gate_names  # pro gates still available

    def test_invalid_override_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A typo'd override value is ignored — full list preserved."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "enterprize")
        gate_names, _ = _compose_gate_list("auto")
        assert gate_names == list(_AUTO_GATE_NAMES)


class TestTierEnforcementSelectGates:
    """_select_gates applies tier filtering to the final composed list."""

    def test_no_override_select_gates_unchanged(self) -> None:
        """No override: _select_gates returns the mode's full list."""
        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)
            gate_names, gates = _select_gates(
                mode="text_only",
                brand_profile=None,
                resume_from=None,
                project_dir=".",
                progress=None,
            )
            assert gate_names == list(_TEXT_ONLY_GATE_NAMES)
            assert [g.gate_name for g in gates] == list(_TEXT_ONLY_GATE_NAMES)
        finally:
            monkeypatch.undo()

    def test_core_override_select_gates_drops_v7(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With AUTOMEDIA_FEATURE_TIER=core, _select_gates excludes V7 + warns."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        gate_names, gates = _select_gates(
            mode="short-video",
            brand_profile=None,
            resume_from=None,
            project_dir=str(tmp_path / "proj"),
            progress=None,
        )
        assert "V7" not in gate_names
        assert "V7" not in [g.gate_name for g in gates]

    def test_tier_filter_applies_after_modifiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A modifier-included pro gate is still dropped under a core override."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        gate_names, _ = _compose_gate_list("text_only", {"gates": {"include": ["V7"]}})
        assert "V7" not in gate_names


class TestTierEnforcementBuildGates:
    """_build_gates_from_names drops unavailable gates near the head."""

    def test_no_override_builds_all(self) -> None:
        """No override: every requested name instantiates (KeyError semantics kept)."""
        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)
            gates = _build_gates_from_names(["G0", "V7", "H0"])
            assert [g.gate_name for g in gates] == ["G0", "V7", "H0"]
        finally:
            monkeypatch.undo()

    def test_core_override_drops_pro_gates_with_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """V7 (pro) dropped under core override, warning logged, core gates kept.

        The warning is asserted via a MagicMock patched over the module-level
        ``runner.log`` — not ``capture_logs()``, which cannot intercept the
        logger once ``cache_logger_on_first_use`` has bound it and a later
        ``structlog.configure`` swapped the processor list (ordering pollution
        under the full suite).
        """
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        mock_log = MagicMock()
        monkeypatch.setattr("automedia.pipelines.runner.log", mock_log)
        gates = _build_gates_from_names(["G0", "V7", "CW"])
        assert [g.gate_name for g in gates] == ["G0", "CW"]
        warning_events = [
            c
            for c in mock_log.warning.call_args_list
            if c.args and c.args[0] == "gate.V7.skipped_tier_gate"
        ]
        assert warning_events, "no skipped_tier_gate warning for V7"
        assert warning_events[0].kwargs.get("tier") == "pro"

    def test_unknown_names_pass_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Names not in the tier table are untouched — KeyError semantics preserved."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        with pytest.raises(KeyError, match="NONEXISTENT_XYZ"):
            _build_gates_from_names(["NONEXISTENT_XYZ"])

    def test_override_failure_mode_skips_dropped_gates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """override_failure_mode for a dropped gate must not KeyError on it."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        gates = _build_gates_from_names(["G0", "V7"], override_failure_mode={"V7": "stop"})
        assert [g.gate_name for g in gates] == ["G0"]


class TestTierEnforcementRunFullPipeline:
    """End-to-end: run_full_pipeline composes a tier-filtered gate list."""

    def _capture_composed_names(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        tmp_path: Path,
        project_id: str,
    ) -> list[list[str]]:
        mock_proj = MagicMock()
        mock_proj.project_id = project_id
        mock_proj.project_dir = str(tmp_path / project_id)
        mock_project.init.return_value = mock_proj

        captured: list[list[str]] = []

        def capture(names: list[str], **kwargs: object) -> list[BaseGate]:
            captured.append(list(names))
            return [_AlwaysPassGate()]

        mock_build.side_effect = capture
        return captured

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_no_override_v7_in_composed_list(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With no override the composed list passed to the engine includes V7."""
        monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)
        captured = self._capture_composed_names(
            mock_record, mock_build, mock_project, tmp_path, "tier0"
        )
        result = run_full_pipeline("topic", "brand", mode="auto")
        assert result.status == "success"
        assert captured and "V7" in captured[0]

    @patch("automedia.core.config_loader.load_config", return_value={})
    @patch("automedia.core.project.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    def test_core_override_v7_dropped_from_run(
        self,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With AUTOMEDIA_FEATURE_TIER=core, run composes its list without V7."""
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        captured = self._capture_composed_names(
            mock_record, mock_build, mock_project, tmp_path, "tierc"
        )
        result = run_full_pipeline("topic", "brand", mode="auto")
        assert result.status == "success"
        assert captured and "V7" not in captured[0]
