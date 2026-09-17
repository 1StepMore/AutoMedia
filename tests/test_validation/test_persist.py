"""Unit tests for run-record persistence (W1-T8).

Covers: exclusive-create (``os.makedirs(exist_ok=False)`` + ``O_CREAT|O_EXCL``)
— a pre-existing run dir or record is NEVER overwritten; the microsecond stamp
format ``%Y%m%d-%H%M%S-%f``; the random-suffix collision fallback (forced via
monkeypatched ``strftime``/``token_hex``); the ``latest.txt`` write+read
roundtrip; newest-first run listing; artifact collection incl. missing-file
semantics (optional tolerated, required loud).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from automedia.validation.persist import (
    PersistError,
    collect_artifacts,
    latest_run,
    list_runs,
    persist_run,
    write_latest_pointer,
)
from automedia.validation.schema import ArtifactCheck, Expect, Step

BASE = "20260814-120000-000001"


def step_with_artifacts(*checks: ArtifactCheck) -> Step:
    """A minimal valid Step carrying the given artifact checks."""
    return Step(
        name="collect outputs",
        kind="file",
        check="artifacts copied",
        standard="guide §3.4",
        command="unused",
        expect=Expect(),
        collect_artifacts=list(checks),
    )


def _seed_run(root: Path, name: str) -> None:
    """Create a run dir containing scenarios.json, as persist_run would."""
    run_dir = root / name
    run_dir.mkdir(parents=True)
    (run_dir / "scenarios.json").write_text("{}", encoding="utf-8")


def _frozen_stamp() -> str:
    """Always return the same base stamp, forcing a collision."""
    return BASE


def _fixed_token_hex(hex_value: str) -> Callable[[int], str]:
    """Return a token_hex replacement returning a fixed 6-hex value."""

    def token_hex(_nbytes: int) -> str:
        return hex_value

    return token_hex


class TestPersistRun:
    def test_creates_timestamped_dir_and_scenarios_json(self, tmp_path: Path) -> None:
        record = {"scenario": "health-smoke", "status": "passed"}
        path = persist_run(tmp_path, record, stamp=BASE)
        assert path == tmp_path / BASE / "scenarios.json"
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8")) == record

    def test_default_stamp_uses_microsecond_format(self, tmp_path: Path) -> None:
        path = persist_run(tmp_path, {"ok": True})
        assert re.fullmatch(r"\d{8}-\d{6}-\d{6}", path.parent.name)

    def test_creates_runs_root_when_missing(self, tmp_path: Path) -> None:
        root = tmp_path / "nested" / "runs"
        path = persist_run(root, {"ok": True}, stamp=BASE)
        assert path.parent.is_dir()

    def test_same_stamp_twice_raises_and_keeps_original(self, tmp_path: Path) -> None:
        first = {"verdict": "first"}
        second = {"verdict": "second"}
        persist_run(tmp_path, first, stamp=BASE)
        with pytest.raises(PersistError):
            persist_run(tmp_path, second, stamp=BASE)
        saved = json.loads((tmp_path / BASE / "scenarios.json").read_text(encoding="utf-8"))
        assert saved == first

    def test_pre_existing_run_dir_raises_persist_error(self, tmp_path: Path) -> None:
        (tmp_path / BASE).mkdir()
        with pytest.raises(PersistError, match="already exists"):
            persist_run(tmp_path, {"ok": True}, stamp=BASE)

    def test_collision_falls_back_to_random_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("automedia.validation.persist._stamp_now", _frozen_stamp)
        first = persist_run(tmp_path, {"n": 1})
        assert first.parent.name == BASE
        second = persist_run(tmp_path, {"n": 2})
        assert re.fullmatch(rf"{re.escape(BASE)}-[0-9a-f]{{6}}", second.parent.name)
        assert second.parent.is_dir()

    def test_collision_fallback_uses_random_suffix_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("automedia.validation.persist._stamp_now", _frozen_stamp)
        monkeypatch.setattr("automedia.validation.persist.token_hex", _fixed_token_hex("aabbcc"))
        persist_run(tmp_path, {"n": 1})
        second = persist_run(tmp_path, {"n": 2})
        assert second.parent.name == f"{BASE}-aabbcc"

    def test_collision_exhaustion_raises_persist_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("automedia.validation.persist._stamp_now", _frozen_stamp)
        monkeypatch.setattr("automedia.validation.persist.token_hex", _fixed_token_hex("000000"))
        (tmp_path / BASE).mkdir()
        (tmp_path / f"{BASE}-000000").mkdir()
        with pytest.raises(PersistError, match="unique run directory"):
            persist_run(tmp_path, {"ok": True})


class TestLatestPointer:
    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        write_latest_pointer(tmp_path, BASE)
        assert (tmp_path / "latest.txt").read_text(encoding="utf-8") == BASE
        assert latest_run(tmp_path) == BASE

    def test_write_returns_pointer_path(self, tmp_path: Path) -> None:
        assert write_latest_pointer(tmp_path, BASE) == tmp_path / "latest.txt"

    def test_absent_pointer_returns_none(self, tmp_path: Path) -> None:
        assert latest_run(tmp_path) is None

    def test_empty_pointer_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "latest.txt").write_text("  \n", encoding="utf-8")
        assert latest_run(tmp_path) is None

    def test_read_strips_whitespace(self, tmp_path: Path) -> None:
        (tmp_path / "latest.txt").write_text(f"  {BASE}  \n", encoding="utf-8")
        assert latest_run(tmp_path) == BASE

    def test_pointer_overwrites_previous(self, tmp_path: Path) -> None:
        write_latest_pointer(tmp_path, "20260813-000000-000000")
        write_latest_pointer(tmp_path, BASE)
        assert latest_run(tmp_path) == BASE


class TestListRuns:
    def test_newest_first(self, tmp_path: Path) -> None:
        for name in (
            "20260814-120000-000001",
            "20260814-110000-000001",
            "20260814-130000-000001",
        ):
            _seed_run(tmp_path, name)
        assert list_runs(tmp_path) == [
            "20260814-130000-000001",
            "20260814-120000-000001",
            "20260814-110000-000001",
        ]

    def test_suffixed_run_sorts_newest_first(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "20260814-120000-000001")
        _seed_run(tmp_path, "20260814-120000-000001-a1b2c3")
        assert list_runs(tmp_path)[0] == "20260814-120000-000001-a1b2c3"

    def test_ignores_dirs_without_scenarios_json(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "20260814-120000-000001")
        (tmp_path / "notes").mkdir()
        assert list_runs(tmp_path) == ["20260814-120000-000001"]

    def test_ignores_files_at_root(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "20260814-120000-000001")
        (tmp_path / "latest.txt").write_text(BASE, encoding="utf-8")
        assert list_runs(tmp_path) == ["20260814-120000-000001"]

    def test_missing_root_returns_empty(self, tmp_path: Path) -> None:
        assert list_runs(tmp_path / "does-not-exist") == []


class TestCollectArtifacts:
    def test_copies_into_artifacts_with_step_prefix(self, tmp_path: Path) -> None:
        source = tmp_path / "out" / "report.md"
        source.parent.mkdir()
        source.write_text("hello", encoding="utf-8")
        step = step_with_artifacts(ArtifactCheck(path="out/report.md"))
        entries = collect_artifacts(step, 3, tmp_path / "run", cwd=tmp_path)
        assert entries == [
            {
                "path": "out/report.md",
                "copied_to": "artifacts/3-report.md",
                "ok": True,
                "required": True,
                "reason": None,
            }
        ]
        copied = tmp_path / "run" / "artifacts" / "3-report.md"
        assert copied.read_text(encoding="utf-8") == "hello"

    def test_missing_optional_is_tolerated(self, tmp_path: Path) -> None:
        step = step_with_artifacts(ArtifactCheck(path="gone.txt", required=False))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert entries == [
            {
                "path": "gone.txt",
                "copied_to": None,
                "ok": False,
                "required": False,
                "reason": "missing",
            }
        ]

    def test_missing_required_is_loud(self, tmp_path: Path) -> None:
        step = step_with_artifacts(ArtifactCheck(path="gone.txt", required=True))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert entries[0]["ok"] is False
        assert entries[0]["required"] is True
        assert entries[0]["reason"] == "missing"
        assert entries[0]["copied_to"] is None

    def test_directory_source_is_not_a_file(self, tmp_path: Path) -> None:
        (tmp_path / "adir").mkdir()
        step = step_with_artifacts(ArtifactCheck(path="adir"))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert entries[0]["ok"] is False
        assert entries[0]["reason"] == "not-a-file"

    def test_absolute_path_ignores_cwd(self, tmp_path: Path) -> None:
        outside = tmp_path / "elsewhere" / "abs.txt"
        outside.parent.mkdir()
        outside.write_text("abs", encoding="utf-8")
        step = step_with_artifacts(ArtifactCheck(path=str(outside)))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert entries[0]["ok"] is True
        assert (tmp_path / "run" / "artifacts" / "1-abs.txt").is_file()

    def test_preserves_collect_order(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        step = step_with_artifacts(ArtifactCheck(path="a.txt"), ArtifactCheck(path="b.txt"))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert [entry["path"] for entry in entries] == ["a.txt", "b.txt"]
        assert [entry["ok"] for entry in entries] == [True, True]

    def test_mixed_missing_and_present(self, tmp_path: Path) -> None:
        (tmp_path / "here.txt").write_text("x", encoding="utf-8")
        step = step_with_artifacts(
            ArtifactCheck(path="here.txt"),
            ArtifactCheck(path="nope.txt", required=False),
        )
        entries = collect_artifacts(step, 2, tmp_path / "run", cwd=tmp_path)
        assert [entry["ok"] for entry in entries] == [True, False]

    def test_cwd_is_keyword_only(self, tmp_path: Path) -> None:
        step = step_with_artifacts(ArtifactCheck(path="a.txt"))
        with pytest.raises(TypeError):
            collect_artifacts(step, 1, tmp_path / "run", tmp_path)

    def test_expands_environment_variable_in_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        marker = tmp_path / "per-run" / "decision.json"
        marker.parent.mkdir()
        marker.write_text('{"ok": true}', encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_TEST_ARTIFACT", str(marker))
        step = step_with_artifacts(ArtifactCheck(path="$AUTOMEDIA_TEST_ARTIFACT"))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert entries[0]["ok"] is True
        assert entries[0]["path"] == str(marker)
        assert (tmp_path / "run" / "artifacts" / "1-decision.json").is_file()

    def test_unset_variable_stays_verbatim_and_misses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AUTOMEDIA_TEST_ARTIFACT", raising=False)
        step = step_with_artifacts(ArtifactCheck(path="$AUTOMEDIA_TEST_ARTIFACT", required=False))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert entries[0]["ok"] is False
        assert entries[0]["reason"] == "missing"
        assert entries[0]["path"] == "$AUTOMEDIA_TEST_ARTIFACT"

    def test_plain_path_is_unchanged(self, tmp_path: Path) -> None:
        (tmp_path / "plain.txt").write_text("x", encoding="utf-8")
        step = step_with_artifacts(ArtifactCheck(path="plain.txt"))
        entries = collect_artifacts(step, 1, tmp_path / "run", cwd=tmp_path)
        assert entries[0]["ok"] is True
        assert entries[0]["path"] == "plain.txt"
