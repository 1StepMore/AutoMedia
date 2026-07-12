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
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PIL import Image
from structlog import get_logger

if TYPE_CHECKING:
    import httpx

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
# ComfyUI helpers (HTTP API client)
# ---------------------------------------------------------------------------


def _run_comfyui(
    workflow: dict[str, Any],
    output_dir: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8188,
    protocol: str = "http",
    timeout: int = 300,
) -> str:
    """Execute a ComfyUI workflow via its HTTP API.

    Makes a real HTTP POST to the ComfyUI ``/prompt`` endpoint with the
    workflow JSON, polls for completion, and downloads the output image.
    Falls back to PIL placeholder generation when *httpx* is not available
    or the server is unreachable.

    Parameters
    ----------
    workflow:
        ComfyUI workflow JSON payload (node graph).
    output_dir:
        Directory where generated images are stored.
    host:
        ComfyUI server hostname (default ``"127.0.0.1"``).
    port:
        ComfyUI server port (default ``8188``).
    protocol:
        HTTP protocol scheme (default ``"http"``).
    timeout:
        Maximum time in seconds to wait for prompt completion (default ``300``).

    Returns
    -------
    str
        Path to the generated image file.
    """
    output_path = os.path.join(output_dir, workflow.get("filename", "output.png"))
    width = workflow.get("width", 1080)
    height = workflow.get("height", 1080)

    # ---- Attempt real ComfyUI API call via httpx ----
    try:
        import httpx  # noqa: F811
    except ImportError:
        from automedia.core._import_helpers import warn_missing_optional

        warn_missing_optional("httpx", feature="using PIL placeholder fallback")
        _create_placeholder(output_path, width, height)
        return output_path

    base_url = f"{protocol}://{host}:{port}"
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            # a) POST workflow to /prompt
            resp = client.post(f"{base_url}/prompt", json={"prompt": workflow})
            resp.raise_for_status()
            prompt_data = resp.json()
            prompt_id = prompt_data.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"No prompt_id in ComfyUI response: {prompt_data}")

            # b) Poll /history/{prompt_id} until completed
            _poll_comfyui(client, base_url, prompt_id, timeout)

            # c) Get output filename from history
            history_resp = client.get(f"{base_url}/history/{prompt_id}")
            history_resp.raise_for_status()
            history = history_resp.json()
            output_filename = _extract_output_filename(history, prompt_id)

            # d) Download image via /view
            download_resp = client.get(
                f"{base_url}/view",
                params={"filename": output_filename},
            )
            download_resp.raise_for_status()

            # e) Write image to disk
            with open(output_path, "wb") as f:
                f.write(download_resp.content)

            logger.info("ComfyUI generated image → %s", output_path)
            return output_path

    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
        logger.warning("ComfyUI API error (%s) — using PIL fallback", exc)
    except Exception as exc:
        logger.warning("ComfyUI unexpected error (%s) — using PIL fallback", exc)

    # ---- Fallback: PIL placeholder ----
    _create_placeholder(output_path, width, height)
    return output_path


def _poll_comfyui(
    client: httpx.Client,  # noqa: F821  — guarded by TYPE_CHECKING
    base_url: str,
    prompt_id: str,
    timeout: int,
) -> None:
    """Poll the ComfyUI ``/history`` endpoint until the prompt completes.

    Raises
    ------
    TimeoutError
        If the prompt does not complete within *timeout* seconds.
    """
    start = time.monotonic()
    poll_interval = 1.0

    while (time.monotonic() - start) < timeout:
        resp = client.get(f"{base_url}/history/{prompt_id}")
        resp.raise_for_status()
        history = resp.json()
        prompt_entry = history.get(prompt_id, {})
        if prompt_entry.get("status", {}).get("completed") is True:
            return
        time.sleep(poll_interval)

    raise TimeoutError(f"ComfyUI prompt {prompt_id} did not complete within {timeout}s")


def _extract_output_filename(history: dict[str, Any], prompt_id: str) -> str:
    """Extract the first output image filename from a ComfyUI history response."""
    outputs = history.get(prompt_id, {}).get("outputs", {})
    for _node_id, node_output in outputs.items():
        images = node_output.get("images", [])
        if images:
            filename = images[0].get("filename")
            if filename:
                return filename
    raise RuntimeError(f"No output image found in ComfyUI history for prompt {prompt_id}")


def _create_placeholder(output_path: str, width: int, height: int) -> None:
    """Create a minimal PNG placeholder image using PIL."""
    img = Image.new("RGB", (width, height), color=(30, 30, 30))
    img.save(output_path, "PNG")


# ---------------------------------------------------------------------------
# ImagePipeline
# ---------------------------------------------------------------------------


class ImagePipeline:
    """Generates cover images, body images, and fallback frames via ComfyUI.

    Each generation method shells out to ComfyUI (subprocess) and writes
    images into *project_dir*.
    """

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
            workflow = {
                "prompt": f"{topic} — {brand} cover {ratio}",
                "width": w,
                "height": h,
                "filename": filename,
            }
            path = _run_comfyui(workflow, covers_dir)
            results[ratio] = path
            logger.info("Generated cover %s → %s", ratio, path)

        return results

    def generate_body_images(
        self,
        topic: str,
        project_dir: str,
        count: int = 4,
    ) -> list[str]:
        """Generate 4:3 landscape body images.

        Parameters
        ----------
        topic:
            Content topic for the image prompt.
        project_dir:
            Root project directory; images are written to ``body/``.
        count:
            Number of images to generate (clamped to 3–6).

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
            workflow = {
                "prompt": f"{topic} body image {i + 1}",
                "width": w,
                "height": h,
                "filename": filename,
            }
            path = _run_comfyui(workflow, body_dir)
            paths.append(path)

        logger.info("Generated %d body images → %s", count, body_dir)
        return paths

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
            Path to the fallback frame image.
        """
        fallback_dir = os.path.join(project_dir, "fallback")
        os.makedirs(fallback_dir, exist_ok=True)

        w, h = BODY_IMAGE_SIZE  # 4:3 landscape default
        workflow = {
            "prompt": f"{topic} fallback frame",
            "width": w,
            "height": h,
            "filename": "fallback_frame.png",
        }
        path = _run_comfyui(workflow, fallback_dir)
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
