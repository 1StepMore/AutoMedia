"""Prompt template loader — user overrides via Jinja2, with built-in fallback.

Usage
-----
>>> from automedia.prompts import load_prompt
>>> prompt = load_prompt("brand_strategy", brand_name="Acme", industry="SaaS")

Override chain
--------------
1. ``~/.automedia/overrides/prompts/<name>.j2``  (user override, highest priority)
2. ``<built-in>/prompts/<name>.j2``               (shipped with automedia, fallback)

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


def load_prompt(name: str, **kwargs: object) -> str:
    """Load and render a prompt template.

    Checks the user override directory first
    (``~/.automedia/overrides/prompts/<name>.j2``), then falls back to the
    built-in template shipped with automedia.

    Parameters
    ----------
    name:
        Template stem (e.g. ``"brand_strategy"`` for
        ``brand_strategy.j2``).
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
    # 1. User override
    override_path = _OVERRIDE_DIR / f"{name}.j2"
    if override_path.exists():
        return Template(override_path.read_text(encoding="utf-8")).render(**kwargs)

    # 2. Built-in fallback
    builtin_path = _PROMPTS_DIR / f"{name}.j2"
    return Template(builtin_path.read_text(encoding="utf-8")).render(**kwargs)


__all__ = ["load_prompt"]
