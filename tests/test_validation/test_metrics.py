"""AX metrics per suite run (gap Tr-02).

Six formulas with explicit ``null`` semantics (never ``0`` for a missing
denominator): task_completion_rate, tool_call_accuracy, recovery_success_rate,
doc_freshness, token_usage, error_recovery_time_s.  An all-unconfigured run
writes ``task_completion_rate: null`` and ``unproven: true``; a suite run
writes ``metrics.json`` beside ``scenarios.json`` and ``validate report``
renders the six keys.

All fixtures are synthetic (Red Line 4).
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from automedia.validation.engine import run_validation_suite_async
from automedia.validation.metrics import METRIC_KEYS, build_metrics
from automedia.validation.report import render_report_json, render_report_text

_STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)


def _record(scenarios: list[dict], **overrides: object) -> dict:
    return {
        "trace_id": "t",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "scenarios": scenarios,
        **overrides,
    }


def _unconfigured(name: str = "u") -> dict:
    return {
        "scenario": name,
        "status": "unconfigured",
        "reason": "missing env: X",
        "confidence": "real",
        "steps": [],
    }


def _passed(name: str = "p", target: str = "health_check") -> dict:
    return {
        "scenario": name,
        "status": "passed",
        "confidence": "real",
        "steps": [
            {
                "step_index": 1,
                "surface": "tool",
                "target": target,
                "passed": True,
                "status": "passed",
                "duration": 0.5,
            }
        ],
    }


class TestFormulas:
    def test_six_keys_always_present(self) -> None:
        metrics = build_metrics(_record([]), doc_freshness_value=1)
        assert set(METRIC_KEYS) <= set(metrics)

    def test_all_unconfigured_writes_null_and_unproven(self) -> None:
        metrics = build_metrics(
            _record([_unconfigured("a"), _unconfigured("b")]), doc_freshness_value=0
        )
        assert metrics["task_completion_rate"] is None
        assert metrics["unproven"] is True
        assert metrics["tool_call_accuracy"] is None
        assert metrics["recovery_success_rate"] is None
        assert metrics["error_recovery_time_s"] is None
        assert metrics["token_usage"] is None
        assert "no runnable real runs" in metrics["reasons"]["task_completion_rate"]

    def test_passing_real_run_completes(self) -> None:
        metrics = build_metrics(_record([_passed()]), doc_freshness_value=1)
        assert metrics["task_completion_rate"] == 1.0
        assert metrics["tool_call_accuracy"] == 1.0
        assert metrics["unproven"] is False
        assert metrics["runs"]["runnable_real"] == 1
        assert metrics["runs"]["passed_real"] == 1

    def test_mock_only_run_is_excluded_and_unproven(self) -> None:
        record = _passed()
        record["confidence"] = "mock"
        metrics = build_metrics(_record([record]), doc_freshness_value=1)
        assert metrics["task_completion_rate"] is None
        assert metrics["unproven"] is True
        assert metrics["runs"]["runnable_real"] == 0

    def test_failed_step_lowers_tool_call_accuracy(self) -> None:
        record = _passed()
        record["status"] = "failed"
        record["steps"][0]["passed"] = False
        record["steps"][0]["status"] = "failed"
        metrics = build_metrics(_record([record]), doc_freshness_value=1)
        assert metrics["tool_call_accuracy"] == 0.0
        assert metrics["task_completion_rate"] == 0.0

    def test_recovery_rate_and_time(self) -> None:
        record = {
            "scenario": "r",
            "status": "recovered",
            "confidence": "real",
            "steps": [
                {
                    "step_index": 1,
                    "passed": True,
                    "status": "recovered",
                    "recovery": [
                        {"passed": True, "status": "passed", "duration": 1.5},
                        {"passed": True, "status": "passed", "duration": 0.5},
                    ],
                }
            ],
        }
        metrics = build_metrics(_record([record]), doc_freshness_value=1)
        assert metrics["recovery_success_rate"] == 1.0
        assert metrics["error_recovery_time_s"] == 2.0


class TestSuiteWritesMetrics:
    @pytest.fixture()
    def scenarios_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        library = tmp_path / "scenarios"
        library.mkdir()
        shutil.copy2(_STANDARDS_FIXTURE, library / "STANDARDS.md")
        gated = (
            "name: metrics-gated\n"
            "description: Gated synthetic scenario.\n"
            "intent: Prove the metrics writer on an unconfigured run.\n"
            "user_level: L0\n"
            "category: baseline\n"
            "requires_env: [AUTOMEDIA_LLM_API_KEY]\n"
            "steps:\n"
            "  - name: echo\n"
            "    kind: cli\n"
            "    check: echo ok\n"
            "    standard: founder-expectations.F02\n"
            "    command: echo ok\n"
            "    expect:\n"
            "      exit_code: 0\n"
        )
        (library / "gated.yaml").write_text(gated, encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(library))
        monkeypatch.delenv("AUTOMEDIA_LLM_API_KEY", raising=False)
        monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)
        return library

    def test_suite_run_writes_metrics_json_and_embeds_it(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        runs = tmp_path / "runs"
        record = asyncio.run(run_validation_suite_async(None, scenarios_dir, runs_root=runs))
        assert record["metrics"]["unproven"] is True
        assert record["metrics"]["task_completion_rate"] is None
        run_name = next(p.name for p in runs.iterdir() if p.is_dir())
        written = json.loads((runs / run_name / "metrics.json").read_text(encoding="utf-8"))
        assert written["unproven"] is True
        assert set(METRIC_KEYS) <= set(written)

    def test_report_renders_six_keys(self) -> None:
        metrics = build_metrics(_record([_passed()]), doc_freshness_value=1)
        text = render_report_text(_record([_passed()], metrics=metrics))
        assert "## Metrics" in text
        for key in METRIC_KEYS:
            assert key in text
        payload = render_report_json(_record([_passed()], metrics=metrics))
        assert set(METRIC_KEYS) <= set(payload["metrics"])
