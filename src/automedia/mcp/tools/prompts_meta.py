"""Prompt template metadata tools — list_overridable_templates."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.mcp.tools._shared import (
    success_response,
)

log = get_logger(__name__)

__all__ = [
    "list_overridable_templates",
]

# ---------------------------------------------------------------------------
# Prompt template metadata — known Jinja2 variables per template
# ---------------------------------------------------------------------------

_PROMPT_METADATA: dict[str, dict[str, Any]] = {
    "brand_strategy": {
        "variables": ["brand_name", "industry", "target_audience", "context"],
        "purpose": "Generate a brand positioning, audience analysis, and messaging "
        "strategy via LLM.",
    },
    "content_quality": {
        "variables": ["content", "criteria", "brand"],
        "purpose": "Score content quality against specified criteria using LLM evaluation.",
    },
    "content_writer": {
        "variables": ["topic", "brand"],
        "purpose": "Write a full article draft for Chinese social media platforms.",
    },
    "copy_review_g2": {
        "variables": ["content", "brand_guidelines"],
        "purpose": "Evaluate content tone, style, and brand compliance (Gate G2).",
    },
    "fact_check_g0": {
        "variables": ["content"],
        "purpose": "Verify factual claims in content against known knowledge (Gate G0).",
    },
    "fact_check_g0_plausibility": {
        "variables": ["content", "topic"],
        "purpose": "Plausibility check for content lacking source material (Gate G0).",
    },
    "humanizer_g1": {
        "variables": ["content"],
        "purpose": "Detect AI writing patterns and assess natural readability (Gate G1).",
    },
    "image_prompt": {
        "variables": ["topic", "brand", "image_index"],
        "purpose": "Generate Stable Diffusion / ComfyUI image prompts for cover art.",
    },
    "pipeline_strategy": {
        "variables": ["topic", "brand", "mode", "context"],
        "purpose": "Design content production strategy — structure, platform, and angles.",
    },
    "topic_research": {
        "variables": ["category", "count", "trending_data"],
        "purpose": "Research trending topics within a category and recommend angles.",
    },
    # Platform-specific overrides
    "platforms/wechat/content_writer": {
        "variables": ["topic", "brand", "tone", "platform", "audience", "brand_guidelines"],
        "purpose": "WeChat-specific content writer template (long-form, formal article).",
    },
}


def list_overridable_templates() -> dict[str, Any]:
    """List all overridable prompt templates with metadata and override status.

    Enumerates every known Jinja2 prompt template, checks whether a user
    override file exists in ``~/.automedia/overrides/prompts/``, and reports
    the template's variables, purpose, and override state.

    Returns
    -------
    dict
        ``{"templates": [...], "count": int, "overrides_dir": str}`` where
        each template entry contains ``name``, ``path``, ``variables``,
        ``purpose``, ``overridden``, ``override_path``, and
        ``platform_overrides``.
    """
    with contextlib.suppress(Exception):
        from automedia.prompts import load_prompt as _  # noqa: F401 — ensure prompts module loaded

    from automedia.core.paths import get_user_config_dir

    prompts_pkg_dir = Path(__file__).resolve().parent.parent / "prompts"
    overrides_prompts_dir = get_user_config_dir() / "overrides" / "prompts"

    templates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for stem, meta in sorted(_PROMPT_METADATA.items()):
        name = stem
        # Determine the built-in path
        if "/" in stem:
            # Platform-scoped template: platforms/wechat/content_writer
            builtin_path = prompts_pkg_dir / f"{stem.replace('/', '/')}.j2"
        else:
            builtin_path = prompts_pkg_dir / f"{stem}.j2"

        path = str(builtin_path) if builtin_path.exists() else ""

        # Check global override
        global_override = overrides_prompts_dir / f"{name.split('/')[-1]}.j2"
        overridden = global_override.exists()
        override_path = str(global_override) if overridden else ""

        # Check platform-scoped overrides
        platform_overrides: dict[str, str] = {}
        if overrides_prompts_dir.is_dir():
            for plat_dir in sorted(overrides_prompts_dir.iterdir()):
                if plat_dir.is_dir():
                    plat_override = plat_dir / f"{name.split('/')[-1]}.j2"
                    if plat_override.exists():
                        platform_overrides[plat_dir.name] = str(plat_override)

        templates.append(
            {
                "name": name,
                "path": path,
                "variables": meta["variables"],
                "purpose": meta["purpose"],
                "overridden": overridden,
                "override_path": override_path,
                "platform_overrides": platform_overrides,
            }
        )
        seen.add(name)

    return success_response(
        {
            "templates": templates,
            "count": len(templates),
            "overrides_dir": str(overrides_prompts_dir),
        }
    )
