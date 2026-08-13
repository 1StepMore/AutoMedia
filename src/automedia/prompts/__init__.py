"""Prompt template loader — user overrides via Jinja2, with built-in fallback.

Usage
-----
>>> from automedia.prompts import load_prompt
>>> prompt = load_prompt("brand_strategy", brand_name="Acme", industry="SaaS")

Override chain
--------------
1. ``~/.automedia/overrides/prompts/<platform>/<name>.j2``  (platform-scoped user override)
2. ``~/.automedia/overrides/prompts/<name>.j2``             (global user override)
3. ``<built-in>/prompts/platforms/<platform>/<name>.j2``    (built-in platform variant)
4. ``<built-in>/prompts/<name>.j2``                          (shipped with automedia, fallback)

When *platform* is ``None`` or ``""``, steps 1 and 3 are skipped — only the global
override and built-in fallback are checked.

The approach mirrors the existing 6-layer config hierarchy used in
``automedia/core/overrides.py`` (see ``OverridesLoader``).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from automedia.core.paths import get_user_config_dir

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent
_OVERRIDE_DIR = get_user_config_dir() / "overrides" / "prompts"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_prompt(name: str, platform: str | None = None, **kwargs: object) -> str:
    """Load and render a prompt template.

    Resolution order (highest to lowest priority):

    1. Platform-scoped user override
       ``~/.automedia/overrides/prompts/<platform>/<name>.j2``
       (checked only when *platform* is not ``None``)
    2. Global user override
       ``~/.automedia/overrides/prompts/<name>.j2``
    3. Built-in platform variant
       ``<built-in>/prompts/platforms/<platform>/<name>.j2``
       (checked only when *platform* is not ``None``)
    4. Built-in template shipped with automedia
       ``<built-in>/prompts/<name>.j2``

    Parameters
    ----------
    name:
        Template stem (e.g. ``"brand_strategy"`` for
        ``brand_strategy.j2``).
    platform:
        Optional platform name for platform-scoped prompt resolution.
        When provided, checks ``<overrides>/prompts/<platform>/<name>.j2``
        and ``<built-in>/prompts/platforms/<platform>/<name>.j2`` before
        the generic built-in fallback.
    **kwargs:
        Variables passed to the Jinja2 ``Template.render()`` call.

    Returns
    -------
    Rendered prompt string.

    Raises
    ------
    FileNotFoundError
        When neither the user override nor the built-in template exists.
    """
    # 1. Platform-scoped user override (highest priority)
    if platform is not None:
        platform_override_path = _OVERRIDE_DIR / platform.lower() / f"{name}.j2"
        if platform_override_path.exists():
            return Template(platform_override_path.read_text(encoding="utf-8")).render(**kwargs)

    # 2. Global user override
    override_path = _OVERRIDE_DIR / f"{name}.j2"
    if override_path.exists():
        return Template(override_path.read_text(encoding="utf-8")).render(**kwargs)

    # 3. Built-in platform variant (shipped with automedia)
    if platform is not None:
        # Check general platforms dir first, then MCP-specific platform variants
        for subdir in ("platforms", "platforms/mcp"):
            builtin_platform_path = _PROMPTS_DIR / subdir / platform.lower() / f"{name}.j2"
            if builtin_platform_path.exists():
                return Template(builtin_platform_path.read_text(encoding="utf-8")).render(**kwargs)

    # 4. Built-in generic fallback
    builtin_path = _PROMPTS_DIR / f"{name}.j2"
    return Template(builtin_path.read_text(encoding="utf-8")).render(**kwargs)


__all__ = ["load_prompt"]
