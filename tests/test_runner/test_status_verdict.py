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
