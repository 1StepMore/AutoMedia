"""Orientation-agnostic resolution floors for ``expect.media``.

``min_long_edge`` / ``min_short_edge`` grade max(width, height) and
min(width, height) so a 1080p floor holds for both landscape (1920×1080) and
portrait (1080×1920) output — the product picks orientation per-platform media
spec (runner ``get_video_media_spec()``), so a per-axis ``min_width: 1920``
assertion is mathematically unsatisfiable for portrait platforms.

All fixtures are synthetic mp4s generated with ``ffmpeg -f lavfi testsrc``
under ``tmp_path``; tests skip when ffmpeg/ffprobe are absent (same convention
as ``tests/test_validation/test_media_assertions.py``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from automedia.validation.expects import evaluate_expect
from automedia.validation.schema import Expect, SchemaError, Step


def make_video_step(expect: dict[str, Any], command: str) -> Step:
    return Step.from_dict(
        {
            "name": "probe",
            "kind": "file",
            "check": "video properties",
            "standard": "media.video",
            "command": command,
            "expect": expect,
        }
    )


def make_video(path: Path, size: str, duration: int = 1) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration}:size={size}:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def evaluate_video(tmp_path: Path, video: Path, media: dict[str, Any]):
    step = make_video_step(
        {"artifact_exists": str(video), "media": media},
        str(video),
    )
    return evaluate_expect(step.expect, {"success": True}, step=step, cwd=tmp_path)


def test_schema_accepts_edge_fields() -> None:
    parsed = Expect.from_dict(
        {"artifact_exists": "v.mp4", "media": {"min_long_edge": 1920, "min_short_edge": 1080}}
    )
    assert parsed.media is not None
    assert parsed.media.min_long_edge == 1920
    assert parsed.media.min_short_edge == 1080
    assert parsed.media.min_width is None
    assert parsed.media.min_height is None


def test_schema_rejects_negative_edge() -> None:
    with pytest.raises(SchemaError):
        Expect.from_dict({"artifact_exists": "v.mp4", "media": {"min_long_edge": -1}})


class TestOrientationAgnostic1080p:
    """min_long_edge: 1920 / min_short_edge: 1080 on both orientations."""

    MEDIA = {"min_long_edge": 1920, "min_short_edge": 1080}

    def test_landscape_passes(self, tmp_path: Path) -> None:
        video = tmp_path / "landscape.mp4"
        make_video(video, "1920x1080")
        result = evaluate_video(tmp_path, video, self.MEDIA)
        assert result.passed is True, result.failures

    def test_portrait_passes(self, tmp_path: Path) -> None:
        video = tmp_path / "portrait.mp4"
        make_video(video, "1080x1920")
        result = evaluate_video(tmp_path, video, self.MEDIA)
        assert result.passed is True, result.failures

    def test_below_1080p_fails_naming_min_long_edge(self, tmp_path: Path) -> None:
        video = tmp_path / "small.mp4"
        make_video(video, "1280x720")
        result = evaluate_video(tmp_path, video, self.MEDIA)
        assert result.passed is False
        assert any(
            "min_long_edge" in failure and "1280" in failure for failure in result.failures
        ), result.failures

    def test_square_fails_short_enough_but_long_edge_insufficient(
        self, tmp_path: Path
    ) -> None:
        video = tmp_path / "square.mp4"
        make_video(video, "1080x1080")
        result = evaluate_video(tmp_path, video, self.MEDIA)
        assert result.passed is False
        assert any("min_long_edge" in failure for failure in result.failures), result.failures


class TestEdgeOnlyStillEvaluated:
    """Only min_long_edge set (no min_width/min_height) must not be skipped."""

    def test_only_min_long_edge_passes_when_satisfied(self, tmp_path: Path) -> None:
        video = tmp_path / "landscape.mp4"
        make_video(video, "1920x1080")
        result = evaluate_video(tmp_path, video, {"min_long_edge": 100})
        assert result.passed is True, result.failures

    def test_only_min_long_edge_fails_when_violated(self, tmp_path: Path) -> None:
        video = tmp_path / "small.mp4"
        make_video(video, "640x360")
        result = evaluate_video(tmp_path, video, {"min_long_edge": 1920})
        assert result.passed is False
        assert any("min_long_edge" in failure for failure in result.failures), result.failures


class TestPerAxisRegression:
    """min_width/min_height keep their original per-axis semantics."""

    def test_landscape_still_passes(self, tmp_path: Path) -> None:
        video = tmp_path / "landscape.mp4"
        make_video(video, "1920x1080")
        result = evaluate_video(tmp_path, video, {"min_width": 1920, "min_height": 1080})
        assert result.passed is True, result.failures

    def test_portrait_still_fails_min_width(self, tmp_path: Path) -> None:
        video = tmp_path / "portrait.mp4"
        make_video(video, "1080x1920")
        result = evaluate_video(tmp_path, video, {"min_width": 1920, "min_height": 1080})
        assert result.passed is False
        assert any("min_width" in failure for failure in result.failures), result.failures


class TestEdgeAndPerAxisCoexist:
    """Edge floors and per-axis floors can be combined."""

    def test_both_sets_evaluated(self, tmp_path: Path) -> None:
        video = tmp_path / "portrait.mp4"
        make_video(video, "1080x1920")
        media = {"min_width": 1080, "min_long_edge": 1920, "min_short_edge": 1080}
        result = evaluate_video(tmp_path, video, media)
        assert result.passed is True, result.failures
        media["min_width"] = 1920  # portrait width 1080 violates it
        result = evaluate_video(tmp_path, video, media)
        assert result.passed is False
        assert any("min_width" in failure for failure in result.failures), result.failures
