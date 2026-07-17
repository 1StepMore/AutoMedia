"""Tests for GateEngine retry call sites — quality retry loop and tenacity retry.

These tests verify that the retry metadata (attempt_number, retry_level,
strategy_delta) are passed correctly through progress events at each
retry call site in GateEngine.

We use mock gate subclasses and a mock PipelineProgress observer to
verify the exact calls without running real pipelines.

Scenarios
---------
1. Quality retry loop: gate failure_mode='retry', returns passed=False →
   progress.on_gate_end/on_gate_start called with retry_level='quality'
   and incrementing attempt_number
2. Quality retry loop stops after max_quality_retries
3. Quality retry loop passes on nth attempt (eventual success)
4. Tenacity _before_sleep callback calls on_gate_end/on_gate_start with
   retry_level='tenacity' and attempt_number
5. Permanent exception in quality retry: on_gate_end called with retry metadata
6. Transient exception in quality retry: on_gate_end called with retry metadata
7. Unknown exception in quality retry: on_gate_end called with retry metadata
8. Consume_retry_gate after gate completion triggers re-run
9. Consume_skip_gate skips gate without execution
10. Cancel during gate execution stops the pipeline
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from automedia.gates.base import BaseGate
from automedia.pipelines.gate_engine import GateEngine, PipelineProgress

# ---------------------------------------------------------------------------
# Mock gate helpers
# ---------------------------------------------------------------------------

# Use gate names G70+ to avoid collisions with existing test gates (G73-G85)


class _PassGate(BaseGate):
    """Always passes."""

    _gate_name = "G70"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


class _FailRetryGate(BaseGate):
    """Always returns passed=False with failure_mode='retry'."""

    _gate_name = "G71"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "gate": self.gate_name, "error": "quality fail"}


class _FailRetryThenPassGate(BaseGate):
    """Fails for first N calls, then passes.

    Uses a class-level counter so each instance shares state (simulating
    how the engine re-executes the same gate instance).
    """

    _gate_name = "G76"
    _failure_mode = "retry"
    _call_count: int = 0

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        type(self)._call_count = self._call_count + 1
        if self._call_count < 3:
            return {"passed": False, "gate": self.gate_name, "error": "quality fail"}
        return {"passed": True, "gate": self.gate_name}


class _TransientRetryGate(BaseGate):
    """Raises ConnectionError (transient) with failure_mode='retry'."""

    _gate_name = "G72"
    _failure_mode = "retry"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("transient — network issue")


class _PermanentErrorOnRetryGate(BaseGate):
    """Returns passed=False first, then raises ValueError on quality retry."""

    _gate_name = "G77"
    _failure_mode = "retry"
    _call_count: int = 0

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        type(self)._call_count = self._call_count + 1
        if self._call_count == 1:
            return {"passed": False, "gate": self.gate_name, "error": "quality fail"}
        raise ValueError("permanent error on quality retry")


class _TransientErrorOnRetryGate(BaseGate):
    """Returns passed=False first, then raises ConnectionError on quality retry."""

    _gate_name = "G78"
    _failure_mode = "retry"
    _call_count: int = 0

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        type(self)._call_count = self._call_count + 1
        if self._call_count == 1:
            return {"passed": False, "gate": self.gate_name, "error": "quality fail"}
        raise ConnectionError("transient error on quality retry")


class _UnknownErrorOnRetryGate(BaseGate):
    """Returns passed=False first, then raises RuntimeError on quality retry."""

    _gate_name = "G79"
    _failure_mode = "retry"
    _call_count: int = 0

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        type(self)._call_count = self._call_count + 1
        if self._call_count == 1:
            return {"passed": False, "gate": self.gate_name, "error": "quality fail"}
        raise RuntimeError("unknown error on quality retry")


class _SkipDetectGate(BaseGate):
    """Records whether execute was called."""

    _gate_name = "G75"
    _failure_mode = "stop"

    def __init__(self) -> None:
        self.executed = False

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        self.executed = True
        return {"passed": True, "gate": self.gate_name}


class _SecondPassGate(BaseGate):
    """Always passes, distinct gate name for multi-gate tests."""

    _gate_name = "G80"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


# =====================================================================
# Quality retry loop — on_gate_end/on_gate_start calls
# =====================================================================


class TestQualityRetryCallsProgress:
    """Quality retry loop calls progress with retry_level='quality'."""

    def test_quality_retry_sends_retry_metadata(self) -> None:
        """Quality retry calls on_gate_end/on_gate_start with 'quality' level."""
        progress = MagicMock(spec=PipelineProgress)
        # Make is_cancelled return False
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_FailRetryGate()],
            max_quality_retries=2,
            max_regenerations=0,
        )

        ok, _results = engine.run({}, progress=progress)

        assert ok is False  # All quality retries exhausted

        # Check that progress was called with retry metadata
        # on_gate_end should have been called with retry_level='quality' for each failed attempt
        end_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "quality"
        ]
        assert len(end_calls) >= 2, (
            f"Expected at least 2 on_gate_end calls with retry_level='quality', "
            f"got {len(end_calls)}"
        )

        # on_gate_start should have been called with retry_level='quality' for retry starts
        start_calls = [
            call
            for call in progress.on_gate_start.call_args_list
            if call.kwargs.get("retry_level") == "quality"
        ]
        assert len(start_calls) >= 2

    def test_quality_retry_attempt_number_increments(self) -> None:
        """Quality retry attempt_number increments with each retry."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_FailRetryGate()],
            max_quality_retries=3,
            max_regenerations=0,
        )

        engine.run({}, progress=progress)

        # Collect attempt_numbers from on_gate_end calls with retry_level='quality'
        end_attempts = [
            call.kwargs.get("attempt_number")
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "quality"
        ]
        # Should have attempts 1, 2, 3
        assert 1 in end_attempts, f"Expected attempt 1, got {end_attempts}"
        assert 2 in end_attempts, f"Expected attempt 2, got {end_attempts}"
        assert 3 in end_attempts, f"Expected attempt 3, got {end_attempts}"

    def test_quality_retry_eventual_success(self) -> None:
        """Quality retry stops retrying when gate eventually passes."""
        _FailRetryThenPassGate._call_count = 0  # Reset shared counter

        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_FailRetryThenPassGate()],
            max_quality_retries=5,
            max_regenerations=0,
        )

        ok, results = engine.run({}, progress=progress)

        assert ok is True  # Eventually passed
        assert results[-1]["passed"] is True

        # Each quality retry attempt generates 2 on_gate_end calls with
        # retry_level='quality': one prep call (0.0s, before re-execute)
        # and one result call (actual duration). For 2 failed attempts
        # plus 1 passed result, that yields 4 calls (2 prep + 2 result).
        quality_end_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "quality"
        ]
        assert len(quality_end_calls) >= 2  # At least the retry attempts

        # Verify attempt numbers are present
        attempt_numbers = {
            call.kwargs.get("attempt_number")
            for call in quality_end_calls
        }
        assert 1 in attempt_numbers
        assert 2 in attempt_numbers

    def test_quality_retry_exhausted_stops(self) -> None:
        """Quality retry stops after max_quality_retries attempts."""
        _FailRetryThenPassGate._call_count = 0  # Reset

        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_FailRetryThenPassGate()],
            max_quality_retries=1,  # Only 1 retry allowed
            max_regenerations=0,
        )

        ok, results = engine.run({}, progress=progress)

        assert ok is False  # Exhausted retries, gate still failing


