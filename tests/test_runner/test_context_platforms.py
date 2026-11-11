"""An explicit platform list must reach the media spec (#494).

``run_full_pipeline(platforms=...)`` (the SDK argument the local UI now sets)
used to feed gate selection only, so the media stage read the brand profile's
spec and a douyin-targeted run rendered 1920x1080.
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import patch

from automedia.core.media_spec import get_video_media_spec
from automedia.manifests.brand_profile_schema import BrandProfile
from automedia.pipelines.runner import _build_pipeline_context, run_full_pipeline


def _project(project_dir: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(project_id="platforms", project_dir=str(project_dir))


def _context(
    project_dir: Path,
    *,
    platforms: list[str] | None,
    brand_profile: BrandProfile | None = None,
) -> dict[str, object]:
    return _build_pipeline_context(
        "topic",
        "brand",
        "short-video",
        _project(project_dir),
        {},
        "default",
        brand_profile,
        False,
        False,
        None,
        "",
        "",
        "corr",
        [],
        platforms=platforms,
    )


def test_explicit_platform_sets_the_video_size(tmp_path: Path) -> None:
    context = _context(tmp_path, platforms=["douyin"])
    spec = get_video_media_spec(context)
    assert (spec.width, spec.height) == (1080, 1920)


def test_explicit_platform_overrides_the_brand_default(tmp_path: Path) -> None:
    brand = BrandProfile(brand_name="b", platforms=["youtube"])
    context = _context(tmp_path, platforms=["douyin"], brand_profile=brand)
    assert context["brand_platforms"] == ["douyin"]
    spec = get_video_media_spec(context)
    assert (spec.width, spec.height) == (1080, 1920)


def test_absent_platform_argument_keeps_the_brand_platforms(tmp_path: Path) -> None:
    brand = BrandProfile(brand_name="b", platforms=["youtube"])
    context = _context(tmp_path, platforms=None, brand_profile=brand)
    assert context["brand_platforms"] == ["youtube"]
    spec = get_video_media_spec(context)
    assert (spec.width, spec.height) == (1920, 1080)


def test_run_full_pipeline_forwards_the_platforms_argument(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def capture(*args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        raise RuntimeError("stop after the context is built")

    project = types.SimpleNamespace(project_id="platforms", project_dir=str(tmp_path / "p"))
    with (
        patch("automedia.core.config_loader.load_config", return_value={}),
        patch("automedia.core.project.Project") as project_cls,
        patch("automedia.pipelines.runner._build_pipeline_context", side_effect=capture),
    ):
        project_cls.init.return_value = project
        result = run_full_pipeline("topic", "brand", mode="short-video", platforms=["douyin"])

    assert captured["platforms"] == ["douyin"]
    assert result.status == "failed"
