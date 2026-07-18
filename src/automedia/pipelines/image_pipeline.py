"""Image pipeline — ComfyUI cover generation, PIL validation, Vision QA degradation.

Provides three main classes:
    - :class:`ImagePipeline` — generates cover images, body images, and fallback
      frames via ComfyUI HTTP API calls.
    - :class:`ImageValidator` — validates image dimensions and aspect ratios using PIL.
    - :class:`VisionQADegradation` — degrades to pixel-luminance analysis when the
      Vision API is rate-limited.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast

from PIL import Image
from structlog import get_logger

from automedia.core.llm_client import LLMError, llm_complete
from automedia.engines import resolve_engine
from automedia.engines.base import BaseImageEngine
from automedia.engines.errors import EngineExecutionError
from automedia.prompts import load_prompt

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COVER_SPECS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "3:4": (1200, 1600),
    "1:1": (1080, 1080),
}

BODY_IMAGE_SIZE: tuple[int, int] = (1600, 1200)  # 4:3 landscape
BODY_IMAGE_MIN_SIDE: int = 800
ASPECT_RATIO_TOLERANCE: float = 0.02  # ±2%


# ---------------------------------------------------------------------------
# Image prompt generation (LLM-powered with naive fallback)
# ---------------------------------------------------------------------------


def _generate_image_prompt(
    topic: str,
    brand: str,
    image_index: int,
    platform: str = "",
) -> str:
    """Generate a detailed SD/ComfyUI image prompt via LLM.

    Uses :func:`load_prompt` to render a Jinja2 template for the user message,
    then calls :func:`llm_complete` with a system prompt tailored for SD
    prompt generation.

    Falls back to the naive ``f"{topic} body image {image_index + 1}"``
    template on any failure (LLM error, empty response, etc.).

    Parameters
    ----------
    topic:
        Content topic used as the image prompt seed.
    brand:
        Brand identifier for style context.
    image_index:
        Zero-based index of the body image (used for variation).

    Returns
    -------
    str
        The generated image prompt (LLM result or fallback).
    """
    try:
        user_message = load_prompt(
            "image_prompt",
            topic=topic,
            brand=brand,
            image_index=image_index,
            platform=platform,
        )
        result: str = llm_complete(
            user_message,
            system_prompt=(
                "You are a professional Stable Diffusion prompt engineer. "
                "Generate detailed, high-quality comma-separated image prompts "
                "optimized for text-to-image generation. "
                "Return ONLY the prompt text — no explanations."
            ),
        )
        if result.strip():
            return result.strip()
        logger.warning(
            "LLM returned empty image prompt — using fallback",
            topic=topic,
            image_index=image_index,
        )
    except (LLMError, Exception) as exc:
        logger.warning(
            "LLM image prompt generation failed (%s) — using fallback",
            exc,
            topic=topic,
            image_index=image_index,
        )

    return f"{topic} body image {image_index + 1}"


# ---------------------------------------------------------------------------
# ImagePipeline
# ---------------------------------------------------------------------------


class ImagePipeline:
    """Generates cover images, body images, and fallback frames via ComfyUI.

    Each generation method delegates to the configured image engine
    (resolved via :func:`~automedia.engines.resolve_engine`) and writes
    images into *project_dir*.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialise the pipeline with an optional config dict.

        Args:
            config: Full pipeline configuration dictionary. When ``None``,
                the engine is resolved using built-in defaults.
        """
        self._config = config
        self._image_engine: BaseImageEngine | None = None

    def _get_image_engine(self) -> BaseImageEngine:
        """Lazy-load and cache the image engine from config."""
        if self._image_engine is None:
            self._image_engine = cast(
                BaseImageEngine,
                resolve_engine("image", self._config),
            )
        return self._image_engine

    def generate_covers(
        self,
        topic: str,
        brand: str,
        project_dir: str,
    ) -> dict[str, str]:
        """Generate 4 cover images in standard aspect ratios.

        Parameters
        ----------
        topic:
            Content topic used as the image prompt seed.
        brand:
            Brand identifier for watermark / style.
        project_dir:
            Root directory for the project; images are written to a
            ``covers/`` subdirectory.

        Returns
        -------
        dict[str, str]
            Mapping of ratio label (e.g. ``"16:9"``) to file path.
        """
        covers_dir = os.path.join(project_dir, "covers")
        os.makedirs(covers_dir, exist_ok=True)

        results: dict[str, str] = {}
        for ratio, (w, h) in COVER_SPECS.items():
            safe_ratio = ratio.replace(":", "x")
            filename = f"cover_{safe_ratio}.png"
            output_path = os.path.join(covers_dir, filename)
            try:
                path = self._get_image_engine().generate(
                    f"{topic} — {brand} cover {ratio}",
                    w,
                    h,
                    output_path,
                )
            except EngineExecutionError as exc:
                logger.warning(
                    "Cover generation failed for %s: %s — continuing without images",
                    ratio,
                    exc,
                )
                continue
            results[ratio] = path
            logger.info("Generated cover %s → %s", ratio, path)

        return results

    def generate_body_images(
        self,
        topic: str,
        project_dir: str,
        count: int = 4,
        brand: str = "",
    ) -> list[str]:
        """Generate 4:3 landscape body images with LLM-enhanced prompts.

        Parameters
        ----------
        topic:
            Content topic for the image prompt.
        project_dir:
            Root project directory; images are written to ``body/``.
        count:
            Number of images to generate (clamped to 3–6).
        brand:
            Brand identifier for prompt context (optional).

        Returns
        -------
        list[str]
            Paths to generated body images.
        """
        count = max(3, min(6, count))
        body_dir = os.path.join(project_dir, "body")
        os.makedirs(body_dir, exist_ok=True)

        w, h = BODY_IMAGE_SIZE
        paths: list[str] = []
        for i in range(count):
            filename = f"body_{i:02d}.png"
            output_path = os.path.join(body_dir, filename)
            prompt = _generate_image_prompt(topic, brand, i)
            try:
                path = self._get_image_engine().generate(prompt, w, h, output_path)
            except EngineExecutionError as exc:
                logger.warning(
                    "Body image %d generation failed: %s — continuing without images",
                    i,
                    exc,
                )
                break
            paths.append(path)

        logger.info("Generated %d body images → %s", count, body_dir)
        return paths

    def generate_single_cover(
        self,
        topic: str,
        brand: str,
        project_dir: str,
        ratio: str = "16:9",
    ) -> str:
        """Generate a single cover image in the specified aspect ratio.

        Writes the cover to ``02_images/cover/cover.png`` within
        *project_dir*.

        Parameters
        ----------
        topic:
            Content topic used as the image prompt seed.
        brand:
            Brand identifier for watermark / style.
        project_dir:
            Root directory for the project.
        ratio:
            Aspect ratio label, one of ``"16:9"``, ``"9:16"``,
            ``"3:4"``, ``"1:1"`` (default ``"16:9"``).

        Returns
        -------
        str
            Path to the generated cover image, or ``""`` on failure.
        """
        spec = COVER_SPECS.get(ratio, (1920, 1080))
        cover_dir = os.path.join(project_dir, "02_images", "cover")
        os.makedirs(cover_dir, exist_ok=True)

        output_path = os.path.join(cover_dir, "cover.png")
        try:
            path = self._get_image_engine().generate(
                f"{topic} — {brand} cover {ratio}",
                spec[0],
                spec[1],
                output_path,
            )
        except EngineExecutionError as exc:
            logger.warning(
                "Single cover generation failed: %s — continuing without images",
                exc,
            )
            return ""

        logger.info("Generated single cover → %s", path)
        return path

    def generate_fallback_frame(
        self,
        topic: str,
        project_dir: str,
    ) -> str:
        """Generate a single fallback frame for video pipelines.

        Parameters
        ----------
        topic:
            Content topic.
        project_dir:
            Root project directory; frame is written to ``fallback/``.

        Returns
        -------
        str
            Path to the fallback frame image, or ``""`` on failure.
        """
        fallback_dir = os.path.join(project_dir, "fallback")
        os.makedirs(fallback_dir, exist_ok=True)

        w, h = BODY_IMAGE_SIZE  # 4:3 landscape default
        output_path = os.path.join(fallback_dir, "fallback_frame.png")
        try:
            path = self._get_image_engine().generate(
                f"{topic} fallback frame",
                w,
                h,
                output_path,
            )
        except EngineExecutionError as exc:
            logger.warning(
                "Fallback frame generation failed: %s — continuing without images",
                exc,
            )
            return ""

        logger.info("Generated fallback frame → %s", path)
        return path


# ---------------------------------------------------------------------------
# ImageValidator
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of a single image validation."""

    path: str
    valid: bool
    reason: str = ""


