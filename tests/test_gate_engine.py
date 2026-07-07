"""Tests for GateEngine — sequential pipeline executor."""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates.base import BaseGate
from automedia.hooks.protocol import GateObserver
from automedia.pipelines.gate_engine import (
    AssetInfo,
    GateEngine,
    GateLogEntry,
    Pipeline,
    PipelineResult,
)


# ---------------------------------------------------------------------------
# Helpers — lightweight gate stubs
# ---------------------------------------------------------------------------


class _PassGate(BaseGate):
    """Always passes."""

    _gate_name = "TEST_PASS"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


class _FailStopGate(BaseGate):
    """Always fails with failure_mode='stop'."""

    _gate_name = "TEST_FAIL_STOP"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "gate": self.gate_name, "error": "boom"}


class _FailRewriteGate(BaseGate):
    """Always fails with failure_mode='rewrite'."""

    _gate_name = "TEST_FAIL_REWRITE"
    _failure_mode = "rewrite"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "gate": self.gate_name, "error": "rewrite me"}


class _ErrorGate(BaseGate):
    """Raises an exception during execute."""

    _gate_name = "TEST_ERROR"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("gate crashed")


class _ErrorRewriteGate(BaseGate):
    """Raises an exception but failure_mode='rewrite'."""

    _gate_name = "TEST_ERROR_REWRITE"
    _failure_mode = "rewrite"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("soft crash")


class _ContextCaptureGate(BaseGate):
    """Captures the context for inspection."""

    _gate_name = "TEST_CAPTURE"
    _failure_mode = "stop"

    def __init__(self) -> None:
        self.captured_context: dict[str, Any] = {}

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        self.captured_context = dict(gate_context)
        return {"passed": True, "gate": self.gate_name}


class _OutputGate(BaseGate):
    """Writes to gate_context to simulate downstream data passing."""

    _gate_name = "TEST_OUTPUT"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        gate_context["output_files"] = [
            {"type": "video", "path": "/tmp/out.mp4", "platform": "bilibili"}
        ]
        return {"passed": True, "gate": self.gate_name}


class _RecordingHook(GateObserver):
    """Records every lifecycle call for assertions."""

    def __init__(self) -> None:
        self.before_calls: list[tuple[str, dict[str, Any]]] = []
        self.after_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.failed_calls: list[tuple[str, dict[str, Any], Exception]] = []

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        self.before_calls.append((gate_name, context))

    def after_gate(
        self, gate_name: str, context: dict[str, Any], result: dict[str, Any]
    ) -> None:
        self.after_calls.append((gate_name, context, result))

    def on_gate_failed(
        self, gate_name: str, context: dict[str, Any], error: Exception
    ) -> None:
        self.failed_calls.append((gate_name, context, error))


# =========================================================================
# Data class tests
# =========================================================================


class TestDataClasses:
    """AssetInfo, GateLogEntry, PipelineResult construction."""

    def test_asset_info_defaults(self) -> None:
        a = AssetInfo(type="video", path="/tmp/v.mp4")
        assert a.type == "video"
        assert a.path == "/tmp/v.mp4"
        assert a.platform == ""
        assert a.md5 == ""

    def test_asset_info_full(self) -> None:
        a = AssetInfo(
            type="image", path="/tmp/i.png", platform="wechat", md5="abc123"
        )
        assert a.platform == "wechat"
        assert a.md5 == "abc123"

    def test_gate_log_entry_passed(self) -> None:
        e = GateLogEntry(gate_name="G0", status="passed", duration_s=1.5)
        assert e.gate_name == "G0"
        assert e.error is None

    def test_gate_log_entry_failed(self) -> None:
        e = GateLogEntry(
            gate_name="G3", status="failed", duration_s=0.3, error="bad brand"
        )
        assert e.error == "bad brand"

    def test_pipeline_result_defaults(self) -> None:
        r = PipelineResult()
        assert r.status == "success"
        assert r.project_id == ""
        assert r.assets == []
        assert r.gates_log == []
        assert r.error is None

    def test_pipeline_result_full(self) -> None:
        r = PipelineResult(
            status="failed",
            project_id="abc123",
            project_dir="/tmp/proj",
            topic="AI",
            brand="test",
            assets=[AssetInfo(type="v", path="/tmp/v")],
            gates_log=[GateLogEntry(gate_name="G0", status="passed", duration_s=1)],
            start_time=100.0,
            end_time=105.0,
            total_duration_s=5.0,
            error="oops",
        )
        assert r.status == "failed"
        assert len(r.assets) == 1
        assert len(r.gates_log) == 1


# =========================================================================
# GateEngine.run() tests
# =========================================================================


