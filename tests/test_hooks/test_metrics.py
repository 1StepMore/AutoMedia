"""Tests for MetricsHook — records per-gate execution metrics to production_metrics.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from automedia.hooks.metrics import METRICS_FILENAME, MetricsHook, _metrics_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_metrics(project_dir: Path) -> dict[str, Any]:
    """Read and return the parsed production_metrics.json from *project_dir*."""
    return json.loads((project_dir / METRICS_FILENAME).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# _metrics_path utility
# ---------------------------------------------------------------------------


class TestMetricsPath:
    """Tests for the module-level _metrics_path helper."""

    def test_returns_path_under_project_dir(self) -> None:
        """_metrics_path joins project_dir with METRICS_FILENAME."""
        result = _metrics_path("/some/project")
        assert result == "/some/project/production_metrics.json"

    def test_uses_metrics_filename_constant(self) -> None:
        """_metrics_path uses the module-level METRICS_FILENAME."""
        assert METRICS_FILENAME == "production_metrics.json"


# ---------------------------------------------------------------------------
# MetricsHook — before_gate
# ---------------------------------------------------------------------------


class TestMetricsHookBeforeGate:
    """before_gate records start time and captures project metadata."""

    def test_records_start_time(self, tmp_path: Path) -> None:
        """Calling before_gate stores a monotonic timestamp for the gate."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("my_gate", ctx)
        assert "my_gate" in hook._start_times

    def test_captures_project_dir_from_context(self, tmp_path: Path) -> None:
        """project_dir is captured from context on first call."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        assert hook._project_dir == str(tmp_path)

    def test_captures_project_id_from_context(self, tmp_path: Path) -> None:
        """project_id is captured from context on first call."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "proj-42"}
        hook.before_gate("g", ctx)
        assert hook._project_id == "proj-42"

    def test_first_call_wins_for_project_metadata(self, tmp_path: Path) -> None:
        """Subsequent before_gate calls do not overwrite project_dir/project_id."""
        hook = MetricsHook()
        hook.before_gate("g1", {"project_dir": "/first", "project_id": "id1"})
        hook.before_gate("g2", {"project_dir": "/second", "project_id": "id2"})
        assert hook._project_dir == "/first"
        assert hook._project_id == "id1"

    def test_context_missing_keys_does_not_raise(self) -> None:
        """before_gate tolerates context without project_dir/project_id."""
        hook = MetricsHook()
        hook.before_gate("g", {})
        assert hook._project_dir is None
        assert hook._project_id is None


# ---------------------------------------------------------------------------
# MetricsHook — after_gate (passed)
# ---------------------------------------------------------------------------


class TestMetricsHookAfterGatePassed:
    """after_gate with a passing result writes metrics with status='passed'."""

    def test_writes_production_metrics_json(self, tmp_path: Path) -> None:
        """A successful gate produces production_metrics.json in project_dir."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("lint", ctx)
        hook.after_gate("lint", ctx, {"passed": True})

        data = _read_metrics(tmp_path)
        assert len(data["gates"]) == 1
        assert data["gates"][0]["gate"] == "lint"
        assert data["gates"][0]["status"] == "passed"

    def test_records_duration(self, tmp_path: Path) -> None:
        """duration_s is a non-negative float recorded for the gate."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": True})

        data = _read_metrics(tmp_path)
        duration = data["gates"][0]["duration_s"]
        assert isinstance(duration, float)
        assert duration >= 0.0

    def test_error_field_is_none_for_passing_gate(self, tmp_path: Path) -> None:
        """A passing gate has error=None in its metrics entry."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": True})

        data = _read_metrics(tmp_path)
        assert data["gates"][0]["error"] is None

    def test_payload_contains_project_id(self, tmp_path: Path) -> None:
        """The top-level payload includes project_id."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "proj-99"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": True})

        data = _read_metrics(tmp_path)
        assert data["project_id"] == "proj-99"

    def test_payload_contains_generated_at(self, tmp_path: Path) -> None:
        """The top-level payload includes an ISO-format generated_at timestamp."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": True})

        data = _read_metrics(tmp_path)
        assert "generated_at" in data
        assert "T" in data["generated_at"]  # ISO 8601 contains 'T'


# ---------------------------------------------------------------------------
# MetricsHook — after_gate (failed)
# ---------------------------------------------------------------------------


class TestMetricsHookAfterGateFailed:
    """after_gate with a failed result records status='failed'."""

    def test_records_failed_status(self, tmp_path: Path) -> None:
        """A gate with passed=False is recorded as status='failed'."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("brand_check", ctx)
        hook.after_gate("brand_check", ctx, {"passed": False})

        data = _read_metrics(tmp_path)
        assert data["gates"][0]["status"] == "failed"

    def test_records_error_from_result(self, tmp_path: Path) -> None:
        """When result contains an 'error' key, it is captured in metrics."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": False, "error": "CTA missing"})

        data = _read_metrics(tmp_path)
        assert data["gates"][0]["error"] == "CTA missing"

    def test_error_is_none_when_result_has_no_error_key(self, tmp_path: Path) -> None:
        """When result lacks 'error', the metrics entry has error=None."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": False})

        data = _read_metrics(tmp_path)
        assert data["gates"][0]["error"] is None


