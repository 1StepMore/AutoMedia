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
    _create_placeholder,
    _extract_output_filename,
    _run_comfyui,
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


# =========================================================================
# _run_comfyui helper tests
# =========================================================================


class TestRunComfyui:
    """ComfyUI HTTP API client with PIL fallback."""

    def test_creates_output_file(self, tmp_path: Any) -> None:
        workflow = {"filename": "test_out.png", "width": 200, "height": 150}
        path = _run_comfyui(workflow, str(tmp_path))
        assert os.path.isfile(path)

    def test_output_dimensions_match_workflow(self, tmp_path: Any) -> None:
        workflow = {"filename": "dim_test.png", "width": 320, "height": 240}
        path = _run_comfyui(workflow, str(tmp_path))
        with Image.open(path) as img:
            assert img.size == (320, 240)

    # ------------------------------------------------------------------
    # httpx fallback (import error)
    # ------------------------------------------------------------------

    def test_httpx_not_available_fallback(self, tmp_path: Any) -> None:
        """Fall back to PIL placeholder when httpx is not installed."""
        original_import = builtins.__import__

        def _mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "httpx":
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            workflow = {"filename": "fallback.png", "width": 120, "height": 80}
            path = _run_comfyui(workflow, str(tmp_path))

        assert os.path.isfile(path)
        with Image.open(path) as img:
            assert img.size == (120, 80)

    # ------------------------------------------------------------------
    # HTTP error fallback tests
    # ------------------------------------------------------------------

    def test_connection_error_fallback(self, tmp_path: Any) -> None:
        """Fall back to PIL placeholder when ComfyUI server is unreachable."""
        mock_client = MagicMock()
        mock_client.post.side_effect = ConnectionError("Connection refused")

        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            workflow = {"filename": "conn_err.png", "width": 64, "height": 64}
            path = _run_comfyui(workflow, str(tmp_path))

        assert os.path.isfile(path)
        with Image.open(path) as img:
            assert img.size == (64, 64)

    def test_timeout_error_fallback(self, tmp_path: Any) -> None:
        """Fall back to PIL placeholder when ComfyUI request times out."""
        mock_client = MagicMock()
        mock_client.post.side_effect = TimeoutError("Request timed out")

        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            workflow = {"filename": "timeout.png", "width": 80, "height": 80}
            path = _run_comfyui(workflow, str(tmp_path))

        assert os.path.isfile(path)
        with Image.open(path) as img:
            assert img.size == (80, 80)

    def test_http_error_status_fallback(self, tmp_path: Any) -> None:
        """Fall back to PIL placeholder on HTTP 5xx response."""
        mock_client = MagicMock()
        post_resp = MagicMock()
        post_resp.raise_for_status.side_effect = Exception("HTTP 500")
        mock_client.post.return_value = post_resp

        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            workflow = {"filename": "http_err.png", "width": 100, "height": 100}
            path = _run_comfyui(workflow, str(tmp_path))

        assert os.path.isfile(path)

    def test_malformed_response_fallback(self, tmp_path: Any) -> None:
        """Fall back to PIL placeholder when response has no prompt_id."""
        mock_client = MagicMock()
        post_resp = MagicMock()
        post_resp.json.return_value = {"status": "error"}  # no prompt_id
        mock_client.post.return_value = post_resp

        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            workflow = {"filename": "bad_resp.png", "width": 100, "height": 100}
            path = _run_comfyui(workflow, str(tmp_path))

        assert os.path.isfile(path)

    # ------------------------------------------------------------------
    # Successful HTTP flow
    # ------------------------------------------------------------------

    def test_successful_http_flow(self, tmp_path: Any) -> None:
        """Make successful ComfyUI API call and download image."""
        mock_client = MagicMock()

        # POST /prompt → success
        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "test-prompt-abc"}
        mock_client.post.return_value = post_resp

        # GET responses (history + download)
        history_resp = MagicMock()
        history_resp.json.return_value = {
            "test-prompt-abc": {
                "status": {"completed": True},
                "outputs": {
                    "3": {"images": [{"filename": "comfy_output.png"}]},
                },
            },
        }

        download_resp = MagicMock()
        download_resp.content = b"fake-image-content"

        # 1st GET = _poll_comfyui, 2nd GET = history re-fetch, 3rd GET = download
        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            workflow = {"filename": "real_out.png", "width": 512, "height": 512}
            path = _run_comfyui(workflow, str(tmp_path))

        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == b"fake-image-content"

    # ------------------------------------------------------------------
    # Polling timeout
    # ------------------------------------------------------------------

    def test_polling_timeout_fallback(self, tmp_path: Any) -> None:
        """Fall back to PIL placeholder when polling exceeds timeout."""
        mock_client = MagicMock()

        # POST succeeds
        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "slow-prompt"}
        mock_client.post.return_value = post_resp

        # GET never returns completed=True → triggers timeout
        pending_resp = MagicMock()
        pending_resp.json.return_value = {
            "slow-prompt": {"status": {"completed": False}},
        }
        mock_client.get.return_value = pending_resp

        with (
            patch("httpx.Client") as mock_cls,
            patch("time.monotonic") as mock_time,
        ):
            mock_cls.return_value.__enter__.return_value = mock_client
            # Simulate time advancing beyond 1s timeout
            mock_time.side_effect = [0.0, 0.1, 2.0]

            workflow = {"filename": "slow_out.png", "width": 50, "height": 50}
            path = _run_comfyui(workflow, str(tmp_path), timeout=1)

        assert os.path.isfile(path)
        with Image.open(path) as img:
            assert img.size == (50, 50)

    # ------------------------------------------------------------------
    # Custom parameters
    # ------------------------------------------------------------------

    def test_custom_host_port_protocol(self, tmp_path: Any) -> None:
        """Pass custom host, port, protocol parameters."""
        mock_client = MagicMock()

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "custom-prompt"}
        mock_client.post.return_value = post_resp

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "custom-prompt": {
                "status": {"completed": True},
                "outputs": {"1": {"images": [{"filename": "out.png"}]}},
            },
        }
        download_resp = MagicMock()
        download_resp.content = b"data"
        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            path = _run_comfyui(
                {"filename": "custom.png"},
                str(tmp_path),
                host="192.168.1.100",
                port=8288,
                protocol="https",
            )

        assert os.path.isfile(path)
        # Verify the correct URL was used
        mock_client.post.assert_called_once()
        call_url = mock_client.post.call_args[0][0]
        assert "https://192.168.1.100:8288/prompt" in call_url