class ImageValidator:
    """Validates image dimensions and aspect ratios using PIL.

    All ratio checks use a tolerance of ±2% (``ASPECT_RATIO_TOLERANCE``).
    """

    # ------------------------------------------------------------------
    # Single-image validators
    # ------------------------------------------------------------------

    @staticmethod
    def validate_cover(image_path: str, expected_ratio: str) -> bool:
        """Validate that *image_path* matches *expected_ratio* within ±2%.

        Parameters
        ----------
        image_path:
            Path to the image file.
        expected_ratio:
            Ratio label such as ``"16:9"``, ``"9:16"``, ``"3:4"``, ``"1:1"``.

        Returns
        -------
        bool
            ``True`` if the image aspect ratio is within tolerance.
        """
        if not os.path.isfile(image_path):
            return False

        spec = COVER_SPECS.get(expected_ratio)
        if spec is None:
            return False

        expected_w, expected_h = spec
        expected_ratio_val = expected_w / expected_h

        with Image.open(image_path) as img:
            w, h = img.size

        if h == 0:
            return False

        actual_ratio = w / h
        return abs(actual_ratio - expected_ratio_val) / expected_ratio_val <= ASPECT_RATIO_TOLERANCE

    @staticmethod
    def validate_body_image(image_path: str) -> bool:
        """Validate a body image: 4:3 ratio ±2%, minimum side ≥ 800 px.

        Parameters
        ----------
        image_path:
            Path to the image file.

        Returns
        -------
        bool
            ``True`` if the image passes both checks.
        """
        if not os.path.isfile(image_path):
            return False

        expected_ratio = BODY_IMAGE_SIZE[0] / BODY_IMAGE_SIZE[1]  # 4:3 ≈ 1.333

        with Image.open(image_path) as img:
            w, h = img.size

        if h == 0 or w == 0:
            return False

        # Minimum side check
        if min(w, h) < BODY_IMAGE_MIN_SIDE:
            return False

        # Ratio check
        actual_ratio = w / h
        return abs(actual_ratio - expected_ratio) / expected_ratio <= ASPECT_RATIO_TOLERANCE

    # ------------------------------------------------------------------
    # Batch validator
    # ------------------------------------------------------------------

    @staticmethod
    def validate_all(project_dir: str) -> list[dict[str, Any]]:
        """Validate all images found under *project_dir*.

        Scans ``covers/``, ``body/``, and ``fallback/`` subdirectories.

        Returns
        -------
        list[dict]
            Each dict has keys ``path``, ``valid``, ``reason``.
        """
        results: list[dict[str, Any]] = []
        image_extensions = {".png", ".jpg", ".jpeg", ".webp"}

        for subdir, validator_fn, _extra_args in [
            ("covers", ImageValidator._validate_cover_file, None),
            ("body", ImageValidator._validate_body_file, None),
            ("fallback", ImageValidator._validate_body_file, None),
        ]:
            dir_path = os.path.join(project_dir, subdir)
            if not os.path.isdir(dir_path):
                continue
            for fname in sorted(os.listdir(dir_path)):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in image_extensions:
                    continue
                fpath = os.path.join(dir_path, fname)
                result = validator_fn(fpath, subdir)
                results.append(result)

        return results

    @staticmethod
    def _validate_cover_file(fpath: str, subdir: str) -> dict[str, Any]:
        """Validate a single cover image file, inferring ratio from filename."""
        fname = os.path.basename(fpath)
        # Try to infer ratio from filename like cover_16x9.png
        ratio_map = {
            "16x9": "16:9",
            "9x16": "9:16",
            "3x4": "3:4",
            "1x1": "1:1",
        }
        expected_ratio = "16:9"  # default
        for pattern, ratio in ratio_map.items():
            if pattern in fname:
                expected_ratio = ratio
                break

        valid = ImageValidator.validate_cover(fpath, expected_ratio)
        return {
            "path": fpath,
            "valid": valid,
            "reason": "" if valid else f"cover ratio mismatch for {expected_ratio}",
        }

    @staticmethod
    def _validate_body_file(fpath: str, subdir: str) -> dict[str, Any]:
        """Validate a body/fallback image file."""
        valid = ImageValidator.validate_body_image(fpath)
        return {
            "path": fpath,
            "valid": valid,
            "reason": "" if valid else "body image: ratio or min-side check failed",
        }


