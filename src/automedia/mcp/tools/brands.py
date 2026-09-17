"""Brand management tools — list_brands, add_brand."""

from __future__ import annotations

from typing import Any

from automedia.manifests.brand_profile_schema import (
    load_brand_profiles,
    save_brand_profile,
)
from automedia.mcp.tools._shared import (
    BrandNotFoundError,
    ConfigError,
    MCPErrorCode,
    error_response,
    success_response,
)

__all__ = ["add_brand", "list_brands"]


def list_brands() -> dict[str, Any]:
    """Return all configured brands with full profile metadata.

    Reads from multi-brand config in ``~/.automedia/brand_profiles.yaml``
    via :func:`automedia.manifests.brand_profile_schema.load_brand_profiles`.

    Returns
    -------
    dict
        ``{"brands": [...], "total": N}`` —
        never raises.  Each brand entry includes all fields from
        :class:`~automedia.manifests.brand_profile_schema.BrandProfile`.
    """
    try:
        profiles = load_brand_profiles()
        brands_list = [
            {
                "name": profile.brand_name,
                "aliases": profile.aliases,
                "cta_principles": profile.cta_principles,
                "blocked_words": profile.blocked_words,
                "tone_guidelines": profile.tone_guidelines,
                "brand_identity": profile.brand_identity,
                "languages": profile.languages,
                "industry": profile.industry,
                "target_audience": profile.target_audience,
                "personality": profile.personality,
                "platforms": profile.platforms,
            }
            for profile in profiles.values()
        ]
        return success_response({"brands": brands_list, "total": len(brands_list)})
    except BrandNotFoundError as exc:
        return {"brands": [], "total": 0, **error_response(MCPErrorCode.BRAND_NOT_FOUND, str(exc))}
    except ConfigError as exc:
        return {"brands": [], "total": 0, **error_response(MCPErrorCode.CONFIG_MISSING, str(exc))}
    except Exception as exc:
        return {"brands": [], "total": 0, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def add_brand(
    name: str,
    industry: str = "",
    target_audience: str = "",
    aliases: list[str] | None = None,
    blocked_words: list[str] | None = None,
    brand_identity: str = "",
    tone_guidelines: str = "",
    cta_principles: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new brand profile.

    Uses :func:`automedia.manifests.brand_profile_schema.save_brand_profile`
    to write the profile into ``~/.automedia/brand_profiles.yaml``.
    The brand *name* is required; every other parameter is optional.

    ``aliases``, ``blocked_words`` and ``brand_identity`` are read by the
    G3 brand-CTA gate; ``tone_guidelines`` is read by the G6 tone gate;
    ``cta_principles`` is injected into the CW (content writer) prompt so the
    drafted call-to-action follows the brand's principles.

    Parameters
    ----------
    name:
        Brand name (required).  Used as the key in the profiles YAML.
    industry:
        Optional industry / vertical (e.g. ``"SaaS"``, ``"e-commerce"``).
    target_audience:
        Optional audience description (e.g. ``"Tech professionals"``).
    aliases:
        Optional alternate names the brand may appear under.
    blocked_words:
        Optional forbidden words that must not appear in content.
    brand_identity:
        Optional brand positioning statement.
    tone_guidelines:
        Optional textual tone-of-voice guidelines.
    cta_principles:
        Optional principles guiding how the call-to-action should be written
        (e.g. ``["Lead with the benefit", "Never use urgency"]``).

    Returns
    -------
    dict
        ``{"success": True, "brand_name": str, "industry": str,
        "target_audience": str}`` on success, or an error dict on
        failure (e.g. empty brand name).
    """
    try:
        data: dict[str, Any] = {"brand_name": name}
        if industry:
            data["industry"] = industry
        if target_audience:
            data["target_audience"] = target_audience
        if aliases:
            data["aliases"] = aliases
        if blocked_words:
            data["blocked_words"] = blocked_words
        if brand_identity:
            data["brand_identity"] = brand_identity
        if tone_guidelines:
            data["tone_guidelines"] = tone_guidelines
        if cta_principles:
            data["cta_principles"] = cta_principles

        save_brand_profile(name, data)

        return success_response(
            {
                "success": True,
                "brand_name": name,
                "industry": industry,
                "target_audience": target_audience,
            }
        )
    except ConfigError as exc:
        return {
            "success": False,
            **error_response(
                MCPErrorCode.CONFIG_MISSING, str(exc), "Check brand profile configuration"
            ),
        }
    except OSError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error saving brand: {exc}"),
        }
