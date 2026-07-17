"""Tests for image pipeline — ImagePipeline, ImageValidator, VisionQADegradation."""

from __future__ import annotations

import builtins
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from automedia.pipelines.image_pipeline import (
    BODY_IMAGE_SIZE,
    COVER_SPECS,
    ImagePipeline,
    ImageValidator,
    VisionQADegradation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image(
    path: str, width: int, height: int, color: tuple[int, int, int] = (100, 150, 200)
) -> str:
    """Create a minimal PNG image at *path* with given dimensions."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGB", (width, height), color=color)
    img.save(path, "PNG")
    return path


# =========================================================================
# ImagePipeline tests
# =========================================================================


class TestImagePipelineGenerateCovers:
    """generate_covers produces 4 cover images."""

    def test_returns_four_ratios(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        results = pipeline.generate_covers("AI trends", "TestBrand", str(tmp_path))
        assert len(results) == 4
        for ratio in ("16:9", "9:16", "3:4", "1:1"):
            assert ratio in results

    def test_creates_cover_files(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        results = pipeline.generate_covers("topic", "brand", str(tmp_path))
        for path in results.values():
            assert os.path.isfile(path)

    def test_covers_directory_created(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        pipeline.generate_covers("topic", "brand", str(tmp_path))
        assert os.path.isdir(os.path.join(str(tmp_path), "covers"))

    def test_cover_dimensions_match_specs(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        results = pipeline.generate_covers("topic", "brand", str(tmp_path))
        for ratio, path in results.items():
            expected_w, expected_h = COVER_SPECS[ratio]
            with Image.open(path) as img:
                w, h = img.size
            assert w == expected_w, f"{ratio}: expected width {expected_w}, got {w}"
            assert h == expected_h, f"{ratio}: expected height {expected_h}, got {h}"


class TestImagePipelineGenerateBodyImages:
    """generate_body_images produces 4:3 landscape images."""

    def test_default_count_is_four(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        paths = pipeline.generate_body_images("topic", str(tmp_path))
        assert len(paths) == 4

    def test_custom_count(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        paths = pipeline.generate_body_images("topic", str(tmp_path), count=5)
        assert len(paths) == 5

    def test_count_clamped_to_minimum_three(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        paths = pipeline.generate_body_images("topic", str(tmp_path), count=1)
        assert len(paths) == 3

    def test_count_clamped_to_maximum_six(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        paths = pipeline.generate_body_images("topic", str(tmp_path), count=10)
        assert len(paths) == 6

    def test_body_files_created(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        paths = pipeline.generate_body_images("topic", str(tmp_path))
        for p in paths:
            assert os.path.isfile(p)

    def test_body_dimensions_are_4_3(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        paths = pipeline.generate_body_images("topic", str(tmp_path))
        for p in paths:
            with Image.open(p) as img:
                w, h = img.size
            assert (w, h) == BODY_IMAGE_SIZE


class TestImagePipelineGenerateFallbackFrame:
    """generate_fallback_frame produces a single image."""

    def test_returns_string_path(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        path = pipeline.generate_fallback_frame("topic", str(tmp_path))
        assert isinstance(path, str)

    def test_file_exists(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        path = pipeline.generate_fallback_frame("topic", str(tmp_path))
        assert os.path.isfile(path)

    def test_fallback_dimensions(self, tmp_path: Any) -> None:
        pipeline = ImagePipeline()
        path = pipeline.generate_fallback_frame("topic", str(tmp_path))
        with Image.open(path) as img:
            w, h = img.size
        assert (w, h) == BODY_IMAGE_SIZE


# =========================================================================
# ImageValidator.validate_cover tests
# =========================================================================


class TestValidateCover:
    """Cover validation with PIL aspect ratio checking."""

    def test_valid_cover_16x9(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "cover.png"), 1920, 1080)
        assert ImageValidator.validate_cover(path, "16:9") is True

    def test_valid_cover_1x1(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "cover.png"), 1080, 1080)
        assert ImageValidator.validate_cover(path, "1:1") is True

    def test_valid_cover_9x16(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "cover.png"), 1080, 1920)
        assert ImageValidator.validate_cover(path, "9:16") is True

    def test_valid_cover_3x4(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "cover.png"), 1200, 1600)
        assert ImageValidator.validate_cover(path, "3:4") is True

    def test_invalid_ratio_cover(self, tmp_path: Any) -> None:
        # Square image, expected 16:9 → fails
        path = _make_image(str(tmp_path / "cover.png"), 1080, 1080)
        assert ImageValidator.validate_cover(path, "16:9") is False

    def test_nonexistent_file_returns_false(self, tmp_path: Any) -> None:
        assert ImageValidator.validate_cover(str(tmp_path / "nope.png"), "16:9") is False

    def test_unknown_ratio_returns_false(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "cover.png"), 1080, 1080)
        assert ImageValidator.validate_cover(path, "7:5") is False

    def test_near_tolerance_passes(self, tmp_path: Any) -> None:
        # 16:9 ratio = 1.7778, tolerance 2% → [1.7422, 1.8133]
        # 1900/1080 = 1.7593 → within tolerance
        path = _make_image(str(tmp_path / "cover.png"), 1900, 1080)
        assert ImageValidator.validate_cover(path, "16:9") is True

    def test_outside_tolerance_fails(self, tmp_path: Any) -> None:
        # 2100/1080 = 1.944 → far outside 2% tolerance of 1.7778
        path = _make_image(str(tmp_path / "cover.png"), 2100, 1080)
        assert ImageValidator.validate_cover(path, "16:9") is False


# =========================================================================
# ImageValidator.validate_body_image tests
# =========================================================================


class TestValidateBodyImage:
    """Body image validation: 4:3 ratio ±2%, min side ≥ 800px."""

    def test_valid_body_image(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "body.png"), 1600, 1200)
        assert ImageValidator.validate_body_image(path) is True

    def test_min_side_exactly_800(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "body.png"), 1067, 800)
        assert ImageValidator.validate_body_image(path) is True

    def test_min_side_below_800_fails(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "body.png"), 799, 600)
        assert ImageValidator.validate_body_image(path) is False

    def test_wrong_ratio_fails(self, tmp_path: Any) -> None:
        # Square 1000x1000 → ratio 1.0, not 1.333
        path = _make_image(str(tmp_path / "body.png"), 1000, 1000)
        assert ImageValidator.validate_body_image(path) is False

    def test_nonexistent_file_returns_false(self, tmp_path: Any) -> None:
        assert ImageValidator.validate_body_image(str(tmp_path / "nope.png")) is False


# =========================================================================
# ImageValidator.validate_all tests
# =========================================================================


class TestValidateAll:
    """Batch validation across project subdirectories."""

    def test_empty_project_dir(self, tmp_path: Any) -> None:
        results = ImageValidator.validate_all(str(tmp_path))
        assert results == []

    def test_valid_covers_and_body(self, tmp_path: Any) -> None:
        # Create covers
        _make_image(str(tmp_path / "covers" / "cover_16x9.png"), 1920, 1080)
        _make_image(str(tmp_path / "covers" / "cover_1x1.png"), 1080, 1080)
        # Create body images
        _make_image(str(tmp_path / "body" / "body_00.png"), 1600, 1200)
        # Create fallback
        _make_image(str(tmp_path / "fallback" / "fallback_frame.png"), 1600, 1200)

        results = ImageValidator.validate_all(str(tmp_path))
        assert len(results) == 4
        assert all(r["valid"] for r in results)

    def test_invalid_image_detected(self, tmp_path: Any) -> None:
        # Wrong ratio cover
        _make_image(str(tmp_path / "covers" / "cover_16x9.png"), 1080, 1080)
        results = ImageValidator.validate_all(str(tmp_path))
        assert len(results) == 1
        assert results[0]["valid"] is False

    def test_non_image_files_skipped(self, tmp_path: Any) -> None:
        os.makedirs(str(tmp_path / "body"), exist_ok=True)
        (tmp_path / "body" / "notes.txt").write_text("not an image")
        _make_image(str(tmp_path / "body" / "body_00.png"), 1600, 1200)
        results = ImageValidator.validate_all(str(tmp_path))
        assert len(results) == 1


# =========================================================================
# VisionQADegradation tests
# =========================================================================


class TestVisionQADegradation:
    """Pixel luminance degradation fallback."""

    def test_degrade_returns_all_keys(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "test.png"), 100, 100, color=(128, 128, 128))
        result = VisionQADegradation.degrade_to_pixel_luminance(path)
        for key in (
            "path",
            "mean_luminance",
            "min_luminance",
            "max_luminance",
            "std_luminance",
            "degraded",
            "error",
        ):
            assert key in result

    def test_degraded_flag_is_true(self, tmp_path: Any) -> None:
        path = _make_image(str(tmp_path / "test.png"), 100, 100)
        result = VisionQADegradation.degrade_to_pixel_luminance(path)
        assert result["degraded"] is True

    def test_uniform_image_luminance(self, tmp_path: Any) -> None:
        # Uniform gray (128, 128, 128) → grayscale luminance = 128
        path = _make_image(str(tmp_path / "test.png"), 50, 50, color=(128, 128, 128))
        result = VisionQADegradation.degrade_to_pixel_luminance(path)
        assert result["error"] is None
        assert result["mean_luminance"] == 128.0
        assert result["min_luminance"] == 128
        assert result["max_luminance"] == 128
        assert result["std_luminance"] == 0.0

    def test_nonexistent_file_error(self, tmp_path: Any) -> None:
        result = VisionQADegradation.degrade_to_pixel_luminance(str(tmp_path / "nope.png"))
        assert result["degraded"] is True
        assert result["error"] is not None
        assert "not found" in result["error"]

    def test_mixed_image_has_nonzero_std(self, tmp_path: Any) -> None:
        # Create image with two different colors
        img = Image.new("RGB", (100, 100), color=(0, 0, 0))
        # Draw a white rectangle in the top half
        for x in range(100):
            for y in range(50):
                img.putpixel((x, y), (255, 255, 255))
        path = str(tmp_path / "mixed.png")
        img.save(path, "PNG")

        result = VisionQADegradation.degrade_to_pixel_luminance(path)
        assert result["error"] is None
        assert result["std_luminance"] > 0
        assert result["min_luminance"] == 0
        assert result["max_luminance"] == 255