# =========================================================================
# _create_placeholder tests
# =========================================================================


class TestCreatePlaceholder:
    """PIL placeholder image creation."""

    def test_creates_png_file(self, tmp_path: Any) -> None:
        path = str(tmp_path / "placeholder.png")
        _create_placeholder(path, 100, 200)
        assert os.path.isfile(path)

    def test_correct_dimensions(self, tmp_path: Any) -> None:
        path = str(tmp_path / "dim.png")
        _create_placeholder(path, 320, 240)
        with Image.open(path) as img:
            assert img.size == (320, 240)

    def test_overwrites_existing_file(self, tmp_path: Any) -> None:
        path = str(tmp_path / "overwrite.png")
        _create_placeholder(path, 10, 10)
        _create_placeholder(path, 50, 50)
        with Image.open(path) as img:
            assert img.size == (50, 50)


# =========================================================================
# _extract_output_filename tests
# =========================================================================


class TestExtractOutputFilename:
    """Extract first image filename from ComfyUI history response."""

    def test_extracts_first_image(self) -> None:
        history = {
            "prompt-1": {
                "outputs": {
                    "5": {"images": [{"filename": "result.png"}]},
                },
            },
        }
        assert _extract_output_filename(history, "prompt-1") == "result.png"

    def test_skips_nodes_without_images(self) -> None:
        history = {
            "prompt-1": {
                "outputs": {
                    "1": {"images": []},
                    "2": {"images": [{"filename": "final.png"}]},
                },
            },
        }
        assert _extract_output_filename(history, "prompt-1") == "final.png"

    def test_raises_on_missing_outputs(self) -> None:
        history = {"prompt-1": {"status": {"completed": True}}}
        with pytest.raises(RuntimeError, match="No output image found"):
            _extract_output_filename(history, "prompt-1")

    def test_raises_on_missing_prompt(self) -> None:
        history: dict[str, Any] = {}
        with pytest.raises(RuntimeError, match="No output image found"):
            _extract_output_filename(history, "nonexistent")
