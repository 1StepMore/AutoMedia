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
from typing import TYPE_CHECKING, Any, cast

from structlog import get_logger

if TYPE_CHECKING:
    from PIL.ImageDraw import ImageDraw
    from PIL.ImageFont import FreeTypeFont

    from automedia.engines.base import BaseImageEngine

from automedia.core.layout import BODY_IMAGES, COVER, FALLBACK_IMAGES, IMAGES
from automedia.core.llm_client import LLMError, llm_complete

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

#: CJK-capable fonts for the deterministic text panel, most common first.
#: ``load_default()`` cannot draw Chinese at all, so a missing font is reported
#: rather than silently producing tofu boxes.
_PANEL_FONT_CANDIDATES: tuple[str, ...] = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)

#: Directories scanned for a CJK font when the fixed list misses.  Slim Linux
#: images (the CI runner included) ship CJK fonts under distribution-specific
#: names, so a name list alone is not enough — and a silently missing font
#: means no scene panel at all.
_PANEL_FONT_DIRS: tuple[str, ...] = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
)

#: Filename fragments that identify a CJK-capable font family.
_CJK_FONT_HINTS: tuple[str, ...] = (
    "notosanscjk",
    "notosanssc",
    "notoserifcjk",
    "sourcehansans",
    "sourcehanserif",
    "wqy",
    "droidsansfallback",
    "arphic",
    "uming",
    "ukai",
    "simhei",
    "msyh",
    "pingfang",
)

_PANEL_BG: tuple[int, int, int] = (17, 24, 39)
_PANEL_FG: tuple[int, int, int] = (243, 244, 246)
_PANEL_MUTED: tuple[int, int, int] = (148, 163, 184)
_PANEL_ACCENT: tuple[int, int, int] = (56, 189, 248)
ASPECT_RATIO_TOLERANCE: float = 0.02  # ±2%


# ---------------------------------------------------------------------------
# Image prompt generation (LLM-powered with naive fallback)
# ---------------------------------------------------------------------------


