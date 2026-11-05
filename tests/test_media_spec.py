"""Tests for platform media spec resolution (#378).

The video engine used to default to 1920x1080 unconditionally, so a ``douyin``
run shipped a landscape video.  ``get_video_media_spec`` is the bridge between
a brand's declared platforms and the renderer's frame size.
"""

from __future__ import annotations

from automedia.core.media_spec import (
    DEFAULT_SPEC,
    PLATFORM_MEDIA_SPECS,
    PlatformMediaSpec,
    get_video_media_spec,
)


def _context(platforms: list[str]) -> dict[str, object]:
    """Build the gate-context slice the resolver reads."""
    return {
        "brand_platforms": platforms,
        "media_specs": {name: PLATFORM_MEDIA_SPECS[name] for name in platforms},
    }


class TestGetVideoMediaSpec:
    def test_douyin_yields_portrait(self) -> None:
        spec = get_video_media_spec(_context(["douyin"]))
        assert (spec.width, spec.height) == (1080, 1920)
        assert spec.aspect_ratio == "9:16"

    def test_skips_non_video_platforms(self) -> None:
        """``wechat`` resolves to a 900x383 JPG — never the video frame size."""
        spec = get_video_media_spec(_context(["wechat", "douyin"]))
        assert spec.format == "mp4"
        assert (spec.width, spec.height) == (1080, 1920)

    def test_first_video_platform_wins(self) -> None:
        spec = get_video_media_spec(_context(["youtube", "douyin"]))
        assert (spec.width, spec.height) == (1920, 1080)

    def test_no_platforms_falls_back_to_default(self) -> None:
        assert get_video_media_spec({}) is DEFAULT_SPEC

    def test_text_only_platform_falls_back_to_default(self) -> None:
        """A brand publishing only markdown has no frame size to honour."""
        spec = get_video_media_spec(_context(["zhihu", "medium"]))
        assert spec is DEFAULT_SPEC

    def test_brand_override_is_respected(self) -> None:
        """A per-brand ``platforms.<name>.media`` override reaches the resolver."""
        from automedia.core.media_spec import get_platform_media_spec

        override = get_platform_media_spec(
            "douyin",
            {"platforms": {"douyin": {"media": {"width": 720, "height": 1280}}}},
        )
        ctx: dict[str, object] = {
            "brand_platforms": ["douyin"],
            "media_specs": {"douyin": override},
        }
        spec = get_video_media_spec(ctx)
        assert (spec.width, spec.height) == (720, 1280)

    def test_zero_sized_spec_is_not_treated_as_video(self) -> None:
        zero = PlatformMediaSpec(width=0, height=0, format="mp4", fps=0)
        ctx: dict[str, object] = {"brand_platforms": ["x"], "media_specs": {"x": zero}}
        # format says mp4, so it is a video platform even with fps 0 — the
        # caller decides what to do with a zero size.
        assert get_video_media_spec(ctx) is zero