# ---------------------------------------------------------------------------
# VisionQADegradation
# ---------------------------------------------------------------------------


class VisionQADegradation:
    """Degrades to pixel-luminance analysis when the Vision API is rate-limited.

    When the external Vision API cannot be called (HTTP 429 / quota exceeded),
    this class provides a local fallback that computes simple luminance statistics
    from the image pixels.
    """

    @staticmethod
    def degrade_to_pixel_luminance(image_path: str) -> dict[str, Any]:
        """Compute pixel-level luminance statistics for *image_path*.

        This is the degradation path when the Vision API is unavailable.

        Parameters
        ----------
        image_path:
            Path to the image file.

        Returns
        -------
        dict
            Keys:
            - ``path``: str — the image path
            - ``mean_luminance``: float — average luminance (0–255)
            - ``min_luminance``: int — minimum pixel luminance
            - ``max_luminance``: int — maximum pixel luminance
            - ``std_luminance``: float — standard deviation of luminance
            - ``degraded``: bool — always ``True`` (indicates degradation)
            - ``error``: str | None — error message if computation failed
        """
        base_result: dict[str, Any] = {
            "path": image_path,
            "mean_luminance": 0.0,
            "min_luminance": 0,
            "max_luminance": 0,
            "std_luminance": 0.0,
            "degraded": True,
            "error": None,
        }

        if not os.path.isfile(image_path):
            base_result["error"] = f"file not found: {image_path}"
            return base_result

        try:
            with Image.open(image_path) as img:
                # Convert to grayscale for luminance analysis
                gray = img.convert("L")
                pixels = list(gray.tobytes())

            if not pixels:
                base_result["error"] = "empty image"
                return base_result

            n = len(pixels)
            mean = sum(pixels) / n
            min_val = min(pixels)
            max_val = max(pixels)
            variance = sum((p - mean) ** 2 for p in pixels) / n
            std_val = variance**0.5

            base_result["mean_luminance"] = round(mean, 2)
            base_result["min_luminance"] = min_val
            base_result["max_luminance"] = max_val
            base_result["std_luminance"] = round(std_val, 2)

        except Exception as exc:
            base_result["error"] = str(exc)

        return base_result
