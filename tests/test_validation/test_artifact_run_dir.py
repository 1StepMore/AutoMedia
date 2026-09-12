"""T-16 — artifacts live inside the per-run directory, exclusively created.

RED on the pre-T-16 engine: GREEN-step artifacts were staged under the shared
runs root (``validation-runs/artifacts/<step_index>-<basename>``) with
``shutil.copy2``, so two runs collecting the same step/basename overwrote
each other and the evidence sat outside the timestamped run dir.

GREEN: a GREEN step's artifacts land in ``<run_dir>/artifacts/`` — the same
immutable timestamped directory that holds ``scenarios.json`` — with
``O_CREAT|O_EXCL`` writes, so an existing artifact is never overwritten
(a same-basename collision gets a distinct file).  ``save=False`` collects
nothing.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from automedia.validation.engine import (
    make_adapters,
    run_validation_scenario_async,
    run_validation_suite_async,
)
from automedia.validation.persist import collect_artifacts, list_runs
from automedia.validation.schema import ArtifactCheck, Expect, Scenario, Step

_STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)

# The step passes (cli dispatch) and collects ``probe.txt`` from the run cwd,
# which each test pre-creates in its dedicated work directory.
ARTIFACT_YAML = """\
name: artifact-producer
description: collects a file as an artifact
intent: prove artifacts land inside the per-run directory
user_level: L0
steps:
  - name: write artifact
    kind: cli
    check: command runs
    standard: founder-expectations.F01
    command: python3 -c "print('probe')"
    expect:
      success: true
    collect_artifacts:
      - path: probe.txt
        required: true
"""


def _artifact_file(run_dir: Path, entry: dict[str, object]) -> Path:
    """Resolve an artifact entry against its run dir (absolute or run-relative)."""
    copied = Path(str(entry["copied_to"]))
    return copied if copied.is_absolute() else run_dir / copied


def _cli_collect_step(path: str = "probe.txt") -> Step:
    """A cli step that passes and declares one collected artifact."""
    return Step(
        name="collect outputs",
        kind="cli",
        check="command runs",
        standard="founder-expectations.F01",
        command="python3 -c \"print('ok')\"",
        expect=Expect(success=True),
        collect_artifacts=[ArtifactCheck(path=path)],
    )


@pytest.fixture
def artifact_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A one-scenario library whose step collects a synthetic artifact."""
    root = tmp_path / "scenarios"
    root.mkdir()
    shutil.copy2(_STANDARDS_FIXTURE, root / "STANDARDS.md")
    (root / "artifact.yaml").write_text(ARTIFACT_YAML, encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))
    return root


def test_suite_collects_inside_per_run_artifacts_dir(
    artifact_library: Path, tmp_path: Path
) -> None:
    """A persisted suite run puts artifacts in the run dir, never the runs root."""
    runs_root = tmp_path / "runs"
    work = tmp_path / "work"
    work.mkdir()
    (work / "probe.txt").write_text("probe", encoding="utf-8")
    asyncio.run(run_validation_suite_async(None, artifact_library, runs_root=runs_root, cwd=work))
    (run_name,) = list_runs(runs_root)
    run_dir = runs_root / run_name
    assert (run_dir / "scenarios.json").is_file()
    assert (run_dir / "artifacts" / "1-probe.txt").is_file()
    # No shared artifact dir ever appears beside the run dirs.
    assert not (runs_root / "artifacts").exists()
    stored = json.loads((run_dir / "scenarios.json").read_text(encoding="utf-8"))
    entry = stored["scenarios"][0]["steps"][0]["artifacts"][0]
    resolved = _artifact_file(run_dir, entry).resolve()
    assert resolved == (run_dir / "artifacts" / "1-probe.txt").resolve()
    assert resolved.is_file()


def test_two_runs_same_step_basename_keep_distinct_artifacts(
    artifact_library: Path, tmp_path: Path
) -> None:
    """Two runs with the same step index + basename never share a file."""
    runs_root = tmp_path / "runs"
    work = tmp_path / "work"
    work.mkdir()
    (work / "probe.txt").write_text("probe", encoding="utf-8")
    asyncio.run(run_validation_suite_async(None, artifact_library, runs_root=runs_root, cwd=work))
    asyncio.run(run_validation_suite_async(None, artifact_library, runs_root=runs_root, cwd=work))
    names = list_runs(runs_root)
    assert len(names) == 2
    targets: list[Path] = []
    for name in names:
        target = runs_root / name / "artifacts" / "1-probe.txt"
        assert target.is_file(), f"missing per-run artifact for {name}"
        targets.append(target.resolve())
    assert targets[0] != targets[1]
    assert len(set(targets)) == 2


def test_collect_artifacts_same_basename_never_overwrites(tmp_path: Path) -> None:
    """Two sources sharing a basename produce two distinct collected files."""
    for sub, text in (("a", "from-a"), ("b", "from-b")):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "report.md").write_text(text, encoding="utf-8")
    step = Step(
        name="collect outputs",
        kind="file",
        check="artifacts copied",
        standard="founder-expectations.F01",
        command="unused",
        expect=Expect(),
        collect_artifacts=[
            ArtifactCheck(path="a/report.md"),
            ArtifactCheck(path="b/report.md"),
        ],
    )
    run_dir = tmp_path / "run"
    entries = collect_artifacts(step, 1, run_dir, cwd=tmp_path)
    assert [entry["ok"] for entry in entries] == [True, True]
    targets = [_artifact_file(run_dir, entry) for entry in entries]
    assert targets[0] != targets[1]
    assert targets[0].read_text(encoding="utf-8") == "from-a"
    assert targets[1].read_text(encoding="utf-8") == "from-b"


def test_save_false_collects_nothing_and_leaves_no_evidence(
    artifact_library: Path, tmp_path: Path
) -> None:
    """The no-save path must not create a run dir or collect artifacts."""
    runs_root = tmp_path / "runs"
    work = tmp_path / "work"
    work.mkdir()
    record = asyncio.run(
        run_validation_suite_async(
            None, artifact_library, runs_root=runs_root, save=False, cwd=work
        )
    )
    scenarios = record["scenarios"]
    assert isinstance(scenarios, list)
    assert len(scenarios) == 1
    assert not runs_root.exists()


def test_scenario_without_run_root_skips_collection(tmp_path: Path) -> None:
    """A standalone scenario run with no run dir collects nothing, never raises."""
    scenario = Scenario(
        name="no-run-root",
        description="standalone collect",
        intent="prove a missing run dir is safe",
        steps=[_cli_collect_step()],
        cleanup_steps=[],
    )
    record = asyncio.run(
        run_validation_scenario_async(scenario, make_adapters(None), run_root=None, cwd=tmp_path)
    )
    steps = record["steps"]
    assert isinstance(steps, list)
    assert isinstance(steps[0], dict)
    assert "artifacts" not in steps[0]