# =====================================================================
# Tenacity retry — _before_sleep callback
# =====================================================================


class TestTenacityRetryCallsProgress:
    """Tenacity _before_sleep calls progress with retry_level='tenacity'."""

    def test_tenacity_retry_sends_retry_metadata(self) -> None:
        """Tenacity _before_sleep calls on_gate_end/on_gate_start with 'tenacity'."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_TransientRetryGate()],
            max_retries=2,  # Allow 2 retry attempts
            retry_delay=0.01,  # Fast retry for tests
            max_quality_retries=0,
        )

        engine.run({}, progress=progress)

        # The _before_sleep callback should call on_gate_end and on_gate_start
        # with retry_level='tenacity'
        tenacity_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "tenacity"
        ]
        assert len(tenacity_calls) >= 1, (
            f"Expected at least 1 on_gate_end call with retry_level='tenacity', "
            f"got {len(tenacity_calls)}"
        )

    def test_tenacity_retry_attempt_number_increments(self) -> None:
        """Tenacity retry attempt_number increments with each retry."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_TransientRetryGate()],
            max_retries=2,
            retry_delay=0.01,
            max_quality_retries=0,
        )

        engine.run({}, progress=progress)

        # Check attempt numbers in tenacity on_gate_end calls
        end_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "tenacity"
        ]
        for call in end_calls:
            assert call.kwargs.get("attempt_number", 0) >= 1, (
                f"tenacity retry should have attempt_number >= 1, "
                f"got {call.kwargs.get('attempt_number')}"
            )


