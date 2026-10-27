"""Local Pillow image engine — deterministic offline fallback art.

Provides:
    - :class:`LocalImageEngine` — a :class:`BaseImageEngine` implementation
      that renders a fully offline, deterministic image: a vertical gradient
      seeded by a hash of ``(prompt, index)``, a soft radial vignette, two to
      three translucent geometric accents, and the prompt's first ~14
      characters drawn over the top.

The output is deterministic: every visual parameter comes from
``sha256(f"{prompt}|{index}")`` and PNG encoding carries no timestamps, so
the same inputs always produce a byte-identical file.  The engine is the
fallback when ComfyUI is unreachable (CI, offline boxes) and is designed to
pass the pipeline's non-uniform-image check honestly, not by faking it.

Font lookup order (best effort — never fatal):

1. ``config["engines"]["image"]["local"]["font_path"]``
2. ``AUTOMEDIA_LOCAL_IMAGE_FONT`` (real env, then ``.env`` overlay)
3. ``/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc``
4. ``/usr/share/fonts/truetype/wqy/wqy-microhei.ttc``
5. common DejaVu / Liberation paths
6. :func:`PIL.ImageFont.load_default`
"""

from __future__ import annotations

import colorsys
import hashlib
import logging
import os
from typing import TYPE_CHECKING, ClassVar, overload

from typing_extensions import override

from automedia.core.env_overlay import env_lookup
from automedia.engines.base import BaseImageEngine
from automedia.engines.errors import EngineExecutionError

if TYPE_CHECKING:
    from PIL import Image as _PILImage
    from PIL import ImageDraw as _PILImageDraw
    from PIL import ImageFont as _PILImageFont

log = logging.getLogger(__name__)

#: Environment variable consulted when no ``font_path`` config is supplied.
FONT_PATH_ENV_VAR = "AUTOMEDIA_LOCAL_IMAGE_FONT"

#: Static font candidates, in priority order.
FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)

#: Default canvas, used when the caller does not pass explicit dimensions.
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080

#: Maximum number of prompt characters rendered on the card.
_TITLE_CHAR_LIMIT = 14


def _digest(prompt: str, index: int) -> bytes:
    """Return ``sha256(f"{prompt}|{index}")`` as raw bytes."""
    return hashlib.sha256(f"{prompt}|{index}".encode()).digest()


def _hsv(hue_deg: float, saturation: float, value: float) -> tuple[int, int, int]:
    """Convert HSV (hue in degrees) to an 8-bit RGB tuple."""
    r, g, b = colorsys.hsv_to_rgb((hue_deg % 360.0) / 360.0, saturation, value)
    return int(r * 255), int(g * 255), int(b * 255)


def _hue(raw: bytes, offset: int) -> float:
    """Derive a hue in ``[0, 360)`` from two digest bytes at *offset*."""
    value = (raw[offset % len(raw)] << 8) | raw[(offset + 1) % len(raw)]
    return (value / 65535.0) * 360.0


