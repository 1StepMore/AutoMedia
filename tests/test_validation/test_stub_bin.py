"""Non-LLM stub seam + ``requires_real_adapter`` (gap T-21).

* ``AUTOMEDIA_VALIDATION_STUB_BIN`` names the committed fixture directory of
  stand-in external tools; the harness prepends it to ``PATH`` so a mode
  journey can run on a machine with no FFmpeg/Whisper/edge-tts installed.
* ``requires_real_adapter: true`` flags a scenario whose only honest proof
  needs real platform credentials; the suite can exclude it from the CI
  denominator instead of counting it as an unconfigured loss.

All synthetic fixtures use the repo's synth STANDARDS.md (Red Line 4).
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import cast

import pytest

from automedia.validation.engine import run_validation_suite_async
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario, SchemaError
from automedia.validation.stub_bin import (
    STUB_BIN_ENV,
    apply_stub_bin_to_path,
)

STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)

STUB_BIN = Path(__file__).resolve().parents[2] / "scenarios" / "stubs" / "bin"
STUB_NAMES = ("ffmpeg", "ffprobe", "whisper", "edge-tts", "tts", "bun", "hyperframes")

_CLI_SCENARIO = """\
name: {name}
description: A synthetic fixture scenario.
intent: Prove the stub seam / real-adapter exclusion contract.
user_level: L0
category: baseline
requires_env: []
{extra}steps:
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


def _scenario_names(record: dict[str, object]) -> list[str]:
    entries = cast(list[dict[str, object]], record["scenarios"])
    return [str(entry["scenario"]) for entry in entries]


def _scenario() -> Scenario:
    return Scenario.from_dict(
        {
            "name": "adapter-fixture",
            "description": "Synthetic real-adapter fixture.",
            "intent": "Exercise requires_real_adapter parsing.",
            "user_level": "L0",
            "category": "baseline",
            "requires_env": [],
            "requires_real_adapter": True,
            "steps": [
                {
                    "name": "echo prints ok",
                    "kind": "cli",
                    "check": "echo prints ok",
                    "standard": "founder-expectations.F02",
                    "command": "echo ok",
                    "timeout_seconds": 30,
                    "expect": {"exit_code": 0, "stdout_has": ["ok"]},
                }
            ],
        }
    )


class TestSchemaFlag:
    def test_defaults_to_false(self) -> None:
        scenario = Scenario.from_dict(
            {
                "name": "plain",
                "description": "d",
                "intent": "i",
                "user_level": "L0",
                "steps": [
                    {
                        "name": "s",
                        "kind": "cli",
                        "check": "c",
                        "standard": "founder-expectations.F02",
                        "command": "echo ok",
                        "expect": {"exit_code": 0},
                    }
                ],
            }
        )
        assert scenario.requires_real_adapter is False

    def test_true_parses(self) -> None:
        assert _scenario().requires_real_adapter is True

    def test_wrong_type_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="requires_real_adapter"):
            Scenario.from_dict(
                {
                    "name": "bad",
                    "description": "d",
                    "intent": "i",
                    "user_level": "L0",
                    "requires_real_adapter": "yes",
                    "steps": [
                        {
                            "name": "s",
                            "kind": "cli",
                            "check": "c",
                            "standard": "founder-expectations.F02",
                            "command": "echo ok",
                            "expect": {"exit_code": 0},
                        }
                    ],
                }
            )

    def test_publish_scenario_declares_it(self) -> None:
        by_name = {scenario.name: scenario for scenario in load_scenarios(default_scenarios_dir())}
        assert by_name["publish-draft-only-real-adapters"].requires_real_adapter is True


class TestApplyStubBin:
    def test_unset_is_a_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(STUB_BIN_ENV, raising=False)
        before = os.environ.get("PATH", "")
        assert apply_stub_bin_to_path() is None
        assert os.environ.get("PATH", "") == before

    def test_set_prepends_and_is_idempotent(self, tmp_path: Path) -> None:
        environ = {"PATH": "/usr/bin", STUB_BIN_ENV: str(tmp_path)}
        assert apply_stub_bin_to_path(environ) == str(tmp_path)
        assert environ["PATH"] == f"{tmp_path}{os.pathsep}/usr/bin"
        assert apply_stub_bin_to_path(environ) == str(tmp_path)
        assert environ["PATH"] == f"{tmp_path}{os.pathsep}/usr/bin"

    def test_stub_is_resolvable_after_apply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(STUB_BIN_ENV, str(STUB_BIN))
        apply_stub_bin_to_path()
        assert shutil.which("ffmpeg") == str(STUB_BIN / "ffmpeg")


class TestCommittedStubFixture:
    def test_every_stub_exists_and_is_executable(self) -> None:
        for name in STUB_NAMES:
            path = STUB_BIN / name
            assert path.is_file(), f"missing stub {name}"
            assert os.access(path, os.X_OK), f"stub {name} is not executable"

    def test_ffprobe_prints_a_duration(self) -> None:
        import subprocess

        proc = subprocess.run(
            [str(STUB_BIN / "ffprobe")], capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0
        assert float(proc.stdout.strip()) == 0.0


class TestSuiteExclusion:
    def _write_lib(self, tmp_path: Path) -> Path:
        lib = tmp_path / "scenarios"
        lib.mkdir()
        shutil.copy2(STANDARDS_FIXTURE, lib / "STANDARDS.md")
        (lib / "green.yaml").write_text(
            _CLI_SCENARIO.format(name="plain-green", extra=""), encoding="utf-8"
        )
        (lib / "real.yaml").write_text(
            _CLI_SCENARIO.format(name="real-adapter", extra="requires_real_adapter: true\n"),
            encoding="utf-8",
        )
        return lib

    def test_excludes_flagged_scenario_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lib = self._write_lib(tmp_path)
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(lib))
        record = asyncio.run(run_validation_suite_async(None, lib, runs_root=tmp_path / "runs"))
        names = _scenario_names(record)
        assert names == ["plain-green"]
        assert record["requires_real_adapter_excluded"] == ["real-adapter"]

    def test_include_flag_keeps_flagged_scenario(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lib = self._write_lib(tmp_path)
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(lib))
        record = asyncio.run(
            run_validation_suite_async(
                None,
                lib,
                runs_root=tmp_path / "runs",
                include_requires_real_adapter=True,
            )
        )
        names = sorted(_scenario_names(record))
        assert names == ["plain-green", "real-adapter"]
        assert "requires_real_adapter_excluded" not in record