# ---------------------------------------------------------------------------
# MetricsHook — on_gate_failed
# ---------------------------------------------------------------------------


class TestMetricsHookOnGateFailed:
    """on_gate_failed records error status with exception string."""

    def test_records_error_status(self, tmp_path: Path) -> None:
        """A gate that raises is recorded as status='error'."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("tts", ctx)
        hook.on_gate_failed("tts", ctx, RuntimeError("service down"))

        data = _read_metrics(tmp_path)
        assert data["gates"][0]["status"] == "error"

    def test_records_exception_string(self, tmp_path: Path) -> None:
        """The exception is converted to string and stored in 'error'."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("tts", ctx)
        hook.on_gate_failed("tts", ctx, ConnectionError("timeout after 30s"))

        data = _read_metrics(tmp_path)
        assert "timeout after 30s" in data["gates"][0]["error"]

    def test_records_duration(self, tmp_path: Path) -> None:
        """duration_s is recorded even for errored gates."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.on_gate_failed("g", ctx, ValueError("bad input"))

        data = _read_metrics(tmp_path)
        assert data["gates"][0]["duration_s"] >= 0.0


# ---------------------------------------------------------------------------
# MetricsHook — multiple gates accumulate
# ---------------------------------------------------------------------------


class TestMetricsHookAccumulation:
    """Multiple gate invocations accumulate entries in the metrics file."""

    def test_multiple_gates_appended(self, tmp_path: Path) -> None:
        """Each gate call adds an entry to the gates list."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}

        hook.before_gate("g1", ctx)
        hook.after_gate("g1", ctx, {"passed": True})

        hook.before_gate("g2", ctx)
        hook.after_gate("g2", ctx, {"passed": False, "error": "bad"})

        hook.before_gate("g3", ctx)
        hook.on_gate_failed("g3", ctx, RuntimeError("boom"))

        data = _read_metrics(tmp_path)
        assert len(data["gates"]) == 3
        assert [g["gate"] for g in data["gates"]] == ["g1", "g2", "g3"]
        assert [g["status"] for g in data["gates"]] == ["passed", "failed", "error"]


# ---------------------------------------------------------------------------
# MetricsHook — write failure resilience
# ---------------------------------------------------------------------------


class TestMetricsHookWriteFailure:
    """Write failures are logged and do not raise."""

    def test_oserror_is_logged_not_raised(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """An OSError during write is caught, logged, and not propagated."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)

        with patch("automedia.hooks.metrics.open", side_effect=OSError("disk full")):
            with caplog.at_level(logging.ERROR, logger="automedia.hooks.metrics"):
                # Should not raise
                hook.after_gate("g", ctx, {"passed": True})

        assert "failed to write" in caplog.text

    def test_on_gate_failed_write_error_is_logged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """An OSError during on_gate_failed's write is caught and logged."""
        hook = MetricsHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)

        with patch("automedia.hooks.metrics.open", side_effect=OSError("read-only fs")):
            with caplog.at_level(logging.ERROR, logger="automedia.hooks.metrics"):
                hook.on_gate_failed("g", ctx, ValueError("oops"))

        assert "failed to write" in caplog.text


# ---------------------------------------------------------------------------
# MetricsHook — missing project_dir
# ---------------------------------------------------------------------------


class TestMetricsHookMissingProjectDir:
    """When project_dir is not set, _write_metrics skips with a warning."""

    def test_write_skipped_when_project_dir_is_none(self, caplog: pytest.LogCaptureFixture) -> None:
        """No file is written and a warning is logged when project_dir is missing."""
        hook = MetricsHook()
        hook.before_gate("g", {})  # no project_dir in context

        with caplog.at_level(logging.WARNING, logger="automedia.hooks.metrics"):
            hook.after_gate("g", {}, {"passed": True})

        assert "project_dir not set" in caplog.text
        # No metrics were appended because _write_metrics returns early
        # but the gate entry IS appended — only the write is skipped.
        assert len(hook._gates) == 1

    def test_no_file_created_when_project_dir_missing(self, tmp_path: Path) -> None:
        """production_metrics.json is not created when project_dir is None."""
        hook = MetricsHook()
        hook.before_gate("g", {})
        hook.after_gate("g", {}, {"passed": True})

        metrics_file = tmp_path / METRICS_FILENAME
        assert not metrics_file.exists()


# ---------------------------------------------------------------------------
# MetricsHook — protocol conformance
# ---------------------------------------------------------------------------


class TestMetricsHookProtocol:
    """MetricsHook satisfies the GateHook protocol."""

    def test_isinstance_gate_hook(self) -> None:
        """MetricsHook is an instance of GateHook via structural subtyping."""
        from automedia.hooks.protocol import GateHook

        assert isinstance(MetricsHook(), GateHook)

    def test_isinstance_gate_observer(self) -> None:
        """MetricsHook inherits from GateObserver."""
        from automedia.hooks.protocol import GateObserver

        assert isinstance(MetricsHook(), GateObserver)