class TestGateEngineRun:
    """GateEngine.run() basic behaviour."""

    def test_empty_gates_returns_true(self) -> None:
        engine = GateEngine([])
        ok, results = engine.run({})
        assert ok is True
        assert results == []

    def test_single_passing_gate(self) -> None:
        engine = GateEngine([_PassGate()])
        ok, results = engine.run({})
        assert ok is True
        assert len(results) == 1
        assert results[0]["passed"] is True

    def test_stop_on_failure(self) -> None:
        """A failing stop gate halts the pipeline."""
        engine = GateEngine([_FailStopGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is False
        assert len(results) == 1  # second gate never ran

    def test_rewrite_does_not_stop(self) -> None:
        """A failing rewrite gate does NOT halt the pipeline."""
        engine = GateEngine([_FailRewriteGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is False  # overall still failed
        assert len(results) == 2  # second gate DID run

    def test_exception_in_stop_gate_stops(self) -> None:
        """An exception in a stop gate halts the pipeline."""
        engine = GateEngine([_ErrorGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is False
        assert len(results) == 1
        assert results[0]["passed"] is False
        assert "gate crashed" in results[0]["error"]

    def test_exception_in_rewrite_gate_continues(self) -> None:
        """An exception in a rewrite gate does NOT halt the pipeline."""
        engine = GateEngine([_ErrorRewriteGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is False
        assert len(results) == 2

    def test_gate_context_gets_gate_name(self) -> None:
        """gate_context['_gate_name'] is set before each gate runs."""
        cap = _ContextCaptureGate()
        engine = GateEngine([cap])
        engine.run({"topic": "test"})
        assert cap.captured_context["_gate_name"] == "TEST_CAPTURE"

    def test_multiple_passing_gates(self) -> None:
        engine = GateEngine([_PassGate(), _PassGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is True
        assert len(results) == 3

    def test_fail_stop_in_middle(self) -> None:
        """Failing stop gate in the middle skips remaining gates."""
        engine = GateEngine(
            [_PassGate(), _FailStopGate(), _PassGate()]
        )
        ok, results = engine.run({})
        assert ok is False
        assert len(results) == 2  # third gate skipped


# =========================================================================
# GateEngine.run_with_results() tests
# =========================================================================


class TestGateEngineRunWithResults:
    """GateEngine.run_with_results() always returns full result list."""

    def test_empty_gates(self) -> None:
        engine = GateEngine([])
        results = engine.run_with_results({})
        assert results == []

    def test_stop_gate_returns_only_up_to_failure(self) -> None:
        engine = GateEngine([_PassGate(), _FailStopGate(), _PassGate()])
        results = engine.run_with_results({})
        assert len(results) == 2  # stops after fail_stop

    def test_rewrite_gate_allows_full_run(self) -> None:
        engine = GateEngine([_FailRewriteGate(), _PassGate()])
        results = engine.run_with_results({})
        assert len(results) == 2

    def test_all_passing(self) -> None:
        engine = GateEngine([_PassGate(), _PassGate()])
        results = engine.run_with_results({})
        assert len(results) == 2
        assert all(r["passed"] for r in results)


# =========================================================================
# Hook dispatch tests
# =========================================================================


class TestHookDispatch:
    """Hooks are called at the correct lifecycle points."""

    def test_before_gate_called(self) -> None:
        hook = _RecordingHook()
        engine = GateEngine([_PassGate()], hooks=[hook])
        engine.run({})
        assert len(hook.before_calls) == 1
        assert hook.before_calls[0][0] == "TEST_PASS"

    def test_after_gate_called_on_pass(self) -> None:
        hook = _RecordingHook()
        engine = GateEngine([_PassGate()], hooks=[hook])
        engine.run({})
        assert len(hook.after_calls) == 1
        assert hook.after_calls[0][2]["passed"] is True

    def test_on_gate_failed_called_on_exception(self) -> None:
        hook = _RecordingHook()
        engine = GateEngine([_ErrorGate()], hooks=[hook])
        engine.run({})
        assert len(hook.failed_calls) == 1
        assert "gate crashed" in str(hook.failed_calls[0][2])

    def test_on_gate_failed_not_called_on_result_failure(self) -> None:
        """on_gate_failed is only for exceptions, not result-level failures."""
        hook = _RecordingHook()
        engine = GateEngine([_FailStopGate()], hooks=[hook])
        engine.run({})
        assert len(hook.failed_calls) == 0
        # But before_gate was called
        assert len(hook.before_calls) == 1

    def test_rewrite_failure_calls_after_gate(self) -> None:
        """A failing rewrite gate still calls after_gate (not on_gate_failed)."""
        hook = _RecordingHook()
        engine = GateEngine([_FailRewriteGate()], hooks=[hook])
        engine.run({})
        assert len(hook.after_calls) == 1
        assert len(hook.failed_calls) == 0

    def test_context_shared_with_hook(self) -> None:
        """Hook receives the same context dict as the gate."""
        hook = _RecordingHook()
        engine = GateEngine([_PassGate()], hooks=[hook])
        ctx = {"key": "value"}
        engine.run(ctx)
        assert hook.before_calls[0][1] is ctx

    def test_multiple_hooks(self) -> None:
        h1 = _RecordingHook()
        h2 = _RecordingHook()
        engine = GateEngine([_PassGate()], hooks=[h1, h2])
        engine.run({})
        assert len(h1.before_calls) == 1
        assert len(h2.before_calls) == 1

    def test_no_hooks_does_not_crash(self) -> None:
        engine = GateEngine([_PassGate()], hooks=None)
        ok, _ = engine.run({})
        assert ok is True


# =========================================================================
# Pipeline alias
# =========================================================================


class TestPipelineAlias:
    """Pipeline is an alias for GateEngine."""

    def test_pipeline_is_gate_engine(self) -> None:
        assert Pipeline is GateEngine

    def test_pipeline_works(self) -> None:
        p = Pipeline([_PassGate()])
        ok, _ = p.run({})
        assert ok is True


# =========================================================================
# Context mutation
# =========================================================================


class TestContextMutation:
    """Gates can mutate the context for downstream gates."""

    def test_output_gate_writes_to_context(self) -> None:
        engine = GateEngine([_OutputGate()])
        ctx: dict[str, Any] = {}
        engine.run(ctx)
        assert "output_files" in ctx
        assert ctx["output_files"][0]["type"] == "video"
