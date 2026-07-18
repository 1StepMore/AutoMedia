"""Platform media specification data model and built-in defaults."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True)
class PlatformMediaSpec:
    """Media specification for a platform's content requirements.

    Attributes:
        width: Video/image width in pixels (0 if not applicable).
        height: Video/image height in pixels (0 if not applicable).
        aspect_ratio: Aspect ratio string (e.g. "16:9", "9:16", "1:1", "3:4", "free").
        max_duration_s: Maximum content duration in seconds (0 if not applicable).
        format: Output format (e.g. "mp4", "jpg", "markdown", "html", "j2").
        codec: Video/audio codec (empty string if not applicable).
        bitrate: Target bitrate in kbps (0 if not applicable).
        fps: Frames per second (0 if not applicable).
    """

    width: int = 0
    height: int = 0
    aspect_ratio: str = "free"
    max_duration_s: int = 0
    format: str = ""
    codec: str = ""
    bitrate: int = 0
    fps: int = 0


DEFAULT_SPEC = PlatformMediaSpec(
    width=1920,
    height=1080,
    aspect_ratio="16:9",
    max_duration_s=0,
    format="mp4",
    codec="h264",
    bitrate=0,
    fps=30,
)

PLATFORM_MEDIA_SPECS: dict[str, PlatformMediaSpec] = {
    "wechat": PlatformMediaSpec(900, 383, "16:9", 600, "jpg", "jpeg", 0, 0),
    "zhihu": PlatformMediaSpec(1080, 0, "free", 0, "markdown", "", 0, 0),
    "xiaohongshu": PlatformMediaSpec(1080, 1440, "3:4", 60, "jpg", "jpeg", 0, 0),
    "douyin": PlatformMediaSpec(1080, 1920, "9:16", 180, "mp4", "h264", 6000, 30),
    "youtube": PlatformMediaSpec(1920, 1080, "16:9", 3600, "mp4", "h264", 16000, 30),
    "twitter": PlatformMediaSpec(1200, 675, "16:9", 140, "mp4", "h264", 5000, 30),
    "tiktok": PlatformMediaSpec(1080, 1920, "9:16", 180, "mp4", "h264", 6000, 30),
    "instagram": PlatformMediaSpec(1080, 1080, "1:1", 90, "mp4", "h264", 5000, 30),
    "facebook": PlatformMediaSpec(1200, 630, "16:9", 240, "mp4", "h264", 8000, 30),
    "linkedin": PlatformMediaSpec(1200, 627, "16:9", 120, "jpg", "jpeg", 0, 0),
    "medium": PlatformMediaSpec(1400, 0, "free", 0, "markdown", "", 0, 0),
    "wordpress": PlatformMediaSpec(1200, 0, "free", 0, "html", "", 0, 0),
    "bilibili": PlatformMediaSpec(1920, 1080, "16:9", 600, "mp4", "h264", 12000, 30),
    "weibo": PlatformMediaSpec(1080, 1920, "9:16", 180, "mp4", "h264", 5000, 30),
    "toutiao": PlatformMediaSpec(1200, 0, "free", 0, "j2", "", 0, 0),
    "baijiahao": PlatformMediaSpec(1200, 0, "free", 0, "html", "", 0, 0),
    "kuaishou": PlatformMediaSpec(1080, 1920, "9:16", 180, "mp4", "h264", 6000, 30),
    "reddit": PlatformMediaSpec(1200, 0, "free", 0, "markdown", "", 0, 0),
    "juejin": PlatformMediaSpec(1200, 0, "free", 0, "markdown", "", 0, 0),
}


def get_platform_media_spec(
    platform: str,
    brand_config: dict[str, Any] | None = None,
) -> PlatformMediaSpec:
    """Resolve a platform media spec, optionally overridden by brand config.

    Steps:
        1. Look up platform name in PLATFORM_MEDIA_SPECS.
        2. Fall back to DEFAULT_SPEC if platform is unknown.
        3. Apply brand config overrides from
           ``brand_config["platforms"][platform]["media"]`` if provided.

    Args:
        platform: Platform name (e.g. "youtube", "xiaohongshu").
        brand_config: Optional brand configuration dict with platforms hierarchy.

    Returns:
        A PlatformMediaSpec with brand overrides applied (if any).
    """
    spec = PLATFORM_MEDIA_SPECS.get(platform, DEFAULT_SPEC)

    if brand_config:
        platforms_cfg = brand_config.get("platforms", {})
        if not isinstance(platforms_cfg, dict):
            return spec  # platforms is a list[str] — no per-platform overrides
        platform_overrides = platforms_cfg.get(platform, {}).get("media", {})
        if platform_overrides:
            override_kwargs = {
                f.name: platform_overrides.get(f.name, getattr(spec, f.name))
                for f in fields(PlatformMediaSpec)
            }
            spec = PlatformMediaSpec(**override_kwargs)

    return spec


def resolve_media_specs(
    brand_profile: dict[str, Any],
    platforms: list[str],
) -> dict[str, PlatformMediaSpec]:
    """Resolve media specs for a list of platforms with brand overrides.

    Iterates over the given platform names and resolves each platform's
    media spec, applying brand-level overrides from the brand profile.

    Args:
        brand_profile: Brand configuration dict with optional
            ``platforms.<name>.media`` override keys.
        platforms: List of platform names (e.g. ``["wechat", "xiaohongshu"]``).

    Returns:
        Dict mapping platform names to their resolved PlatformMediaSpec.
    """
    specs: dict[str, PlatformMediaSpec] = {}
    for platform in platforms:
        specs[platform] = get_platform_media_spec(platform, brand_profile)
    return specs


def get_active_media_spec(
    gate_context: dict[str, Any],
    platform: str | None = None,
) -> PlatformMediaSpec:
    """Get active media spec from gate context, optionally for a specific platform.

    Args:
        gate_context: The pipeline gate context dict.  Expects keys
            ``media_specs`` (resolved spec dict) and ``brand_platforms``
            (ordered list of platform names).
        platform: Optional platform name.  When ``None``, uses the first
            platform from ``brand_platforms`` or falls back to
            ``DEFAULT_SPEC``.

    Returns:
        A PlatformMediaSpec for the given or first active platform.
    """
    media_specs: dict[str, PlatformMediaSpec] = gate_context.get("media_specs", {})

    if platform is not None:
        return media_specs.get(platform, DEFAULT_SPEC)

    # No platform specified — use first platform's spec or DEFAULT_SPEC
    brand_platforms: list[str] = gate_context.get("brand_platforms", [])
    if brand_platforms:
        return media_specs.get(brand_platforms[0], DEFAULT_SPEC)

    return DEFAULT_SPEC
