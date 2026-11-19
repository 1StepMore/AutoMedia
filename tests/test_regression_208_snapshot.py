"""#565 — ``_snapshot_dir`` must tolerate unstat-able entries.

The reg-208 guard snapshots the real ``~/.automedia`` to prove it was not
modified.  A user config directory can legitimately contain entries Windows
cannot stat (a WSL-created ``node_modules/.bin`` symlink raises WinError
1920); the guard must record such entries as present-without-attributes
instead of crashing.  Loaded via ``importlib`` — ``scripts/`` is not a
package (same pattern as ``tests/test_check_release_scope.py``).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "regression_208_check.py"

_spec = importlib.util.spec_from_file_location("regression_208_check", _SCRIPT)
assert _spec is not None and _spec.loader is not None
regression_208_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(regression_208_check)

_snapshot_dir = regression_208_check._snapshot_dir


def test_snapshot_dir_records_unstat_entry_as_present_without_attributes(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "ok.txt").write_text("fine")
    weird = tmp_path / "weird.bin"
    weird.write_text("data")

    real_stat = os.stat

    def fake_stat(path: object, *args: object, **kwargs: object):
        if str(path).endswith(str(weird.name)):
            raise OSError(1920, "system cannot access this file")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "stat", fake_stat)

    snapshot = _snapshot_dir(tmp_path)

    by_name = {name: (size, mtime) for name, size, mtime in snapshot}
    assert by_name["ok.txt"][0] >= 0, "statable file keeps its real size"
    assert by_name[str(weird.name)] == (-1, 0), (
        "unstat-able entry survives as present-without-attributes"
    )


def test_snapshot_dir_stable_across_repeated_calls(tmp_path: Path, monkeypatch) -> None:
    """Two snapshots of an unstat-able entry must compare equal (untouched)."""
    (tmp_path / "only.bin").write_text("payload")

    real_stat = os.stat

    def fake_stat(path: object, *args: object, **kwargs: object):
        if str(path).endswith("only.bin"):
            raise OSError(1920, "system cannot access this file")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "stat", fake_stat)

    assert _snapshot_dir(tmp_path) == _snapshot_dir(tmp_path)


def test_snapshot_dir_still_reports_removal(tmp_path: Path, monkeypatch) -> None:
    """If an unstat-able entry disappears, the snapshots must differ."""
    weird = tmp_path / "gone.bin"
    weird.write_text("payload")

    real_stat = os.stat

    def fake_stat(path: object, *args: object, **kwargs: object):
        if str(path).endswith("gone.bin"):
            raise OSError(1920, "system cannot access this file")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "stat", fake_stat)
    before = _snapshot_dir(tmp_path)

    weird.unlink()
    after = _snapshot_dir(tmp_path)

    assert before != after, "removal of an unstat-able entry must be detected"


def test_doctor_python_skips_unstat_venv_candidate(monkeypatch) -> None:
    """A WSL-symlink ``.venv/bin/python`` (unstat-able on Windows) must not
    crash interpreter resolution — the resolver skips it (#565).

    ``sys.executable`` is replaced by a sentinel because a "path differs" check
    is vacuous when pytest itself runs under the repo's ``.venv/bin/python``:
    the fallback then equals the skipped candidate (#569).
    """
    from pathlib import Path as _Path

    repo_root = regression_208_check._REPO_ROOT
    wsl_python = repo_root / ".venv" / "bin" / "python"
    real_is_file = _Path.is_file

    def fake_is_file(self: _Path) -> bool:
        if self == wsl_python:
            raise OSError(1920, "system cannot access this file")
        return real_is_file(self)

    monkeypatch.setattr(_Path, "is_file", fake_is_file)
    monkeypatch.setattr(
        regression_208_check.sys, "executable", "<sentinel-interpreter>"
    )

    result = regression_208_check._doctor_python()

    assert result == ["<sentinel-interpreter>"], (
        "unstat-able candidate must be skipped, falling back to sys.executable"
    )


def test_user_scope_guard_holds_on_this_platform(tmp_path: Path) -> None:
    """Guard 3 end-to-end on the running platform: the refused write leaves the
    seed intact and the opt-in lands.  On Windows this pins the USERPROFILE
    redirect (#565); on POSIX it pins the pre-existing HOME behaviour."""
    failures = regression_208_check._check_user_scope_guard(tmp_path)

    assert failures == [], failures
