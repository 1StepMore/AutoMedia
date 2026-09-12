"""Baseline immutability (gap R-10).

The committed baseline was overwritten in place by the ``json.dump(r,
open(..., 'w'))`` regeneration one-liner, destroying the prior RED baseline.
This module pins the fix: regeneration goes through
``persist_baseline`` (``O_CREAT|O_EXCL``) and refuses to overwrite an existing
baseline; the committed README records the lost-RED event.  All run fixtures
are synthetic (Red Line 4) — no network, no LLM, no credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automedia.validation.baseline import DEFAULT_BASELINE_PATH, regenerate_baseline
from automedia.validation.persist import PersistError, persist_baseline

_STANDARD = "founder-expectations.F01"

_GREEN_SCENARIO = f"""\
name: baseline-green
description: A deterministic passing scenario for baseline regeneration.
intent: Prove regeneration writes through the exclusive-create path.
user_level: L0
category: baseline
requires_env: []
steps:
  - name: echo prints ok
    kind: cli
    check: echo prints the word ok
    standard: {_STANDARD}
    command: echo ok
    timeout_seconds: 30
    expect:
      exit_code: 0
      stdout_has: ["ok"]
"""


def _library(tmp_path: Path) -> Path:
    """A one-scenario synthetic library that loads through the real loader."""
    lib = tmp_path / "scenarios"
    lib.mkdir()
    (lib / "green.yaml").write_text(_GREEN_SCENARIO, encoding="utf-8")
    return lib


class TestPersistBaseline:
    def test_writes_new_file(self, tmp_path: Path) -> None:
        target = tmp_path / "baseline.json"
        assert persist_baseline(target, {"baseline": True}) == target
        assert json.loads(target.read_text(encoding="utf-8")) == {"baseline": True}

    def test_refuses_overwrite_and_keeps_original(self, tmp_path: Path) -> None:
        target = tmp_path / "baseline.json"
        persist_baseline(target, {"verdict": "first"})
        with pytest.raises(PersistError, match="refusing to overwrite"):
            persist_baseline(target, {"verdict": "second"})
        assert json.loads(target.read_text(encoding="utf-8")) == {"verdict": "first"}

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "baseline.json"
        assert persist_baseline(target, {"ok": True}) == target
        assert target.is_file()


class TestRegenerateBaseline:
    def test_regeneration_writes_a_new_baseline(self, tmp_path: Path) -> None:
        target = tmp_path / "baseline.json"
        written = regenerate_baseline(None, baseline_path=target, scenarios_dir=_library(tmp_path))
        assert written == target
        record = json.loads(target.read_text(encoding="utf-8"))
        assert record["baseline"] is True
        assert record["note"] == "full-suite baseline"
        assert [scenario["status"] for scenario in record["scenarios"]] == ["passed"]

    def test_second_regeneration_refuses_overwrite(self, tmp_path: Path) -> None:
        target = tmp_path / "baseline.json"
        lib = _library(tmp_path)
        regenerate_baseline(None, baseline_path=target, scenarios_dir=lib)
        original = target.read_text(encoding="utf-8")
        with pytest.raises(PersistError, match="refusing to overwrite"):
            regenerate_baseline(None, baseline_path=target, scenarios_dir=lib)
        assert target.read_text(encoding="utf-8") == original


class TestLostRedDocumented:
    def test_committed_baseline_path_is_a_file(self) -> None:
        assert Path(DEFAULT_BASELINE_PATH).is_file()

    def test_readme_records_the_lost_red_baseline(self) -> None:
        readme = Path(DEFAULT_BASELINE_PATH).parent / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert "Lost RED baseline" in text
        assert "refuses to overwrite" in text
