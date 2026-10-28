"""Unit tests for :mod:`automedia.validation.media_probe`.

Every fixture is synthetic and lives under ``tmp_path``.  Pillow is a core
dependency, so the image tests always run; the audio/video probes need
``ffmpeg``/``ffprobe`` and skip when the toolchain is absent.  Each probe must
report failure (``ok: False``) rather than silently passing on a missing or
unreadable artifact.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from automedia.validation.media_probe import (
    glob_artifacts,
    probe_image,
    probe_media,
    probe_srt,
    probe_text,
)


def _ffmpeg_toolchain_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


requires_ffmpeg = pytest.mark.skipif(
    not _ffmpeg_toolchain_available(),
    reason="ffmpeg/ffprobe not available on PATH",
)


def _solid_image(path: Path, size: tuple[int, int] = (64, 64)) -> None:
    from PIL import Image

    Image.new("RGB", size, (120, 120, 120)).save(path)


def _gradient_image(path: Path, size: tuple[int, int] = (80, 60)) -> None:
    from PIL import Image

    Image.linear_gradient("L").resize(size).convert("RGB").save(path)


def _write_silent_wav(path: Path, seconds: int = 1) -> None:
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=mono:d={seconds}",
            "-t",
            str(seconds),
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class TestProbeImage:
    def test_gradient_image_is_non_uniform(self, tmp_path: Path) -> None:
        image = tmp_path / "gradient.png"
        _gradient_image(image)

        result = probe_image(image)

        assert result["ok"] is True
        assert (result["width"], result["height"]) == (80, 60)
        assert result["format"] == "PNG"
        assert result["non_uniform"] is True
        assert result["stddev"] >= 1.0

    def test_solid_image_is_uniform(self, tmp_path: Path) -> None:
        image = tmp_path / "solid.png"
        _solid_image(image)

        result = probe_image(image)

        assert result["ok"] is True
        assert result["non_uniform"] is False

    def test_missing_file_fails_loudly(self, tmp_path: Path) -> None:
        result = probe_image(tmp_path / "absent.png")

        assert result["ok"] is False
        assert "file not found" in result["error"]

    def test_non_image_bytes_fail_loudly(self, tmp_path: Path) -> None:
        fake = tmp_path / "fake.png"
        fake.write_text("not an image", encoding="utf-8")

        result = probe_image(fake)

        assert result["ok"] is False
        assert result["error"]


class TestProbeText:
    def test_counts_headings_and_paragraphs(self, tmp_path: Path) -> None:
        draft = tmp_path / "draft.md"
        draft.write_text(
            "# Title\n\n"
            "First paragraph line one.\n"
            "Second line of the same paragraph.\n\n"
            "Second paragraph.\n\n"
            "```\n"
            "code block is not a paragraph\n"
            "```\n",
            encoding="utf-8",
        )

        result = probe_text(draft)

        assert result["ok"] is True
        assert result["has_heading"] is True
        assert result["headings"] == 1
        assert result["paragraphs"] == 2
        assert result["chars"] > 0

    def test_missing_file_fails_loudly(self, tmp_path: Path) -> None:
        result = probe_text(tmp_path / "absent.md")

        assert result["ok"] is False
        assert "file not found" in result["error"]


class TestProbeSrt:
    def test_ordered_cues_are_monotonic(self, tmp_path: Path) -> None:
        subtitle = tmp_path / "narration.srt"
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nfirst\n\n2\n00:00:01,500 --> 00:00:02,500\nsecond\n",
            encoding="utf-8",
        )

        result = probe_srt(subtitle)

        assert result["ok"] is True
        assert result["cues"] == 2
        assert result["monotonic"] is True
        assert result["first_start_s"] == pytest.approx(0.0)
        assert result["last_end_s"] == pytest.approx(2.5)

    def test_overlapping_cues_break_monotonicity(self, tmp_path: Path) -> None:
        subtitle = tmp_path / "narration.srt"
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nfirst\n\n2\n00:00:01,000 --> 00:00:03,000\nsecond\n",
            encoding="utf-8",
        )

        result = probe_srt(subtitle)

        assert result["ok"] is True
        assert result["cues"] == 2
        assert result["monotonic"] is False

    def test_missing_file_fails_loudly(self, tmp_path: Path) -> None:
        result = probe_srt(tmp_path / "absent.srt")

        assert result["ok"] is False
        assert "file not found" in result["error"]


class TestGlobArtifacts:
    def test_returns_sorted_absolute_matches(self, tmp_path: Path) -> None:
        nested = tmp_path / "02_images" / "body"
        nested.mkdir(parents=True)
        for name in ("b.png", "a.png"):
            _solid_image(nested / name)
        (nested / "ignored.txt").write_text("x", encoding="utf-8")

        matches = glob_artifacts(tmp_path, "02_images/body/*.png")

        assert [Path(match).name for match in matches] == ["a.png", "b.png"]
        assert all(Path(match).is_absolute() for match in matches)

    def test_missing_root_returns_empty(self, tmp_path: Path) -> None:
        assert glob_artifacts(tmp_path / "absent", "**/*.png") == []


@requires_ffmpeg
class TestProbeMedia:
    def test_audio_reports_duration_and_codec(self, tmp_path: Path) -> None:
        audio = tmp_path / "narration.wav"
        _write_silent_wav(audio, seconds=2)

        result = probe_media(audio)

        assert result["ok"] is True
        assert result["decodable"] is True
        assert result["has_audio"] is True
        assert result["has_video"] is False
        assert result["duration_s"] == pytest.approx(2.0, abs=0.2)
        assert result["codec"]

    def test_missing_file_fails_loudly(self, tmp_path: Path) -> None:
        result = probe_media(tmp_path / "absent.mp4")

        assert result["ok"] is False
        assert "file not found" in result["error"]

    def test_non_media_bytes_fail_loudly(self, tmp_path: Path) -> None:
        fake = tmp_path / "fake.mp4"
        fake.write_text("not media", encoding="utf-8")

        result = probe_media(fake)

        assert result["ok"] is False
        assert result["decodable"] is False
        assert result["error"]