# =====================================================================
# Exception handlers in quality retry
# =====================================================================


class TestQualityRetryExceptionHandlers:
    """Exception handlers inside quality retry call on_gate_end with retry metadata.

    These tests use 2-phase gates: first call returns passed=False (entering the
    quality retry loop), subsequent calls raise an exception (testing the exception
    handler inside the quality retry loop).
    """

    def test_permanent_exception_during_quality_retry(self) -> None:
        """Permanent exception during quality retry calls on_gate_end with metadata."""
        _PermanentErrorOnRetryGate._call_count = 0  # Reset

        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_PermanentErrorOnRetryGate()],
            max_quality_retries=2,
            max_regenerations=0,
        )

        engine.run({}, progress=progress)

        # The quality retry loop handles the permanent exception and calls
        # on_gate_end with retry_level='quality'
        quality_end_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "quality"
        ]
        assert len(quality_end_calls) >= 1

    def test_transient_exception_during_quality_retry(self) -> None:
        """Transient exception during quality retry calls on_gate_end with metadata."""
        _TransientErrorOnRetryGate._call_count = 0  # Reset

        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_TransientErrorOnRetryGate()],
            max_retries=0,
            max_quality_retries=2,
            max_regenerations=0,
        )

        engine.run({}, progress=progress)

        # The quality retry loop handles the transient exception and calls
        # on_gate_end with retry_level='quality'
        quality_end_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "quality"
        ]
        assert len(quality_end_calls) >= 1

    def test_unknown_exception_during_quality_retry(self) -> None:
        """Unknown exception during quality retry calls on_gate_end with metadata."""
        _UnknownErrorOnRetryGate._call_count = 0  # Reset

        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_UnknownErrorOnRetryGate()],
            max_quality_retries=2,
            max_regenerations=0,
        )

        with pytest.raises(RuntimeError, match="unknown error on quality retry"):
            engine.run({}, progress=progress)

        # The quality retry loop handles the unknown exception, calls
        # on_gate_end with retry metadata, then re-raises
        quality_end_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.kwargs.get("retry_level") == "quality"
        ]
        assert len(quality_end_calls) >= 1


# =====================================================================
# Retry gate flag — consume_retry_gate triggers re-run
# =====================================================================


class TestRetryGateFlagWithEngine:
    """The retry gate flag in the engine loop causes re-execution."""

    def test_retry_flag_triggers_rerun(self) -> None:
        """When progress.consume_retry_gate returns the current gate, it re-runs."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None

        # consume_retry_gate is called AFTER gate execution. First call
        # returns "G70" (matching the just-completed gate) to trigger retry.
        # Subsequent calls return None (no retry).
        progress.consume_retry_gate.side_effect = ["G70", None, None]

        engine = GateEngine(
            [_PassGate(), _SecondPassGate()],
            max_quality_retries=0,
            max_regenerations=0,
        )

        ok, results = engine.run({}, progress=progress)

        assert ok is True
        # G70 executed twice (initial + retry), G80 executed once
        assert len(results) == 3

    def test_retry_flag_calls_on_gate_end_for_rerun(self) -> None:
        """When gate is re-run via retry flag, on_gate_end is called per execution."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None

        # consume_retry_gate returns "G70" first to trigger retry, then None
        progress.consume_retry_gate.side_effect = ["G70", None, None]

        engine = GateEngine(
            [_PassGate(), _SecondPassGate()],
            max_quality_retries=0,
            max_regenerations=0,
        )

        engine.run({}, progress=progress)

        # G70 should have 2 on_gate_end calls (initial + retry re-run)
        g70_end_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.args[0] == "G70"
        ]
        assert len(g70_end_calls) == 2


