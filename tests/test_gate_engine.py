"""Tests for GateEngine — sequential pipeline executor."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from automedia.gates.base import BaseGate
from automedia.hooks.protocol import GateObserver
from automedia.pipelines.gate_engine import (
    AssetInfo,
    GateEngine,
    GateLogEntry,
    Pipeline,
    PipelineProgress,
    PipelineResult,
)

# ---------------------------------------------------------------------------
# Helpers — lightweight gate stubs
# ---------------------------------------------------------------------------


class _PassGate(BaseGate):
    """Always passes."""

    _gate_name = "G85"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


class _FailStopGate(BaseGate):
    """Always fails with failure_mode='stop'."""

    _gate_name = "G84"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "gate": self.gate_name, "error": "boom"}


class _FailRewriteGate(BaseGate):
    """Always fails with failure_mode='retry'."""

    _gate_name = "G83"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "gate": self.gate_name, "error": "rewrite me"}


class _ErrorGate(BaseGate):
    """Raises an exception during execute."""

    _gate_name = "G82"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("gate crashed")


class _ErrorRewriteGate(BaseGate):
    """Raises a transient exception but failure_mode='retry'."""

    _gate_name = "G81"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("soft crash")


class _ContextCaptureGate(BaseGate):
    """Captures the context for inspection."""

    _gate_name = "G80"
    _failure_mode = "stop"

    def __init__(self) -> None:
        self.captured_context: dict[str, Any] = {}

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        self.captured_context = dict(gate_context)
        return {"passed": True, "gate": self.gate_name}


class _OutputGate(BaseGate):
    """Writes to gate_context to simulate downstream data passing."""

    _gate_name = "G79"
    _failure_mode = "stop"

    def __init__(self, base_dir: str = "/tmp") -> None:
        self.base_dir = base_dir

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        gate_context["output_files"] = [
            {"type": "video", "path": f"{self.base_dir}/out.mp4", "platform": "bilibili"}
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

    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None:
        self.after_calls.append((gate_name, context, result))

    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None:
        self.failed_calls.append((gate_name, context, error))


# =========================================================================
# Data class tests
# =========================================================================


class TestDataClasses:
    """AssetInfo, GateLogEntry, PipelineResult construction."""

    def test_asset_info_defaults(self, tmp_path: Any) -> None:
        p = str(tmp_path / "v.mp4")
        a = AssetInfo(type="video", path=p)
        assert a.type == "video"
        assert a.path == p
        assert a.platform == ""
        assert a.md5 == ""

    def test_asset_info_full(self, tmp_path: Any) -> None:
        a = AssetInfo(type="image", path=str(tmp_path / "i.png"), platform="wechat", md5="abc123")
        assert a.platform == "wechat"
        assert a.md5 == "abc123"

    def test_gate_log_entry_passed(self) -> None:
        e = GateLogEntry(gate_name="G0", status="passed", duration_s=1.5)
        assert e.gate_name == "G0"
        assert e.error is None

    def test_gate_log_entry_failed(self) -> None:
        e = GateLogEntry(gate_name="G3", status="failed", duration_s=0.3, error="bad brand")
        assert e.error == "bad brand"

    def test_pipeline_result_defaults(self) -> None:
        r = PipelineResult()
        assert r.status == "success"
        assert r.project_id == ""
        assert r.assets == []
        assert r.gates_log == []
        assert r.error is None

    def test_pipeline_result_full(self, tmp_path: Any) -> None:
        r = PipelineResult(
            status="failed",
            project_id="abc123",
            project_dir=str(tmp_path / "proj"),
            topic="AI",
            brand="test",
            assets=[AssetInfo(type="v", path=str(tmp_path / "v"))],
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
        assert ok is True  # pipeline completed with stop gate passing
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
        """A transient exception in a rewrite gate does NOT halt the pipeline."""
        engine = GateEngine([_ErrorRewriteGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is True  # pipeline completed with stop gate passing
        assert len(results) == 2

    def test_gate_context_gets_gate_name(self) -> None:
        """gate_context['_gate_name'] is set before each gate runs."""
        cap = _ContextCaptureGate()
        engine = GateEngine([cap])
        engine.run({"topic": "test"})
        assert cap.captured_context["_gate_name"] == "G80"

    def test_multiple_passing_gates(self) -> None:
        engine = GateEngine([_PassGate(), _PassGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is True
        assert len(results) == 3

    def test_fail_stop_in_middle(self) -> None:
        """Failing stop gate in the middle skips remaining gates."""
        engine = GateEngine([_PassGate(), _FailStopGate(), _PassGate()])
        ok, results = engine.run({})
        assert ok is False
        assert len(results) == 2  # third gate skipped

    def test_result_contains_duration_s(self) -> None:
        """Every result dict includes duration_s >= 0."""
        engine = GateEngine([_PassGate(), _FailRewriteGate(), _ErrorGate()])
        _, results = engine.run({})
        assert len(results) >= 1
        for r in results:
            assert "duration_s" in r, f"Missing duration_s in {r.get('gate', '?')}"
            assert r["duration_s"] >= 0.0, f"Negative duration_s in {r.get('gate', '?')}"


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
        assert hook.before_calls[0][0] == "G85"

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

    def test_output_gate_writes_to_context(self, tmp_path: Any) -> None:
        engine = GateEngine([_OutputGate(base_dir=str(tmp_path))])
        ctx: dict[str, Any] = {}
        engine.run(ctx)
        assert "output_files" in ctx
        assert ctx["output_files"][0]["type"] == "video"


# =========================================================================
# Exception categorization helpers (TDD — Issue #2)
# =========================================================================

# Permanent exceptions — should fail immediately even in rewrite mode
_PERMANENT_EXCEPTION_TYPES = (KeyError, ValueError, TypeError)

# Transient exceptions — retriable, may continue in retry mode
_TRANSIENT_EXCEPTION_TYPES = (ConnectionError, TimeoutError)


class _PermanentErrorRewriteGate(BaseGate):
    """Raises ValueError (permanent) with failure_mode='retry'."""

    _gate_name = "G78"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("permanent error — bad input")


class _KeyErrorRewriteGate(BaseGate):
    """Raises KeyError (permanent) with failure_mode='retry'."""

    _gate_name = "G77"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise KeyError("missing required key")


class _TypeErrorRewriteGate(BaseGate):
    """Raises TypeError (permanent) with failure_mode='retry'."""

    _gate_name = "G76"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise TypeError("wrong argument type")


class _TransientConnectionErrorGate(BaseGate):
    """Raises ConnectionError (transient) with failure_mode='retry'."""

    _gate_name = "G75"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("transient — network down")


class _TransientTimeoutErrorGate(BaseGate):
    """Raises TimeoutError (transient) with failure_mode='retry'."""

    _gate_name = "G74"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("transient — request timed out")


class _UnknownErrorRewriteGate(BaseGate):
    """Raises RuntimeError (unknown category) with failure_mode='retry'."""

    _gate_name = "G73"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("unknown error type")


# =========================================================================
# TDD: Exception categorization (Issue #2)
# =========================================================================


class TestExceptionCategorization:
    """Permanent exceptions in retry-mode gates should halt the pipeline.

    Currently (bug): ALL exceptions in retry-mode gates are silently swallowed
    and the pipeline continues.  Permanent exceptions (KeyError, ValueError,
    TypeError) should cause an immediate halt — they cannot be fixed by
    re-running the gate.
    """

    @pytest.mark.parametrize(
        "gate_cls, exc_name",
        [
            (_PermanentErrorRewriteGate, "ValueError"),
            (_KeyErrorRewriteGate, "KeyError"),
            (_TypeErrorRewriteGate, "TypeError"),
        ],
        ids=["ValueError", "KeyError", "TypeError"],
    )
    def test_permanent_exception_in_rewrite_gate_halts_pipeline(
        self, gate_cls: type[BaseGate], exc_name: str
    ) -> None:
        """Permanent exceptions in retry-mode gates must halt the pipeline."""
        trailing = _PassGate()
        engine = GateEngine([gate_cls(), trailing])
        ok, results = engine.run({})

        assert ok is False, f"{exc_name} in retry gate should fail pipeline"
        assert len(results) >= 1
        error_result = results[-1] if not results[0].get("passed", True) else results[0]
        assert error_result["passed"] is False
        assert len(results) == 1, (
            f"{exc_name} in rewrite gate should halt before the next gate, "
            f"but {len(results)} results were returned (expected 1)"
        )

    def test_transient_connection_error_in_rewrite_gate_continues(self) -> None:
        """Transient ConnectionError in a rewrite gate allows continuation."""
        trailing = _PassGate()
        engine = GateEngine([_TransientConnectionErrorGate(), trailing])
        ok, results = engine.run({})

        assert ok is True  # pipeline completed with stop gate passing
        assert len(results) == 2, "Transient error should not halt pipeline"
        assert results[0]["passed"] is False
        assert results[1]["passed"] is True

    def test_transient_timeout_error_in_rewrite_gate_continues(self) -> None:
        """Transient TimeoutError in a rewrite gate allows continuation."""
        trailing = _PassGate()
        engine = GateEngine([_TransientTimeoutErrorGate(), trailing])
        ok, results = engine.run({})

        assert ok is True  # pipeline completed with stop gate passing
        assert len(results) == 2
        assert results[0]["passed"] is False
        assert results[1]["passed"] is True

    def test_unknown_exception_in_rewrite_gate_re_raised(self) -> None:
        """Unknown exceptions in rewrite gates must be re-raised, not swallowed."""
        engine = GateEngine([_UnknownErrorRewriteGate(), _PassGate()])

        with pytest.raises(RuntimeError, match="unknown error type"):
            engine.run({})


# =========================================================================
# PipelineProgress tests (gates_done / gates_remaining / total_gates)
# =========================================================================


class TestPipelineProgress:
    """PipelineProgress.gates_done / gates_remaining / total_gates."""

    def test_initial_state(self) -> None:
        """At init: gates_done empty, gates_remaining = all, total_gates set."""
        progress = PipelineProgress(project_id="test-1")
        progress.set_gate_names(["G0", "G1", "G2"])
        p = progress.get_progress()
        assert p["gates_done"] == []
        assert p["gates_remaining"] == ["G0", "G1", "G2"]
        assert p["total_gates"] == 3

    def test_after_one_gate(self) -> None:
        """After one gate completes: gates_done=[G0], remaining=[G1, G2]."""
        progress = PipelineProgress(project_id="test-2")
        progress.set_gate_names(["G0", "G1", "G2"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        p = progress.get_progress()
        assert p["gates_done"] == ["G0"]
        assert p["gates_remaining"] == ["G1", "G2"]
        assert p["total_gates"] == 3

    def test_after_two_gates(self) -> None:
        """After two gates complete: gates_done=[G0, G1], remaining=[G2]."""
        progress = PipelineProgress(project_id="test-3")
        progress.set_gate_names(["G0", "G1", "G2"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        progress.on_gate_start("G1")
        progress.on_gate_end("G1", False, 0.5)
        p = progress.get_progress()
        assert p["gates_done"] == ["G0", "G1"]
        assert p["gates_remaining"] == ["G2"]
        assert p["total_gates"] == 3

    def test_all_gates_complete(self) -> None:
        """All gates complete: gates_done all, gates_remaining empty."""
        progress = PipelineProgress(project_id="test-4")
        progress.set_gate_names(["G0", "G1", "G2"])
        for g in ["G0", "G1", "G2"]:
            progress.on_gate_start(g)
            progress.on_gate_end(g, True, 1.0)
        p = progress.get_progress()
        assert p["gates_done"] == ["G0", "G1", "G2"]
        assert p["gates_remaining"] == []
        assert p["total_gates"] == 3

    def test_retry_does_not_duplicate_gate(self) -> None:
        """Retry calls on_gate_end multiple times for same gate — only one entry."""
        progress = PipelineProgress(project_id="test-5")
        progress.set_gate_names(["G0", "G1"])
        # First attempt — fails
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", False, 1.0)
        # Retry — mark end of failed attempt, then start again
        progress.on_gate_end("G0", False, 0.0)
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 2.0)
        p = progress.get_progress()
        assert p["gates_done"] == ["G0"], "retried gate should appear only once"
        assert p["gates_remaining"] == ["G1"]
        assert p["total_gates"] == 2

    def test_set_gate_names_sets_total_gates(self) -> None:
        """set_gate_names should set total_gates."""
        progress = PipelineProgress()
        assert progress.total_gates == 0
        progress.set_gate_names(["pre-gate", "CW", "G0", "G1", "G2", "G3", "G4", "G5"])
        assert progress.total_gates == 8

    def test_default_total_gates_zero(self) -> None:
        """Without calling set_gate_names, total_gates is 0."""
        progress = PipelineProgress(project_id="test-6")
        p = progress.get_progress()
        assert p["total_gates"] == 0
        assert p["gates_done"] == []
        assert p["gates_remaining"] == []


class TestTracebackLogging:
    """All exception types must log full tracebacks, not just str(exc)."""

    def test_permanent_error_logs_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Permanent exceptions must include traceback in the log."""
        engine = GateEngine([_PermanentErrorRewriteGate()])
        with caplog.at_level(logging.ERROR, logger="automedia.pipelines.gate_engine"):
            engine.run({})

        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR
        ]
        assert len(error_records) >= 1, "Expected at least one ERROR log record"
        combined = "\n".join(r.getMessage() for r in error_records)
        assert "ValueError" in combined or "permanent error" in combined

    def test_transient_error_logs_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Transient exceptions must include traceback in the log."""
        engine = GateEngine([_TransientConnectionErrorGate()])
        with caplog.at_level(logging.ERROR, logger="automedia.pipelines.gate_engine"):
            engine.run({})

        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR
        ]
        assert len(error_records) >= 1
        combined = "\n".join(r.getMessage() for r in error_records)
        assert "ConnectionError" in combined or "transient" in combined
