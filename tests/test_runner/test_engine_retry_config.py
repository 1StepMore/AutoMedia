"""The retry knobs from defaults.yaml reach GateEngine (issue #268)."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from automedia.pipelines.runner import _engine_retry_settings, _setup_and_run_engine

_DEFAULTS = {
    "max_retries": 3,
    "retry_delay": 1.0,
    "max_quality_retries": 3,
    "max_regenerations": 2,
}


def _project(tmp_path: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(project_id="retry-config", project_dir=str(tmp_path))


class TestEngineRetrySettings:
    def test_reads_configured_values(self) -> None:
        settings = _engine_retry_settings(
            {
                "gate_engine": {
                    "max_retries": 2,
                    "retry_delay": 0.25,
                    "max_quality_retries": 1,
                    "max_regenerations": 0,
                }
            }
        )
        assert settings == {
            "max_retries": 2,
            "retry_delay": 0.25,
            "max_quality_retries": 1,
            "max_regenerations": 0,
        }

    def test_defaults_when_missing(self) -> None:
        assert _engine_retry_settings(None) == _DEFAULTS
        assert _engine_retry_settings({}) == _DEFAULTS
        assert _engine_retry_settings({"gate_engine": None}) == _DEFAULTS

    def test_invalid_and_out_of_range_values_fall_back(self) -> None:
        settings = _engine_retry_settings(
            {
                "gate_engine": {
                    "max_retries": 0,
                    "retry_delay": -1,
                    "max_quality_retries": "nope",
                    "max_regenerations": -2,
                }
            }
        )
        assert settings == _DEFAULTS


def test_setup_and_run_engine_forwards_configured_retry_budget(tmp_path: Path) -> None:
    engine = MagicMock()
    engine.run.return_value = (True, [{"passed": True, "gate": "T"}])
    engine.hitl_awaiting = False

    with patch("automedia.pipelines.gate_engine.GateEngine", return_value=engine) as engine_cls:
        _setup_and_run_engine(
            [],
            None,
            False,
            _project(tmp_path),
            {},
            None,
            True,
            {
                "gate_engine": {
                    "max_retries": 2,
                    "retry_delay": 0.0,
                    "max_quality_retries": 1,
                    "max_regenerations": 0,
                }
            },
        )

    kwargs = engine_cls.call_args.kwargs
    assert kwargs["max_retries"] == 2
    assert kwargs["retry_delay"] == 0.0
    assert kwargs["max_quality_retries"] == 1
    assert kwargs["max_regenerations"] == 0


class _TransientGate:
    gate_name = "T"
    failure_mode = "retry"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        raise ConnectionError("transient")


def test_configured_max_retries_controls_attempts(tmp_path: Path) -> None:
    gate = _TransientGate()
    _setup_and_run_engine(
        [gate],
        None,
        False,
        _project(tmp_path),
        {},
        None,
        True,
        {"gate_engine": {"max_retries": 2, "retry_delay": 0.0}},
    )
    assert gate.calls == 2
