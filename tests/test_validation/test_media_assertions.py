"""Regression tests for the media/artifact assertion layer.

All fixtures are synthetic and live under ``tmp_path``.  Image tests need only
Pillow; the video probe test skips when ``ffmpeg``/``ffprobe`` are absent.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from automedia.validation.adapters import FileAdapter
from automedia.validation.expects import CHECK_TYPE_EVALUATORS, evaluate_expect
from automedia.validation.schema import Expect, SchemaError, Step


def make_step(check: str, expect: dict[str, Any], command: str) -> Step:
    return Step.from_dict(
        {
            "name": "probe",
            "kind": "file",
            "check": check,
            "standard": "artifact.glob-exists",
            "command": command,
            "expect": expect,
        }
    )


def solid_image(path: Path, size: tuple[int, int] = (64, 64)) -> None:
    from PIL import Image

    Image.new("RGB", size, (120, 120, 120)).save(path)


def gradient_image(path: Path, size: tuple[int, int] = (64, 64)) -> None:
    from PIL import Image

    gradient = Image.linear_gradient("L").resize(size)
    gradient.convert("RGB").save(path)


class TestSchema:
    def test_artifact_exists_and_glob_are_mutually_exclusive(self) -> None:
        with pytest.raises(SchemaError):
            Expect.from_dict({"artifact_exists": "a.png", "artifact_glob": "*.png"})

    def test_glob_without_media_is_allowed(self) -> None:
        parsed = Expect.from_dict({"artifact_glob": "frames/*.png"})
        assert parsed.artifact_glob == "frames/*.png"
        assert parsed.media is None

    def test_max_count_is_not_a_media_key(self) -> None:
        with pytest.raises(SchemaError):
            Expect.from_dict({"artifact_glob": "*.png", "media": {"max_count": 3}})

    def test_absolute_glob_is_rejected(self) -> None:
        with pytest.raises(SchemaError):
            Expect.from_dict({"artifact_glob": "/tmp/*.png"})


class TestMediaAssertions:
    def test_image_dimensions_and_non_uniform(self, tmp_path: Path) -> None:
        image = tmp_path / "photo.png"
        gradient_image(image)
        step = make_step(
            "media.image",
            {
                "artifact_exists": str(image),
                "media": {"min_width": 64, "min_height": 64, "non_uniform": True},
            },
            str(image),
        )
        result = evaluate_expect(step.expect, {"success": True}, step=step, cwd=tmp_path)
        assert result.passed is True, result.failures

    def test_flat_image_fails_non_uniform(self, tmp_path: Path) -> None:
        image = tmp_path / "flat.png"
        solid_image(image)
        step = make_step(
            "media.image",
            {"artifact_exists": str(image), "media": {"non_uniform": True}},
            str(image),
        )
        result = evaluate_expect(step.expect, {"success": True}, step=step, cwd=tmp_path)
        assert result.passed is False
        assert any("non_uniform" in failure for failure in result.failures)

    def test_carousel_glob_count_and_same_size(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        for index in range(2):
            solid_image(frames / f"{index}.png", (80, 80))
        expect = Expect.from_dict(
            {
                "artifact_glob": "frames/*.png",
                "media": {"min_count": 2, "same_size": True, "min_width": 80},
            }
        )
        step = make_step(
            "media.carousel",
            {
                "artifact_glob": "frames/*.png",
                "media": {"min_count": 2, "same_size": True, "min_width": 80},
            },
            str(tmp_path),
        )
        result = evaluate_expect(expect, {"success": True}, step=step, cwd=tmp_path)
        assert result.passed is True, result.failures

    def test_carousel_same_size_mismatch_fails(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        solid_image(frames / "a.png", (80, 80))
        solid_image(frames / "b.png", (81, 80))
        expect = Expect.from_dict({"artifact_glob": "frames/*.png", "media": {"same_size": True}})
        step = make_step(
            "media.carousel",
            {"artifact_glob": "frames/*.png", "media": {"same_size": True}},
            str(tmp_path),
        )
        result = evaluate_expect(expect, {"success": True}, step=step, cwd=tmp_path)
        assert result.passed is False
        assert any("same_size" in failure for failure in result.failures)

    def test_video_probe_when_tools_available(self, tmp_path: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None or shutil.which("ffprobe") is None:
            pytest.skip("ffmpeg/ffprobe not installed")
        video = tmp_path / "clip.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=1:size=160x120:rate=10",
                "-pix_fmt",
                "yuv420p",
                str(video),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        step = make_step(
            "media.video",
            {
                "artifact_exists": str(video),
                "media": {"min_duration_s": 0.5, "min_width": 160, "decodable": True},
            },
            str(video),
        )
        result = evaluate_expect(step.expect, {"success": True}, step=step, cwd=tmp_path)
        assert result.passed is True, result.failures


class TestTextSubtitleAndKeyword:
    def test_text_article_thresholds(self, tmp_path: Path) -> None:
        draft = tmp_path / "draft.md"
        draft.write_text("# Title\n\nFirst paragraph.\n\nSecond paragraph.", encoding="utf-8")
        expect = Expect.from_dict(
            {
                "artifact_exists": "draft.md",
                "text": {"min_paragraphs": 2, "min_headings": 1, "has_heading": True},
            }
        )
        result = evaluate_expect(expect, {"success": True}, cwd=tmp_path)
        assert result.passed is True, result.failures

    def test_text_failure_names_observed_value(self, tmp_path: Path) -> None:
        draft = tmp_path / "draft.md"
        draft.write_text("Only one paragraph.", encoding="utf-8")
        expect = Expect.from_dict({"artifact_exists": "draft.md", "text": {"min_paragraphs": 3}})
        result = evaluate_expect(expect, {"success": True}, cwd=tmp_path)
        assert result.passed is False
        assert "observed 1" in result.failures[0]

    def test_subtitle_monotonic_and_overlap(self, tmp_path: Path) -> None:
        srt = tmp_path / "sub.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nA\n\n2\n00:00:01,000 --> 00:00:02,000\nB\n",
            encoding="utf-8",
        )
        passing = Expect.from_dict(
            {"artifact_exists": "sub.srt", "subtitle": {"min_cues": 2, "monotonic": True}}
        )
        assert evaluate_expect(passing, {"success": True}, cwd=tmp_path).passed is True
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nA\n\n2\n00:00:00,500 --> 00:00:02,000\nB\n",
            encoding="utf-8",
        )
        overlapping = Expect.from_dict(
            {"artifact_exists": "sub.srt", "subtitle": {"min_cues": 2, "monotonic": True}}
        )
        result = evaluate_expect(overlapping, {"success": True}, cwd=tmp_path)
        assert result.passed is False
        assert any("monotonic" in failure for failure in result.failures)

    def test_text_similarity_passes_faithful_transcript(self, tmp_path: Path) -> None:
        (tmp_path / "script.txt").write_text(
            "别只盯着短视频，播客才是品牌影响力的慢变量。戴耳机通勤时，声音最贴身。",
            encoding="utf-8",
        )
        (tmp_path / "sub.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n"
            "别只盯着短视频，播客才是品牌影响力的慢变量\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\n戴耳机通勤时，声音最贴身\n",
            encoding="utf-8",
        )
        expect = Expect.from_dict(
            {
                "artifact_exists": "sub.srt",
                "text_similarity": {"reference": "script.txt", "min_ratio": 0.8},
            }
        )
        result = evaluate_expect(expect, {"success": True}, cwd=tmp_path)
        assert result.passed is True, result.failures

    def test_text_similarity_fails_garbled_transcript(self, tmp_path: Path) -> None:
        (tmp_path / "script.txt").write_text(
            "别只盯着短视频，播客才是品牌影响力的慢变量。戴耳机通勤时，声音最贴身。",
            encoding="utf-8",
        )
        (tmp_path / "sub.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n太别指定者短视评播课才是评牌影响力的慢编量\n",
            encoding="utf-8",
        )
        expect = Expect.from_dict(
            {
                "artifact_exists": "sub.srt",
                "text_similarity": {"reference": "script.txt", "min_ratio": 0.6},
            }
        )
        result = evaluate_expect(expect, {"success": True}, cwd=tmp_path)
        assert result.passed is False
        assert "text_similarity" in result.failures[0]
        assert "observed ratio" in result.failures[0]

    def test_text_similarity_missing_reference_is_a_failure(self, tmp_path: Path) -> None:
        (tmp_path / "sub.srt").write_text("hello", encoding="utf-8")
        expect = Expect.from_dict(
            {
                "artifact_exists": "sub.srt",
                "text_similarity": {"reference": "missing.txt", "min_ratio": 0.5},
            }
        )
        result = evaluate_expect(expect, {"success": True}, cwd=tmp_path)
        assert result.passed is False
        assert "cannot read reference" in result.failures[0]

    def test_keyword_coverage_ratio(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("alpha beta", encoding="utf-8")
        (tmp_path / "b.md").write_text("gamma", encoding="utf-8")
        expect = Expect.from_dict(
            {
                "keyword_coverage": {
                    "keywords": ["alpha", "beta", "missing"],
                    "min_ratio": 0.66,
                    "over": ["a.md", "b.md"],
                }
            }
        )
        result = evaluate_expect(expect, {"success": True}, cwd=tmp_path)
        assert result.passed is True, result.failures
        expect = Expect.from_dict(
            {
                "keyword_coverage": {
                    "keywords": ["alpha", "beta", "missing"],
                    "min_ratio": 1.0,
                    "over": ["a.md", "b.md"],
                }
            }
        )
        result = evaluate_expect(expect, {"success": True}, cwd=tmp_path)
        assert result.passed is False
        assert "missing" in result.failures[0]


class TestAdapterFacts:
    def test_glob_media_and_base_dir_facts(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        solid_image(frames / "0.png", (80, 80))
        step = make_step(
            "media.image",
            {"artifact_glob": "frames/*.png", "media": {"min_count": 1}},
            str(tmp_path),
        )
        result = FileAdapter().run(step)
        assert result.ok is True
        assert len(result.output["artifact_glob"]) == 1
        assert result.output["exists"] is True
        assert result.output["base_dir"] == str(tmp_path.resolve())
        assert result.output["media"][0]["width"] == 80

    def test_text_and_subtitle_facts(self, tmp_path: Path) -> None:
        draft = tmp_path / "draft.md"
        draft.write_text("# T\n\nBody.", encoding="utf-8")
        step = make_step(
            "text.article", {"artifact_exists": str(draft), "text": {"min_chars": 1}}, str(draft)
        )
        result = FileAdapter().run(step)
        assert result.output["text"]["has_heading"] is True
        assert result.output["base_dir"] == str(tmp_path.resolve())

    def test_missing_glob_facts(self, tmp_path: Path) -> None:
        step = make_step("artifact.glob-exists", {"artifact_glob": "nothing/*.png"}, str(tmp_path))
        result = FileAdapter().run(step)
        assert result.output["artifact_glob"] == []
        assert result.output["exists"] is False


def test_required_check_types_registered() -> None:
    required = {
        "artifact.glob-exists",
        "media.video",
        "media.audio",
        "media.image",
        "media.carousel",
        "text.article",
        "subtitle.srt",
        "quality.keyword-coverage",
    }
    assert required <= set(CHECK_TYPE_EVALUATORS)
