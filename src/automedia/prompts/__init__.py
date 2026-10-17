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

from jinja2 import Environment, FileSystemLoader

from automedia.core.paths import get_user_config_dir

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent
_OVERRIDE_DIR = get_user_config_dir() / "overrides" / "prompts"

# A shared environment whose loader resolves ``{% include %}`` / ``{% import %}``
# against the built-in prompts directory. This lets platform templates reuse
# common partials (e.g. ``partials/no_unsourced_numbers.j2``) instead of
# copy-pasting the same constraint into every file. User overrides are rendered
# through this environment too, so an override may also include built-in
# partials. Rendering defaults match the previous ``jinja2.Template`` usage.
# Prompts are plain-text LLM instructions, never rendered to HTML, so
# autoescape stays off to preserve the exact template text (matching the
# previous jinja2.Template default).
_JINJA_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)))  # noqa: S701


def _render(source: str, **kwargs: object) -> str:
    """Render a Jinja2 template *source* string with the shared environment."""
    return _JINJA_ENV.from_string(source).render(**kwargs)


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
            return _render(platform_override_path.read_text(encoding="utf-8"), **kwargs)

    # 2. Global user override
    override_path = _OVERRIDE_DIR / f"{name}.j2"
    if override_path.exists():
        return _render(override_path.read_text(encoding="utf-8"), **kwargs)

    # 3. Built-in platform variant (shipped with automedia)
    if platform is not None:
        # Check general platforms dir first, then MCP-specific platform variants
        for subdir in ("platforms", "platforms/mcp"):
            builtin_platform_path = _PROMPTS_DIR / subdir / platform.lower() / f"{name}.j2"
            if builtin_platform_path.exists():
                return _render(builtin_platform_path.read_text(encoding="utf-8"), **kwargs)

    # 4. Built-in generic fallback
    builtin_path = _PROMPTS_DIR / f"{name}.j2"
    return _render(builtin_path.read_text(encoding="utf-8"), **kwargs)


__all__ = ["load_prompt"]
