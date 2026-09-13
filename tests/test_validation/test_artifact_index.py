"""Tr-06: every collected artifact resolves inside its run directory.

RED before Tr-06: ``collect_artifacts`` stored an arbitrary path string and
``persist_run`` accepted a record whose artifact pointed at another run's
directory, so recorded evidence could not be traced to its subject.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automedia.validation.persist import (
    ArtifactIndexError,
    assert_artifact_index,
    collect_artifacts,
    persist_run,
)
from automedia.validation.schema import ArtifactCheck, Expect, Step


def _collect_step(path: str = "probe.txt") -> Step:
    return Step(
        name="collect",
        kind="cli",
        check="collect a file",
        standard="founder-expectations.F01",
        command="python3 -c \"print('ok')\"",
        expect=Expect(success=True),
        collect_artifacts=[ArtifactCheck(path=path)],
    )


def test_collect_artifacts_stores_run_relative_path(tmp_path: Path) -> None:
    (tmp_path / "probe.txt").write_text("probe", encoding="utf-8")
    run_dir = tmp_path / "run"
    entries = collect_artifacts(_collect_step(), 1, run_dir, cwd=tmp_path)
    assert entries[0]["copied_to"] == "artifacts/1-probe.txt"
    assert (run_dir / str(entries[0]["copied_to"])).is_file()


def test_artifact_index_accepts_inside_and_rejects_cross_run(tmp_path: Path) -> None:
    inside = {"scenarios": [{"steps": [{"artifacts": [{"copied_to": "artifacts/1-x"}]}]}]}
    assert_artifact_index(inside, tmp_path / "run")

    cross = str(tmp_path / "other-run" / "artifacts" / "1-x")
    outside = {"scenarios": [{"steps": [{"artifacts": [{"copied_to": cross}]}]}]}
    with pytest.raises(ArtifactIndexError, match="outside the run directory"):
        assert_artifact_index(outside, tmp_path / "run")


def test_persist_run_refuses_cross_run_artifact(tmp_path: Path) -> None:
    other = tmp_path / "other-run" / "artifacts" / "1-x"
    other.parent.mkdir(parents=True)
    other.write_text("x", encoding="utf-8")
    record = {"scenarios": [{"steps": [{"artifacts": [{"copied_to": str(other)}]}]}]}
    with pytest.raises(ArtifactIndexError):
        persist_run(tmp_path / "runs", record, stamp="20260101-000000-000000")


def test_persist_run_accepts_run_relative_artifact(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "20260101-000000-000000"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "artifacts" / "1-x").write_text("x", encoding="utf-8")
    record = {"scenarios": [{"steps": [{"artifacts": [{"copied_to": "artifacts/1-x"}]}]}]}
    path = persist_run(tmp_path / "runs", record, run_dir=run_dir)
    assert json.loads(path.read_text(encoding="utf-8")) == record