def _generate_image_prompt(
    topic: str,
    brand: str,
    image_index: int,
    platform: str = "",
    scene_text: str = "",
) -> str:
    """Generate a detailed SD/ComfyUI image prompt via LLM.

    Uses :func:`load_prompt` to render a Jinja2 template for the user message,
    then calls :func:`llm_complete` with a system prompt tailored for SD
    prompt generation.

    ``scene_text`` pins the picture to one narration beat.  Without it every
    scene of a video shares one topic-level prompt and differs only by
    ``image_index`` — six variations of the same idea, which is exactly what
    #377 complained about (related-looking, scene-irrelevant frames).

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
    platform:
        Target platform, when the caller knows it.
    scene_text:
        Narration of the scene this image illustrates.  Optional; when given
        the prompt must depict *this* beat, not the topic in general.

    Returns
    -------
    str
        The generated image prompt (LLM result or fallback).
    """
    try:
        from automedia.prompts import load_prompt

        user_message = load_prompt(
            "image_prompt",
            topic=topic,
            brand=brand,
            image_index=image_index,
            platform=platform,
        )
        if scene_text.strip():
            # Render what this sentence *shows*, not what the topic is about.
            user_message += (
                "\n\nThe image illustrates this exact narration line (translate the "
                "visual content into English, do not translate the words into the "
                "picture):\n"
                f"{scene_text.strip()}\n"
                "Depict only what this line shows. No text, no captions, no watermark."
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
        self._image_chain: list[BaseImageEngine] | None = None

    def _image_engine_chain(self) -> list[BaseImageEngine]:
        """Return the ordered, available image engine chain (cached).

        The chain comes from ``config["engines"]["image"]`` (``default`` +
        ``fallback``).  Resolution never raises: unavailable or misconfigured
        engines are skipped, and an empty list means "no image possible".
        """
        from automedia.engines import resolve_engine_chain

        if self._image_chain is None:
            try:
                resolved = resolve_engine_chain("image", self._config)
            except Exception:
                logger.warning("Image engine chain resolution failed")
                resolved = []
            self._image_chain = [cast("BaseImageEngine", engine) for engine in resolved]
        return self._image_chain

    def _get_image_engine(self) -> BaseImageEngine:
        """Lazy-load and cache the first available image engine.

        Raises:
            EngineUnavailableError: When no engine in the chain is available.
        """
        from automedia.engines.errors import EngineUnavailableError

        if self._image_engine is None:
            chain = self._image_engine_chain()
            if not chain:
                raise EngineUnavailableError(
                    engine_name="image",
                    reason="no image engine available",
                    install_hint=(
                        "Configure engines.image (comfyui or local) and install its dependencies."
                    ),
                )
            self._image_engine = chain[0]
        return self._image_engine

    def _generate_with_chain(
        self,
        prompt: str,
        width: int,
        height: int,
        output_path: str,
    ) -> str:
        """Generate one image, falling through the engine chain on failure.

        Raises the last engine error when every engine fails, or
        :class:`EngineUnavailableError` when the chain is empty.
        """
        from automedia.engines.errors import EngineExecutionError, EngineUnavailableError

        chain = self._image_engine_chain()
        if not chain:
            raise EngineUnavailableError(
                engine_name="image",
                reason="no image engine available",
                install_hint=(
                    "Configure engines.image (comfyui or local) and install its dependencies."
                ),
            )

        last_exc: Exception | None = None
        for engine in chain:
            try:
                return engine.generate(prompt, width, height, output_path)
            except (EngineExecutionError, EngineUnavailableError) as exc:
                logger.warning(
                    "Image engine %s failed for %s: %s — trying next engine",
                    getattr(engine, "engine_name", engine),
                    output_path,
                    exc,
                )
                last_exc = exc
            except Exception as exc:
                logger.warning(
                    "Image engine %s raised unexpectedly for %s: %s — trying next engine",
                    getattr(engine, "engine_name", engine),
                    output_path,
                    exc,
                )
                last_exc = exc

        if last_exc is not None:
            raise last_exc
        raise EngineUnavailableError(
            engine_name="image",
            reason="no image engine available",
            install_hint="Configure engines.image (comfyui or local) and install its dependencies.",
        )

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
        from automedia.engines.errors import EngineExecutionError

        covers_dir = os.path.join(project_dir, "covers")
        os.makedirs(covers_dir, exist_ok=True)

        results: dict[str, str] = {}
        for ratio, (w, h) in COVER_SPECS.items():
            safe_ratio = ratio.replace(":", "x")
            filename = f"cover_{safe_ratio}.png"
            output_path = os.path.join(covers_dir, filename)
            try:
                path = self._generate_with_chain(
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
        from automedia.engines.errors import EngineExecutionError

        count = max(3, min(6, count))
        body_dir = os.path.join(project_dir, IMAGES, "body")
        os.makedirs(body_dir, exist_ok=True)

        w, h = BODY_IMAGE_SIZE
        paths: list[str] = []
        for i in range(count):
            filename = f"body_{i:02d}.png"
            output_path = os.path.join(body_dir, filename)
            prompt = _generate_image_prompt(topic, brand, i)
            try:
                path = self._generate_with_chain(prompt, w, h, output_path)
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
        from automedia.engines.errors import EngineExecutionError

        spec = COVER_SPECS.get(ratio, (1920, 1080))
        cover_dir = os.path.join(project_dir, IMAGES, "cover")
        os.makedirs(cover_dir, exist_ok=True)

        output_path = os.path.join(cover_dir, "cover.png")
        try:
            path = self._generate_with_chain(
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
        *,
        size: tuple[int, int] | None = None,
    ) -> str:
        """Generate a single fallback frame for video pipelines.

        Tries the image engine with a prompt that is actually a picture
        description, then falls back to a deterministic text panel (#377).
        The old prompt — ``f"{topic} fallback frame"`` — was passed straight to
        an SD model: for a Chinese topic it reads as random tokens, which is how
        watermark-bearing stock photos of bedrooms ended up in a video about
        content scheduling.

        Parameters
        ----------
        topic:
            Content topic (also rendered as the panel heading).
        project_dir:
            Root project directory; frame is written to ``fallback/``.
        size:
            Target ``(width, height)``; defaults to :data:`BODY_IMAGE_SIZE`.

        Returns
        -------
        str
            Path to the fallback frame image, or ``""`` on failure.
        """
        fallback_dir = os.path.join(project_dir, IMAGES, "fallback")
        os.makedirs(fallback_dir, exist_ok=True)

        w, h = size or BODY_IMAGE_SIZE
        output_path = os.path.join(fallback_dir, "fallback_frame.png")
        try:
            path = self._generate_with_chain(
                _generate_image_prompt(topic, "", 0),
                w,
                h,
                output_path,
            )
        except Exception as exc:
            logger.warning(
                "Fallback frame generation failed: %s — rendering a text panel instead", exc
            )
            return self.render_text_panel(topic, w, h, output_path, heading=topic)

        logger.info("Generated fallback frame → %s", path)
        return path

    # ------------------------------------------------------------------
    # Per-scene assets (#377)
    # ------------------------------------------------------------------

    def generate_scene_image(
        self,
        scene_text: str,
        width: int,
        height: int,
        output_path: str,
        *,
        topic: str = "",
        brand: str = "",
        index: int = 0,
    ) -> str:
        """Generate one real image for a scene; raise when no engine can.

        The prompt comes from :func:`_generate_image_prompt` (the same
        LLM-backed builder the cover/body images use), anchored on
        *scene_text*: a Chinese sentence handed verbatim to an SD model is
        noise (how ``"{topic} fallback frame"`` produced bedrooms and luggage
        racks for a video about scheduling), but a topic-only prompt yields six
        interchangeable frames.  The scene line goes through the LLM so the
        picture depicts this beat.
        """
        prompt = _generate_image_prompt(
            topic or scene_text,
            brand,
            index,
            scene_text=scene_text,
        )
        logger.info("Generating scene image (%sx%s): %s", width, height, prompt[:80])
        return self._generate_with_chain(prompt, width, height, output_path)

    def render_text_panel(
        self,
        text: str,
        width: int,
        height: int,
        output_path: str,
        *,
        heading: str = "",
        index: int = 0,
    ) -> str:
        """Render *text* onto a deterministic panel image (#377).

        No diffusion model, no stock photo, no third-party watermark: the same
        input always yields the same picture, and the words on screen are the
        words in the narration.  Returns ``""`` when Pillow or a CJK font is
        missing — the caller then keeps whatever frame it already had.
        """
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            logger.warning("Pillow not installed — cannot render a text panel")
            return ""

        font = self._load_panel_font(max(24, width // 20))
        if font is None:
            logger.warning("No CJK font found — cannot render a readable text panel")
            return ""

        image = Image.new("RGB", (width, height), _PANEL_BG)
        draw = ImageDraw.Draw(image)
        margin = max(40, width // 18)

        # Accent bar + heading (topic or scene label) keep panels distinguishable.
        draw.rectangle([margin, margin, margin + 8, margin + 96], fill=_PANEL_ACCENT)
        heading_font = self._load_panel_font(max(20, width // 34))
        if heading:
            draw.text((margin + 28, margin + 6), heading, font=heading_font, fill=_PANEL_MUTED)

        body_font, lines = self._fit_panel_text(
            draw, text, body_font_size=int(font.size), panel_width=width
        )
        if body_font is None:  # pragma: no cover - font was loaded above
            return ""
        line_height = int(body_font.size * 1.5)
        block_height = line_height * len(lines)
        y = max(margin + 120, (height - block_height) // 2)
        for line in lines:
            draw.text((margin + 28, y), line, font=body_font, fill=_PANEL_FG)
            y += line_height

        if index:
            draw.text(
                (margin + 28, height - margin - 24),
                f"{index:02d}",
                font=heading_font,
                fill=_PANEL_MUTED,
            )

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        image.save(output_path)
        logger.info("Rendered text panel → %s", output_path)
        return os.path.abspath(output_path)

    @staticmethod
    def find_cjk_font() -> str | None:
        """Return a CJK-capable font file, or ``None`` when the host has none.

        Checks the fixed name list first, then walks the standard font
        directories for a filename that looks like a CJK family.  A slim Linux
        image (the CI runner is one) has no ``NotoSansCJK-Regular.ttc`` but may
        ship the font under a different name, and a missing font silently costs
        every scene its panel.
        """
        for candidate in _PANEL_FONT_CANDIDATES:
            if os.path.isfile(candidate):
                return candidate

        for directory in _PANEL_FONT_DIRS:
            if not os.path.isdir(directory):
                continue
            for root, _dirs, files in os.walk(directory):
                for filename in files:
                    lowered = filename.lower()
                    if not lowered.endswith((".ttf", ".ttc", ".otf")):
                        continue
                    if any(hint in lowered for hint in _CJK_FONT_HINTS):
                        return os.path.join(root, filename)
        return None

    @staticmethod
    def _load_panel_font(size: int) -> FreeTypeFont | None:
        """Load the first available CJK font at *size*; ``None`` when none exist."""
        from PIL import ImageFont

        font_path = ImagePipeline.find_cjk_font()
        if font_path is None:
            return None
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:  # pragma: no cover - corrupt/unreadable font
            return None

    def _fit_panel_text(
        self,
        draw: ImageDraw,
        text: str,
        *,
        body_font_size: int,
        panel_width: int,
    ) -> tuple[FreeTypeFont | None, list[str]]:
        """Wrap *text* to the panel width, shrinking the font until it fits."""
        max_width = panel_width - 2 * max(40, panel_width // 18) - 28
        max_lines = 6
        size = body_font_size
        while size >= 20:
            font = self._load_panel_font(size)
            if font is None:  # pragma: no cover - guarded by the caller
                break
            lines = self._wrap_by_pixels(draw, text, font, max_width)
            if len(lines) <= max_lines:
                return font, lines
            size = int(size * 0.85)
        fallback_font = self._load_panel_font(20)
        if fallback_font is None:  # pragma: no cover - guarded by the caller
            return None, []
        return fallback_font, self._wrap_by_pixels(draw, text, fallback_font, max_width)[:max_lines]

    @staticmethod
    def _wrap_by_pixels(
        draw: ImageDraw, text: str, font: FreeTypeFont, max_width: float
    ) -> list[str]:
        """Greedy character wrap — correct for CJK, acceptable for Latin."""
        lines: list[str] = []
        current = ""
        for char in text.replace("\r", ""):
            if char == "\n":
                lines.append(current)
                current = ""
                continue
            candidate = current + char
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = char
        if current:
            lines.append(current)
        return [line for line in lines if line.strip()]


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
        from PIL import Image

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

        from PIL import Image

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

        Scans ``02_images/cover/``, ``body/``, and ``fallback/`` subdirectories.

        Returns
        -------
        list[dict]
            Each dict has keys ``path``, ``valid``, ``reason``.
        """
        results: list[dict[str, Any]] = []
        image_extensions = {".png", ".jpg", ".jpeg", ".webp"}

        for subdir, validator_fn, _extra_args in [
            (COVER, ImageValidator._validate_cover_file, None),
            (BODY_IMAGES, ImageValidator._validate_body_file, None),
            (FALLBACK_IMAGES, ImageValidator._validate_body_file, None),
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
            from PIL import Image

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
