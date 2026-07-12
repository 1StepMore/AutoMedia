"""Tests for GateEngine retry logic on transient exceptions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from structlog.testing import capture_logs

from automedia.pipelines.gate_engine import (
    GateEngine,
    PipelineProgress,
    _TRANSIENT_EXCEPTIONS,
)


class _FakeGate:
    """Lightweight gate stub that bypasses BaseGate's auto-registration."""

    def __init__(
        self,
        name: str,
        mode: str,
        execute_fn: Any,
    ) -> None:
        self._name = name
        self._mode = mode
        self._execute_fn = execute_fn

    @property
    def gate_name(self) -> str:
        return self._name

    @property
    def failure_mode(self) -> str:
        return self._mode

    def execute(self, ctx: dict[str, Any]) -> dict[str, Any]:
        return self._execute_fn(ctx)


# ---------------------------------------------------------------------------
# (a) Flaky gate fails 2 times transient, succeeds on 3rd
# ---------------------------------------------------------------------------


def test_retry_succeeds_after_transient_failures() -> None:
    call_count = {"n": 0}

    def _flaky_execute(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ConnectionError("transient failure")
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _flaky_execute)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is True
    assert len(results) == 1
    assert results[0]["passed"] is True
    assert results[0].get("retry_count") == 2
    assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# (b) Flaky gate always fails transient — exhausts retries
# ---------------------------------------------------------------------------


def test_retry_exhausted_on_persistent_transient() -> None:
    call_count = {"n": 0}

    def _always_fail(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise TimeoutError("always times out")

    gate = _FakeGate("G0", "retry", _always_fail)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert results[0]["retry_count"] == 3
    assert results[0]["retry_delay_s"] == 0.01
    assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# (c) Permanent error — no retry, immediate failure
# ---------------------------------------------------------------------------


def test_permanent_error_no_retry() -> None:
    call_count = {"n": 0}

    def _key_error(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise KeyError("missing key")

    gate = _FakeGate("G0", "retry", _key_error)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert "retry_count" not in results[0]
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# (d) failure_mode="stop" with transient error — no retry
# ---------------------------------------------------------------------------


def test_stop_mode_no_retry_on_transient() -> None:
    call_count = {"n": 0}

    def _conn_error(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise ConnectionError("connection lost")

    gate = _FakeGate("G0", "stop", _conn_error)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert "retry_count" not in results[0]
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# (e) Log output contains retry attempt messages
# ---------------------------------------------------------------------------


def test_retry_logging_contains_attempt_messages() -> None:
    call_count = {"n": 0}

    def _flaky_execute(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ConnectionError("transient")
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _flaky_execute)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    with capture_logs() as cap:
        engine.run({"topic": "test"})

    retry_events = [e for e in cap if e.get("log_level") == "info" and "retry" in e.get("event", "")]
    assert len(retry_events) == 2

    first = retry_events[0]
    assert first["attempt"] == 1
    assert first["max_retries"] == 3
    assert first["gate_name"] == "G0"


# ---------------------------------------------------------------------------
# Progress events emitted for each retry attempt
# ---------------------------------------------------------------------------


def test_retry_emits_progress_events() -> None:
    call_count = {"n": 0}

    def _flaky_execute(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ConnectionError("transient")
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _flaky_execute)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    progress = PipelineProgress(project_id="test-proj")

    engine.run({"topic": "test"}, progress=progress)

    events = progress.get_progress()["events"]
    running_events = [e for e in events if e["status"] == "running"]
    failed_events = [e for e in events if e["status"] == "failed"]
    passed_events = [e for e in events if e["status"] == "passed"]

    assert len(running_events) == 3
    assert len(failed_events) == 2
    assert len(passed_events) == 1


# ---------------------------------------------------------------------------
# Unknown exception with retry mode — no retry, re-raises
# ---------------------------------------------------------------------------


def test_unknown_exception_no_retry_reraises() -> None:
    call_count = {"n": 0}

    def _runtime_error(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise RuntimeError("unexpected")

    gate = _FakeGate("G0", "retry", _runtime_error)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    with pytest.raises(RuntimeError, match="unexpected"):
        engine.run({"topic": "test"})

    assert call_count["n"] == 1
