"""Suite-run persistence immutability (gap R-09).

The whole-library suite writes ONE exclusive-create record.  A second write
to the same run stamp is refused by the filesystem (``O_CREAT|O_EXCL``),
never overwritten.  All fixtures are synthetic (Red Line 4).
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from automedia.validation.engine import run_validation_suite_async
from automedia.validation.persist import PersistError, list_runs, persist_run

STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)

_GREEN_SCENARIO = """\
name: persistence-green
description: A passing synthetic scenario for suite persistence.
intent: Prove the suite record is exclusive-create and immutable.
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


def test_suite_persists_one_immutable_record(scenarios_dir: Path, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    record = asyncio.run(run_validation_suite_async(None, scenarios_dir, runs_root=runs_root))
    assert [scenario["status"] for scenario in record["scenarios"]] == ["passed"]
    (run_name,) = list_runs(runs_root)
    stored = json.loads((runs_root / run_name / "scenarios.json").read_text(encoding="utf-8"))
    assert stored["trace_id"] == record["trace_id"]


def test_second_write_to_the_same_stamp_is_refused(scenarios_dir: Path, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    record = asyncio.run(run_validation_suite_async(None, scenarios_dir, runs_root=runs_root))
    (run_name,) = list_runs(runs_root)
    record_path = runs_root / run_name / "scenarios.json"
    original = record_path.read_text(encoding="utf-8")
    with pytest.raises(PersistError, match="refusing to overwrite"):
        persist_run(runs_root, record, stamp=run_name)
    assert record_path.read_text(encoding="utf-8") == original
