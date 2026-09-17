"""Unit tests for director sign-off (W4-T5).

Covers: the pinned line format ``YYYY-MM-DDTHH:MM:SS <signer> <verdict>``;
APPEND semantics (never overwrite — the director may sign again, and the
sign-off history is immutable); ``is_signed`` before/after; ``list_unsigned``
excluding signed runs (newest-first, inheriting ``persist.list_runs``);
``signoff_status`` shape for the report renderer; and :class:`SignoffError`
on an unknown run dir or an unusable verdict (empty / whitespace / newline).

All tests use ``tmp_path`` only — never the real ``validation-runs/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.validation.signoff import (
    DEFAULT_SIGNER,
    SIGNED_FILENAME,
    SignoffError,
    is_signed,
    list_unsigned,
    sign_run,
    signoff_status,
)

FROZEN_STAMP = "2026-08-14T12:00:00"


def _seed_run(root: Path, name: str) -> Path:
    """Create a run dir containing scenarios.json, as persist_run would."""
    run_dir = root / name
    run_dir.mkdir(parents=True)
    (run_dir / "scenarios.json").write_text("{}", encoding="utf-8")
    return run_dir


def _freeze_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("automedia.validation.signoff._stamp_now", lambda: FROZEN_STAMP)


class TestSignRun:
    def test_writes_pinned_line_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _freeze_stamp(monkeypatch)
        _seed_run(tmp_path, "run-a")
        path = sign_run(tmp_path, "run-a", "approved")
        assert path == tmp_path / "run-a" / SIGNED_FILENAME
        assert path.read_text(encoding="utf-8") == f"{FROZEN_STAMP} {DEFAULT_SIGNER} approved\n"

    def test_records_custom_signer(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze_stamp(monkeypatch)
        _seed_run(tmp_path, "run-a")
        sign_run(tmp_path, "run-a", "rejected", signer="qa-lead")
        assert path_lines(tmp_path, "run-a") == [f"{FROZEN_STAMP} qa-lead rejected"]

    def test_append_never_overwrites(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze_stamp(monkeypatch)
        _seed_run(tmp_path, "run-a")
        sign_run(tmp_path, "run-a", "approved")
        sign_run(tmp_path, "run-a", "approved-with-waivers")
        lines = path_lines(tmp_path, "run-a")
        assert lines == [
            f"{FROZEN_STAMP} {DEFAULT_SIGNER} approved",
            f"{FROZEN_STAMP} {DEFAULT_SIGNER} approved-with-waivers",
        ]

    def test_append_preserves_pre_existing_sign_off_history(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _freeze_stamp(monkeypatch)
        run_dir = _seed_run(tmp_path, "run-a")
        signed = run_dir / SIGNED_FILENAME
        signed.write_text("2026-08-13T09:00:00 director approved\n", encoding="utf-8")
        sign_run(tmp_path, "run-a", "approved")
        assert signed.read_text(encoding="utf-8") == (
            f"2026-08-13T09:00:00 director approved\n{FROZEN_STAMP} {DEFAULT_SIGNER} approved\n"
        )

    def test_creates_signed_txt_when_absent(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        path = sign_run(tmp_path, "run-a", "approved")
        assert path.is_file()

    def test_missing_run_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SignoffError, match="run directory does not exist"):
            sign_run(tmp_path, "ghost-run", "approved")

    def test_missing_runs_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SignoffError):
            sign_run(tmp_path / "no-such-root", "run-a", "approved")

    def test_run_dir_existence_is_the_only_gate(self, tmp_path: Path) -> None:
        # Spec: sign_run checks the run DIR exists (the record file is not
        # required — the director signs the run directory, and signing a
        # bare dir is permitted; list_unsigned filters on the record).
        (tmp_path / "bare-dir").mkdir()
        path = sign_run(tmp_path, "bare-dir", "approved")
        assert path.is_file()

    def test_empty_verdict_raises(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        with pytest.raises(SignoffError, match="non-empty"):
            sign_run(tmp_path, "run-a", "")

    def test_whitespace_verdict_raises(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        with pytest.raises(SignoffError, match="non-empty"):
            sign_run(tmp_path, "run-a", "   ")

    def test_multiline_verdict_raises(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        with pytest.raises(SignoffError, match="single line"):
            sign_run(tmp_path, "run-a", "approved\nsee note")

    def test_failed_sign_does_not_touch_signed_txt(self, tmp_path: Path) -> None:
        run_dir = _seed_run(tmp_path, "run-a")
        with pytest.raises(SignoffError):
            sign_run(tmp_path, "run-a", "")
        assert not (run_dir / SIGNED_FILENAME).exists()


class TestIsSigned:
    def test_false_before_sign_off(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        assert is_signed(tmp_path, "run-a") is False

    def test_true_after_sign_off(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        sign_run(tmp_path, "run-a", "approved")
        assert is_signed(tmp_path, "run-a") is True

    def test_false_for_unknown_run(self, tmp_path: Path) -> None:
        assert is_signed(tmp_path, "ghost-run") is False

    def test_false_when_signed_txt_empty(self, tmp_path: Path) -> None:
        run_dir = _seed_run(tmp_path, "run-a")
        (run_dir / SIGNED_FILENAME).write_text("", encoding="utf-8")
        assert is_signed(tmp_path, "run-a") is False

    def test_false_when_signed_txt_whitespace_only(self, tmp_path: Path) -> None:
        run_dir = _seed_run(tmp_path, "run-a")
        (run_dir / SIGNED_FILENAME).write_text(" \n ", encoding="utf-8")
        assert is_signed(tmp_path, "run-a") is False


class TestListUnsigned:
    def test_lists_runs_without_sign_off(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        _seed_run(tmp_path, "run-b")
        assert list_unsigned(tmp_path) == ["run-b", "run-a"]

    def test_excludes_signed_runs(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        _seed_run(tmp_path, "run-b")
        sign_run(tmp_path, "run-a", "approved")
        assert list_unsigned(tmp_path) == ["run-b"]

    def test_empty_signed_txt_counts_as_unsigned(self, tmp_path: Path) -> None:
        run_dir = _seed_run(tmp_path, "run-a")
        (run_dir / SIGNED_FILENAME).write_text("", encoding="utf-8")
        assert list_unsigned(tmp_path) == ["run-a"]

    def test_newest_first_order(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "20260814-120000-000001")
        _seed_run(tmp_path, "20260814-120000-000002")
        assert list_unsigned(tmp_path) == [
            "20260814-120000-000002",
            "20260814-120000-000001",
        ]

    def test_missing_root_is_empty(self, tmp_path: Path) -> None:
        assert list_unsigned(tmp_path / "no-such-root") == []


class TestSignoffStatus:
    def test_unsigned_run_shape(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        assert signoff_status(tmp_path) == {
            "run-a": {"run": "run-a", "signed": False, "verdict_lines": []}
        }

    def test_signed_run_carries_verdict_lines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _freeze_stamp(monkeypatch)
        _seed_run(tmp_path, "run-a")
        sign_run(tmp_path, "run-a", "approved")
        sign_run(tmp_path, "run-a", "approved-with-waivers", signer="qa-lead")
        status = signoff_status(tmp_path)
        assert status["run-a"]["signed"] is True
        assert status["run-a"]["verdict_lines"] == [
            "2026-08-14T12:00:00 director approved",
            "2026-08-14T12:00:00 qa-lead approved-with-waivers",
        ]

    def test_covers_all_runs_newest_first(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        _seed_run(tmp_path, "run-b")
        sign_run(tmp_path, "run-a", "approved")
        assert list(signoff_status(tmp_path)) == ["run-b", "run-a"]

    def test_missing_root_is_empty(self, tmp_path: Path) -> None:
        assert signoff_status(tmp_path / "no-such-root") == {}

    def test_ignores_non_run_dirs(self, tmp_path: Path) -> None:
        _seed_run(tmp_path, "run-a")
        (tmp_path / "not-a-run").mkdir()
        assert list(signoff_status(tmp_path)) == ["run-a"]


def path_lines(root: Path, run_name: str) -> list[str]:
    """The raw signed.txt lines for a run."""
    text = (root / run_name / SIGNED_FILENAME).read_text(encoding="utf-8")
    return text.splitlines()
