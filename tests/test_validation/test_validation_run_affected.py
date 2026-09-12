"""Tests for the CI validation runner's whole-library persistence (gap R-09).

``scripts/validation_run_affected.py --all`` is the nightly/whole-library
path.  Before gap R-09 it ran every scenario with ``run_root=None`` and
persisted nothing; now it writes ONE immutable suite record under
``--runs-root``.  These tests drive ``main()`` with a synthetic library
(synthetic fixtures only, Red Line 4) and assert the record exists and is
exclusive-create.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.validation_run_affected import main

STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)

_GREEN_SCENARIO = """\
name: runner-green
description: A passing synthetic scenario for the runner persistence test.
intent: Prove the --all path persists one suite record.
user_level: L0
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


@pytest.fixture()
def scenarios_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    library = tmp_path / "scenarios"
    library.mkdir()
    shutil.copy2(STANDARDS_FIXTURE, library / "STANDARDS.md")
    (library / "green.yaml").write_text(_GREEN_SCENARIO, encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(library))
    return library


def test_all_persists_one_suite_record(
    scenarios_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs_root = tmp_path / "runs"
    code = main(["--all", "--runs-root", str(runs_root)])
    assert code == 0
    run_names = [entry.name for entry in runs_root.iterdir() if entry.is_dir()]
    assert len(run_names) == 1
    record = json.loads((runs_root / run_names[0] / "scenarios.json").read_text(encoding="utf-8"))
    assert [scenario["scenario"] for scenario in record["scenarios"]] == ["runner-green"]
    assert (runs_root / "latest.txt").is_file()
    assert "suite record:" in capsys.readouterr().out


def test_affected_subset_persists_nothing(
    scenarios_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The subset path keeps the evidence-free contract (run_root=None)."""
    runs_root = tmp_path / "runs"
    code = main(["--runs-root", str(runs_root), "green.yaml"])
    assert code == 0
    capsys.readouterr()
    assert not runs_root.exists()
