"""Mock-aware run records (gap T-22).

Every run record carries ``confidence: real|mock``: ``mock`` marks a run
executed against the deterministic fake LLM (plumbing only — never
capability proof), ``real`` marks the shipped provider.  Coverage consumes
this field to keep mock-only surfaces out of ``covered``.

All fixtures are synthetic (Red Line 4).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from automedia.validation.engine import (
    make_adapters,
    run_validation_scenario_async,
    run_validation_suite_async,
)
from automedia.validation.schema import Expect, Scenario, Step

_FAKE = "AUTOMEDIA_FAKE_LLM"

_GREEN_SCENARIO = """\
name: confidence-green
description: A passing synthetic scenario for confidence recording.
intent: Prove the run record carries real|mock confidence.
category: baseline
requires_env: []
steps:
  - name: echo prints ok
    kind: cli
    check: echo prints the word ok
    standard: founder-expectations.F02
    command: echo ok
    timeout_seconds: 30
    expect:
      exit_code: 0
      stdout_has: ["ok"]
"""

_STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)


def _scenario() -> Scenario:
    return Scenario(
        name="confidence-fixture",
        description="Synthetic passing scenario.",
        intent="Prove confidence recording.",
        steps=[
            Step(
                name="echo ok",
                kind="cli",
                check="echo prints ok",
                standard="founder-expectations.F02",
                command="echo ok",
                expect=Expect(exit_code=0, stdout_has=["ok"]),
            )
        ],
    )


class TestScenarioConfidence:
    def test_real_run_is_real(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_FAKE, raising=False)
        record = asyncio.run(
            run_validation_scenario_async(_scenario(), make_adapters(None))
        )
        assert record["confidence"] == "real"

    def test_fake_run_is_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_FAKE, "1")
        record = asyncio.run(
            run_validation_scenario_async(_scenario(), make_adapters(None))
        )
        assert record["status"] == "passed"
        assert record["confidence"] == "mock"


class TestSuiteConfidence:
    @pytest.fixture()
    def scenarios_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        library = tmp_path / "scenarios"
        library.mkdir()
        shutil.copy2(_STANDARDS_FIXTURE, library / "STANDARDS.md")
        (library / "green.yaml").write_text(_GREEN_SCENARIO, encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(library))
        return library

    def test_suite_records_confidence_on_record_and_scenarios(
        self, scenarios_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        record = asyncio.run(
            run_validation_suite_async(None, scenarios_dir, runs_root=tmp_path / "runs")
        )
        assert record["confidence"] == "mock"
        assert [r["confidence"] for r in record["scenarios"]] == ["mock"]

    def test_real_suite_records_real(
        self, scenarios_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(_FAKE, raising=False)
        record = asyncio.run(
            run_validation_suite_async(None, scenarios_dir, runs_root=tmp_path / "runs")
        )
        assert record["confidence"] == "real"
        assert [r["confidence"] for r in record["scenarios"]] == ["real"]