def _mix(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate two RGB colours by *t* in ``[0, 1]``."""
    mixed = [round(start[c] + (end[c] - start[c]) * t) for c in range(3)]
    return mixed[0], mixed[1], mixed[2]


def _clamped(value: int, low: int, high: int) -> int:
    """Clamp *value* into ``[low, high]``."""
    return max(low, min(high, value))


def _coerce_int(value: object) -> int:
    """Convert a numeric call argument to ``int`` or raise ``ValueError``."""
    if isinstance(value, (int, float, str, bytes, bytearray)):
        return int(value)
    raise ValueError(f"invalid integer value: {value!r}")


class LocalImageEngine(BaseImageEngine):
    """Deterministic, dependency-light Pillow image engine."""

    engine_name: ClassVar[str] = "local"
    modality: ClassVar[str] = "image"

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @override
    def check_available(self) -> tuple[bool, str]:
        """Available whenever Pillow imports (font selection is best effort)."""
        try:
            import PIL  # noqa: F401  # import probe only
        except Exception as exc:  # pragma: no cover - Pillow is a core dep
            return False, f"Pillow is not installed: {exc}"
        return True, "PIL"

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    @overload
    def generate(self, prompt: str, width: int, height: int, output_path: str) -> str: ...

    @overload
    def generate(
        self,
        prompt: str,
        output_path: str,
        *,
        width: int = ...,
        height: int = ...,
        **kwargs: object,
    ) -> str: ...

    def generate(
        self,
        prompt: str,
        *args: object,
        **kwargs: object,
    ) -> str:
        """Render a deterministic card for *prompt*.

        Two call shapes are accepted:

        * ``generate(prompt, width, height, output_path)`` — the abstract
          :class:`BaseImageEngine` / :class:`ImagePipeline` contract.
        * ``generate(prompt, output_path, width=..., height=...)`` — the
          convenience shape used by direct callers.

        Args:
            prompt: Text used for the seed, title, and accent palette.
            *args: Positional dimensions/output path (see call shapes).
            width: Image width in pixels (default ``1920``).
            height: Image height in pixels (default ``1080``).
            output_path: Destination PNG path (required).
            **kwargs: Optional ``index`` (default ``0``) varies the seed.

        Returns:
            Absolute path to the written PNG.

        Raises:
            ValueError: If dimensions or *output_path* are invalid.
            EngineExecutionError: If rendering/writing fails.
        """
        width, height, output_path = self._normalise_call(args, kwargs)
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid image dimensions: {width}x{height}")
        if not output_path:
            raise ValueError("output_path must not be empty")

        try:
            import PIL  # noqa: F401  # import probe only
        except ImportError as exc:  # pragma: no cover - Pillow is a core dep
            raise EngineExecutionError(
                self.engine_name,
                f"Pillow is not installed: {exc}",
                cause=exc,
            ) from exc

        output_abs = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_abs), exist_ok=True)

        index = self._index(kwargs)
        seed = _digest(prompt, index)

        try:
            image = self._render(prompt, index, seed, width, height)
            image.save(output_abs, "PNG")
        except (ValueError, OSError):
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise EngineExecutionError(
                self.engine_name,
                f"Pillow rendering failed: {exc}",
                cause=exc,
            ) from exc

        return output_abs

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_call(
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> tuple[int, int, str | None]:
        """Resolve both supported positional call shapes."""
        width = kwargs.pop("width", None)
        height = kwargs.pop("height", None)
        output_path = kwargs.pop("output_path", None)
        if len(args) == 3:
            if width is not None or height is not None or output_path is not None:
                raise TypeError("generate() received dimensions twice")
            return _coerce_int(args[0]), _coerce_int(args[1]), str(args[2])
        if len(args) == 1:
            if output_path is not None:
                raise TypeError("generate() received output_path twice")
            output_path = str(args[0])
        elif len(args) > 1:
            raise TypeError("generate() accepts at most three positional arguments")

        return (
            _coerce_int(width) if width is not None else DEFAULT_WIDTH,
            _coerce_int(height) if height is not None else DEFAULT_HEIGHT,
            str(output_path) if output_path is not None else None,
        )

    @staticmethod
    def _index(kwargs: dict[str, object]) -> int:
        """Return the seed index from ``index`` / ``image_index`` kwargs."""
        raw = kwargs.get("index", kwargs.get("image_index", 0))
        if not isinstance(raw, (int, float, str, bytes, bytearray)):
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def _render(
        self,
        prompt: str,
        index: int,
        seed: bytes,
        width: int,
        height: int,
    ) -> _PILImage.Image:
        """Compose gradient + accents + vignette + title and return the image."""
        from PIL import Image, ImageDraw

        top = _hsv(_hue(seed, 0), 0.55, 0.40)
        bottom = _hsv(_hue(seed, 2) + 35.0, 0.48, 0.94)

        base = Image.new("RGB", (width, height), top)
        draw = ImageDraw.Draw(base)

        # Vertical gradient — the non-uniformity source that validation sees.
        for y in range(height):
            t = y / max(1, height - 1)
            draw.line([(0, y), (width, y)], fill=_mix(top, bottom, t))

        # Two to three translucent geometric accents, seeded by the digest.
        accent_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        accent_draw = ImageDraw.Draw(accent_layer)
        self._draw_accents(accent_draw, seed, width, height)
        composed = Image.alpha_composite(base.convert("RGBA"), accent_layer)

        # Soft radial vignette (dark edges, clear centre) as an alpha mask.
        composed = self._apply_vignette(composed, width, height)

        # Title: first ~14 prompt characters, drawn with a shadow.
        flat = composed.convert("RGB")
        self._draw_title(ImageDraw.Draw(flat), prompt, width, height)
        return flat

    @staticmethod
    def _draw_accents(
        draw: _PILImageDraw.ImageDraw,
        seed: bytes,
        width: int,
        height: int,
    ) -> None:
        """Draw two or three seeded geometric shapes with low alpha."""
        count = 2 + (seed[8] % 2)
        min_side = min(width, height)
        for i in range(count):
            cursor = 9 + i * 7
            cx = int(width * (0.15 + 0.70 * (seed[cursor] / 255.0)))
            cy = int(height * (0.15 + 0.70 * (seed[cursor + 1] / 255.0)))
            radius = int(min_side * (0.10 + 0.16 * (seed[cursor + 2] / 255.0)))
            alpha = 36 + (seed[cursor + 3] % 60)
            fill = (*_hsv(_hue(seed, cursor + 4), 0.65, 0.95), alpha)

            if i % 2 == 0:
                draw.ellipse(
                    [
                        _clamped(cx - radius, -radius, width),
                        _clamped(cy - radius, -radius, height),
                        _clamped(cx + radius, -radius, width + radius),
                        _clamped(cy + radius, -radius, height + radius),
                    ],
                    fill=fill,
                )
            else:
                half = max(4, radius // 2)
                points = [
                    (cx, cy - half),
                    (cx + half, cy),
                    (cx, cy + half),
                    (cx - half, cy),
                ]
                draw.polygon(points, fill=fill)

    @staticmethod
    def _apply_vignette(
        image: _PILImage.Image,
        width: int,
        height: int,
    ) -> _PILImage.Image:
        """Composite a soft dark vignette over *image* using a radial mask."""
        from PIL import Image, ImageOps

        try:
            mask = Image.radial_gradient("L")
        except Exception:  # pragma: no cover - very old Pillow
            return image

        # radial_gradient is black at the centre and white at the edges in
        # current Pillow.  Normalise the orientation defensively so the
        # vignette always darkens the border rather than the centre.
        corner = mask.getpixel((0, 0))
        if isinstance(corner, (int, float)) and corner < 128:
            mask = ImageOps.invert(mask)

        mask = mask.resize((width, height), Image.Resampling.BILINEAR)
        shade = Image.new("RGBA", (width, height), (8, 8, 12, 255))
        shade.putalpha(mask.point(lambda value: int(value * 0.55)))
        return Image.alpha_composite(image, shade)

    def _draw_title(
        self,
        draw: _PILImageDraw.ImageDraw,
        prompt: str,
        width: int,
        height: int,
    ) -> None:
        """Draw the first *14* prompt characters centred on the card."""
        title = " ".join(prompt.split())
        if len(title) > _TITLE_CHAR_LIMIT:
            title = title[:_TITLE_CHAR_LIMIT] + "…"
        if not title:
            title = "AutoMedia"

        font_size = max(12, int(min(width, height) * 0.07))
        font = self._load_font(font_size)
        text_width = self._text_width(draw, title, font)
        x = max(8, (width - text_width) // 2)
        y = max(8, (height - font_size) // 2)

        # Shadow first, then the glyphs — readable on any gradient.
        draw.text((x + 2, y + 2), title, font=font, fill=(0, 0, 0))
        draw.text((x, y), title, font=font, fill=(255, 255, 255))

    def _font_candidates(self) -> list[str]:
        """Return font paths to try, in priority order."""
        candidates: list[str] = []
        configured = self._config.get("font_path") or env_lookup(FONT_PATH_ENV_VAR)
        if configured:
            candidates.append(os.path.expanduser(str(configured)))
        candidates.extend(FONT_CANDIDATES)
        return candidates

    def _load_font(self, size: int) -> _PILImageFont.FreeTypeFont | _PILImageFont.ImageFont:
        """Load the first usable font at *size*, falling back to the default."""
        from PIL import ImageFont

        for path in self._font_candidates():
            if not path or not os.path.isfile(path):
                continue
            try:
                return ImageFont.truetype(path, size)
            except Exception as exc:
                log.debug("Font candidate rejected (%s): %s", path, exc)
                continue

        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # very old Pillow without sized default font
            return ImageFont.load_default()

    @staticmethod
    def _text_width(
        draw: _PILImageDraw.ImageDraw,
        text: str,
        font: _PILImageFont.FreeTypeFont | _PILImageFont.ImageFont,
    ) -> int:
        """Measure rendered text width, tolerating font implementations."""
        try:
            return int(draw.textlength(text, font=font))
        except Exception:
            bbox = draw.textbbox((0, 0), text, font=font)
            return int(bbox[2] - bbox[0])
