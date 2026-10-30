"""``GateEngine`` reports success only when every gate ended in a passing state.

Regression lock for the P0 where the engine's verdict was a last-write-wins
accumulator: a retry-mode gate that exhausted its retries in a CW-less mode
(``qa_only``, ``video_only``) left a failed row in ``results`` while a later
passing gate reset the flag.  ``run()`` returned ``True``, so
``PipelineResult.status`` became ``"success"`` and the CLI exited 0 —
contradicting the gate log, the gate-report and the nightly DoD.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.pipelines.gate_engine import GateEngine, _verdict_from_results
from automedia.pipelines.runner import _MODE_MAP, _finalize_pipeline


class TestVerdictFromResults:
    def test_all_passed(self) -> None:
        assert _verdict_from_results([{"passed": True}, {"passed": True}]) is True

    def test_any_failure(self) -> None:
        assert _verdict_from_results([{"passed": True}, {"passed": False}]) is False

    def test_failure_followed_by_pass_is_still_failure(self) -> None:
        assert _verdict_from_results([{"passed": False}, {"passed": True}]) is False

    def test_skipped_gate_counts_as_pass(self) -> None:
        assert _verdict_from_results([{"passed": True, "status": "skipped"}]) is True

    def test_empty_result_list_is_success(self) -> None:
        assert _verdict_from_results([]) is True


def _gates_for(mode: str, failing: str) -> list[Any]:
    import automedia.gates  # noqa: F401 — import registers every gate class
    from automedia.gates.base import _registry

    gates = [_registry.get(name)() for name in _MODE_MAP[mode]]
    for gate in gates:
        name = gate.gate_name
        passed = name != failing
        gate.execute = types.MethodType(
            lambda self, ctx, _name=name, _passed=passed: {
                "passed": _passed,
                "gate": _name,
                "error": "" if _passed else "forced failure",
            },
            gate,
        )
    return gates


class TestRetryExhaustionIsNotSuccess:
    @pytest.mark.parametrize(("mode", "failing"), [("qa_only", "G2"), ("video_only", "V5")])
    def test_cwless_retry_failure_is_not_success(self, mode: str, failing: str) -> None:
        engine = GateEngine(
            gates=_gates_for(mode, failing), max_quality_retries=0, max_regenerations=2
        )
        ok, results = engine.run({"content": "x"})

        assert ok is False
        assert any(r["passed"] is False for r in results)

    def test_later_passing_gate_cannot_erase_the_failure(self) -> None:
        engine = GateEngine(
            gates=_gates_for("qa_only", "G2"), max_quality_retries=0, max_regenerations=2
        )
        ok, results = engine.run({"content": "x"})

        assert results[-1]["passed"] is True
        assert [r["gate"] for r in results][-1] != "G2"
        assert ok is False


class TestRecoveryKeepsSuccess:
    def test_quality_retry_recovery_is_success(self) -> None:
        import automedia.gates  # noqa: F401 — import registers every gate class
        from automedia.gates.base import _registry

        gate = _registry.get("G2")()
        calls = {"n": 0}

        def flaky(self: Any, ctx: Any) -> dict[str, Any]:
            calls["n"] += 1
            return {"passed": calls["n"] > 1, "gate": "G2", "error": "first attempt"}

        gate.execute = types.MethodType(flaky, gate)
        engine = GateEngine(gates=[gate], max_quality_retries=1, max_regenerations=0)
        ok, results = engine.run({"content": "x"})

        assert calls["n"] == 2
        assert ok is True
        assert [r["passed"] for r in results] == [True]


class TestPipelineStatusFollowsVerdict:
    @pytest.fixture()
    def project(self, tmp_path: Path) -> MagicMock:
        proj = MagicMock()
        proj.project_id = "proj-verdict-1"
        proj.project_dir = str(tmp_path)
        return proj

    def _run_and_finalize(self, project: MagicMock, mode: str, failing: str) -> Any:
        engine = GateEngine(
            gates=_gates_for(mode, failing), max_quality_retries=0, max_regenerations=2
        )
        ok, results = engine.run({"content": "x"})
        with patch(
            "automedia.core.llm_client.get_usage_summary",
            return_value={"total_tokens": 0},
        ):
            return _finalize_pipeline(
                success=ok,
                results=results,
                mode=mode,
                gate_context={},
                project=project,
                config={},
                brand="b",
                topic="t",
                start=0.0,
                workflow=None,
            )

    def test_failed_run_is_partial(self, project: MagicMock) -> None:
        result = self._run_and_finalize(project, "video_only", "V5")

        assert result.status == "partial"
        assert [e.gate_name for e in result.gates_log if e.status == "failed"] == ["V5"]

    def test_clean_run_is_success(self, project: MagicMock) -> None:
        result = self._run_and_finalize(project, "video_only", "")

        assert result.status == "success"
        assert [e.gate_name for e in result.gates_log if e.status == "failed"] == []


class TestOwedVideoDowngradeHint:
    """欠视频的运行产出为零时降级 partial，且提示区分两种空转形态（issue #342）。

    中文说明：``video_only`` 不带源材料跑媒体阶段时零产物——修复前唯一信号
    是 ``log.info`` 加 V 门整排 ``skipped``，报告里与"正常跳过"无法区分。降级
    到 ``partial`` 的行为本身早已存在（#152）；这里锁定的是它的两条提示路径：
    "媒体阶段什么都没产出"与"产出了音频但没视频"必须可辨。
    """

    @pytest.fixture()
    def project(self, tmp_path: Path) -> MagicMock:
        proj = MagicMock()
        proj.project_id = "proj-owed-video"
        proj.project_dir = str(tmp_path)
        return proj

    def _finalize(self, project: MagicMock, gate_context: dict[str, Any]) -> Any:
        with (
            patch(
                "automedia.core.llm_client.get_usage_summary",
                return_value={"total_tokens": 0},
            ),
            patch("automedia.pipelines.runner.log") as mock_log,
        ):
            result = _finalize_pipeline(
                success=True,
                results=[],
                mode="video_only",
                gate_context=gate_context,
                project=project,
                config={},
                brand="b",
                topic="t",
                start=0.0,
                workflow=None,
                owes_video=True,
            )
        events = [
            call
            for call in mock_log.warning.call_args_list
            if call.args and call.args[0] == "pipeline.video_not_produced"
        ]
        return result, events

    @staticmethod
    def _latest_report_json(project_dir: str) -> dict[str, Any]:
        import json
        import os

        report_dir = os.path.join(project_dir, "05_review", "gate-report")
        files = sorted(f for f in os.listdir(report_dir) if f.endswith(".json"))
        with open(os.path.join(report_dir, files[-1]), encoding="utf-8") as fh:
            return json.load(fh)

    def test_zero_artifacts_downgrade_names_the_media_stage(self, project: MagicMock) -> None:
        """媒体阶段零产物（无正文等）⇒ partial，提示指向媒体阶段本身，
        gate-report 带上 ``no_content`` 注记（issue #342 主体）。"""
        result, events = self._finalize(project, {"mode": "video_only"})

        assert result.status == "partial"
        assert events, "video_not_produced event was not logged"
        assert "no artifacts at all" in events[0].kwargs["hint"]

        report = self._latest_report_json(project.project_dir)
        assert report["media_stage"]["notes"][0]["event"] == "no_content"

    def test_audio_without_video_downgrade_names_the_video_engine(self, project: MagicMock) -> None:
        """产出了音频但没视频 ⇒ partial，提示保持指向视频引擎配置。"""
        ctx: dict[str, Any] = {
            "mode": "video_only",
            "audio_path": "/proj/03_audio/narration.mp3",
            "required_files": ["/proj/03_audio/narration.mp3"],
        }
        result, events = self._finalize(project, ctx)

        assert result.status == "partial"
        assert events
        assert "no video artifact was produced" in events[0].kwargs["hint"]

        report = self._latest_report_json(project.project_dir)
        assert report["media_stage"]["produced_files"] == ["/proj/03_audio/narration.mp3"]
