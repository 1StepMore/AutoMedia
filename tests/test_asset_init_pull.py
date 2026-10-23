"""Tests for best-effort asset-pack pulling during project creation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from automedia.core import asset_pack
from automedia.core.project import Project

_PULL_SCRIPT = """\
import json
import pathlib
import sys

project = pathlib.Path(sys.argv[sys.argv.index("--project") + 1])
assets = project / "assets"
assets.mkdir(parents=True, exist_ok=True)
(assets / "_source.json").write_text(json.dumps({
    "preset": "video-core",
    "mode": "copy",
    "date": "2026-10-22",
    "files": [{"path": "assets/fonts/brand.woff2", "sha256": "a" * 64}],
}))
"""

_FAILING_SCRIPT = "import sys\nsys.exit(1)\n"

_PARTIAL_FAILING_SCRIPT = """\
import pathlib
import sys

project = pathlib.Path(sys.argv[sys.argv.index("--project") + 1])
assets = project / "assets"
assets.mkdir(parents=True, exist_ok=True)
(assets / "half-copied.bin").write_bytes(b"partial")
sys.exit(1)
"""


def _make_library(tmp_path: Path, script_body: str) -> Path:
    library = tmp_path / "library"
    tools = library / "_tools"
    tools.mkdir(parents=True)
    (tools / "pull_assets.py").write_text(script_body, encoding="utf-8")
    return library


@pytest.fixture(autouse=True)
def _clear_asset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOMEDIA_SKIP_ASSET_PULL", raising=False)
    monkeypatch.delenv("AUTOMEDIA_ASSET_LIBRARY", raising=False)


def test_missing_library_warns_and_never_runs_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("AUTOMEDIA_ASSET_LIBRARY", str(missing))

    def _fail(*args: object, **kwargs: object) -> None:
        pytest.fail("subprocess.run must not be called when the library is missing")

    monkeypatch.setattr(asset_pack.subprocess, "run", _fail)

    assert asset_pack.pull_video_assets(tmp_path / "project") is None


def test_existing_library_pulls_pack_and_writes_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _make_library(tmp_path, _PULL_SCRIPT)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    calls: list[list[str]] = []
    real_run = subprocess.run

    def _recording_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(asset_pack.subprocess, "run", _recording_run)

    record = asset_pack.pull_video_assets(project_dir, library_dir=library)

    assert record is not None
    assert len(calls) == 1
    args = calls[0]
    assert "--preset" in args
    assert args[args.index("--preset") + 1] == "video-core"

    record_path = project_dir / "assets" / "_pull_record.json"
    assert record_path.is_file()
    persisted = json.loads(record_path.read_text(encoding="utf-8"))
    assert persisted["library"] == str(library.resolve())
    assert persisted["preset"] == "video-core"
    assert persisted["file_count"] == 1
    assert isinstance(persisted["manifest_digest"], str)
    assert len(persisted["manifest_digest"]) == 64
    int(persisted["manifest_digest"], 16)

    assert not any(path.is_symlink() for path in (project_dir / "assets").rglob("*"))


def test_failed_pull_returns_none_without_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    library = _make_library(tmp_path, _FAILING_SCRIPT)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with caplog.at_level("WARNING"):
        assert asset_pack.pull_video_assets(project_dir, library_dir=library) is None

    assert "Asset pull failed" in caplog.text
    assert not (project_dir / "assets" / "_pull_record.json").exists()


@pytest.mark.parametrize("assets_dir_exists", [False, True])
def test_failed_pull_discards_partial_assets_and_retry_succeeds(
    tmp_path: Path, assets_dir_exists: bool
) -> None:
    library = _make_library(tmp_path, _PARTIAL_FAILING_SCRIPT)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    if assets_dir_exists:
        (project_dir / "assets").mkdir()

    assert asset_pack.pull_video_assets(project_dir, library_dir=library) is None

    assets = project_dir / "assets"
    if assets_dir_exists:
        assert assets.is_dir()
        assert not any(assets.iterdir())
    else:
        assert not assets.exists()

    (library / "_tools" / "pull_assets.py").write_text(_PULL_SCRIPT, encoding="utf-8")
    record = asset_pack.pull_video_assets(project_dir, library_dir=library)

    assert record is not None
    assert (assets / "_source.json").is_file()
    assert (assets / "_pull_record.json").is_file()


def test_project_init_survives_failed_pull(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _make_library(tmp_path, _FAILING_SCRIPT)
    monkeypatch.setenv("AUTOMEDIA_ASSET_LIBRARY", str(library))

    project = Project.init("asset pull failure", "default", base_dir=str(tmp_path / "projects"))

    root = Path(project.project_dir)
    for sub in (
        "01_content/drafts",
        "02_images/cover",
        "03_video",
        "04_subtitle",
        "05_review",
        "06_publish",
    ):
        assert (root / sub).is_dir()
    assert (root / "00_project_info.json").is_file()
    assert not (root / "assets" / "_pull_record.json").exists()


def test_project_init_skips_assets_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTOMEDIA_SKIP_ASSET_PULL", "yes")

    project = Project.init("skip asset pull", "default", base_dir=str(tmp_path / "projects"))

    assert not (Path(project.project_dir) / "assets").exists()