# =====================================================================
# Skip gate flag — consume_skip_gate skips the gate
# =====================================================================


class TestSkipGateFlagWithEngine:
    """The skip gate flag in the engine loop causes the gate to be skipped."""

    def test_skip_flag_skips_execution(self) -> None:
        """When consume_skip_gate returns current gate, it's skipped."""
        detect = _SkipDetectGate()
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = "G75"
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [detect, _PassGate()],
            max_quality_retries=0,
        )

        engine.run({}, progress=progress)

        assert detect.executed is False, "Skipped gate should not have executed"

    def test_skip_flag_calls_on_gate_end_with_skipped_detail(self) -> None:
        """When gate is skipped, on_gate_end is called with detail='skipped via MCP'."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        # Only skip the first gate (G70), not the second (G80)
        progress.consume_skip_gate.side_effect = ["G70", None]
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_PassGate(), _SecondPassGate()],
            max_quality_retries=0,
        )

        engine.run({}, progress=progress)

        # G70 should have exactly one on_gate_end call with detail='skipped via MCP'
        skipped_calls = [
            call
            for call in progress.on_gate_end.call_args_list
            if call.args[0] == "G70" and call.kwargs.get("detail") == "skipped via MCP"
        ]
        assert len(skipped_calls) == 1


# =====================================================================
# Cancel flag — stops the pipeline
# =====================================================================


class TestCancelFlagWithEngine:
    """Cancellation stops the pipeline at gate boundaries."""

    def test_cancel_stops_pipeline(self) -> None:
        """When is_cancelled returns True, pipeline stops."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = True  # Cancel immediately
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_PassGate(), _PassGate()],
            max_quality_retries=0,
        )

        ok, results = engine.run({}, progress=progress)

        assert ok is True  # No gates ran, so vacuously true
        assert len(results) == 0  # No gates executed

    def test_cancel_after_first_gate(self) -> None:
        """Cancel after first gate stops before second."""
        progress = MagicMock(spec=PipelineProgress)
        # First gate: not cancelled. Second gate: cancelled.
        progress.is_cancelled.side_effect = [False, True]
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_PassGate(), _PassGate()],
            max_quality_retries=0,
        )

        ok, results = engine.run({}, progress=progress)

        assert len(results) == 1  # Only first gate executed


# =====================================================================
# Pause flag — wait_if_paused blocks between gates
# =====================================================================


class TestPauseFlagWithEngine:
    """Pause support in gate engine loop."""

    def test_pause_between_gates(self) -> None:
        """Engine calls wait_if_paused between gates."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = True
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_PassGate(), _PassGate()],
            max_quality_retries=0,
        )

        engine.run({}, progress=progress)

        # wait_if_paused should have been called (once per gate)
        assert progress.wait_if_paused.call_count >= 2

    def test_pause_with_cancel_during_wait(self) -> None:
        """When wait_if_paused returns False, pipeline stops."""
        progress = MagicMock(spec=PipelineProgress)
        progress.is_cancelled.return_value = False
        progress.wait_if_paused.return_value = False  # Cancelled during pause
        progress.consume_skip_gate.return_value = None
        progress.consume_retry_gate.return_value = None

        engine = GateEngine(
            [_PassGate(), _PassGate()],
            max_quality_retries=0,
        )

        ok, results = engine.run({}, progress=progress)

        assert len(results) == 0  # Cancelled before any gate


# =====================================================================
# No progress — engine works without progress tracker
# =====================================================================


class TestEngineWithoutProgress:
    """GateEngine works without a PipelineProgress instance."""

    def test_engine_works_without_progress(self) -> None:
        """Engine.run() with progress=None still works."""
        engine = GateEngine([_PassGate(), _PassGate()])
        ok, results = engine.run({}, progress=None)
        assert ok is True
        assert len(results) == 2

    def test_quality_retry_works_without_progress(self) -> None:
        """Quality retry works even without progress tracker."""
        engine = GateEngine(
            [_FailRetryGate(), _PassGate()],
            max_quality_retries=2,
            max_regenerations=0,
        )
        ok, results = engine.run({}, progress=None)
        assert ok is True  # PassGate after the failing retry gate
        assert len(results) == 2
