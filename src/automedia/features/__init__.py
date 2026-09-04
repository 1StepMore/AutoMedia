"""Open-core feature tier marker module (declarative only — no license logic).

Defines which canonical gate IDs belong to which open-core tier and provides
:func:`check_tier` to query tier availability for a feature. This module is a
MARKER: it never blocks execution itself and contains no license enforcement.
Enforcement call sites are added separately (plan todo 17) at gate-list
composition points.

Tier semantics
--------------
- With **no override** set, every tier reports ``available=True`` — the free
  local edition runs everything.
- An optional override restricts availability: env var
  ``AUTOMEDIA_FEATURE_TIER`` (e.g. ``"pro"``) or a user-level
  ``~/.automedia/features.yaml`` file containing ``tier: pro|enterprise``.
  The override names the edition the deployment runs: gates in tiers ABOVE
  the override tier (i.e. paid tiers above it) are unavailable, everything
  at or below is available. ``core`` < ``pro`` < ``enterprise``.
  The env var wins over the YAML file when both are set.
- Unknown features resolve to ``{"available": False, "error": ...}`` without
  raising.

User-config reads use the existing machinery (``automedia.core.paths`` /
``automedia.core.config_loader`` pattern: ``AUTOMEDIA_CONFIG_DIR`` aware,
pure read, no writes).
"""

from __future__ import annotations

import os
from typing import Any

from automedia.core.paths import get_user_config_dir

__all__ = [
    "FEATURE_ALIASES",
    "FEATURE_TIERS",
    "check_tier",
]

# ---------------------------------------------------------------------------
# Tier table — keyed by CANONICAL gate IDs (the `_gate_name` strings)
# ---------------------------------------------------------------------------

FEATURE_TIERS: dict[str, list[str]] = {
    # Free tier: everything a local content pipeline needs.
    "core": [
        "pre-gate",
        "CW",
        "G0",
        "G2",
        "G3",
        "G4",
        "G6",
        "L1",
        "L2",
        "L4",
    ],
    # Pro tier: humanizer, HTML hard, full video track, HITL, distribution.
    "pro": [
        "G1",
        "G5",
        "V0",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "H0",
        "D1",
        "D2",
        "D3",
        "D4",
        "D5",
        "D6",
        "D7",
    ],
    # Enterprise tier: platform integrity + sub-pipeline repurpose.
    "enterprise": [
        "L3",
        "P1",
        "P2",
        "P3",
        "P4",
    ],
}

# ---------------------------------------------------------------------------
# Load-time assertion — the tier union must exactly cover the gate registry
# ---------------------------------------------------------------------------


def _canonical_registry_names() -> set[str]:
    """Return gate names registered from production ``automedia.*`` modules.

    Test fixtures intentionally inject fake gates (e.g. ``G89`` in
    tests/test_core/test_smoke.py) into the global registry; those classes
    have ``__module__`` under ``tests`` and are excluded here so the
    load-time assertion only reasons about real pipeline gates.
    """
    from automedia.gates.base import _registry

    return {
        name
        for name, cls in _registry.get_all().items()
        if getattr(cls, "__module__", "").startswith("automedia.")
    }


def _verify_tiers_cover_registry() -> None:
    """Assert FEATURE_TIERS union == production GateRegistry keys at import.

    Imports the gate registry (``automedia.gates`` auto-registration via
    ``BaseGate.__init_subclass__``) and fails loudly if a production gate
    lacks a tier or a tier entry names a nonexistent gate. Raises
    ``ImportError`` on any mismatch so misconfiguration is caught at
    import, not at runtime.
    """
    import automedia.gates  # noqa: F401 — import triggers auto-registration

    registered = _canonical_registry_names()
    tiered: set[str] = {name for names in FEATURE_TIERS.values() for name in names}

    missing = sorted(registered - tiered)
    phantom = sorted(tiered - registered)
    if missing or phantom:
        raise ImportError(
            "FEATURE_TIERS does not match the gate registry: "
            f"gates without a tier: {missing or '[]'}; "
            f"tier entries that are not registered gates: {phantom or '[]'}"
        )


_verify_tiers_cover_registry()


# ---------------------------------------------------------------------------
# Alias table — roadmap-style snake_case ids → canonical gate id(s)
# ---------------------------------------------------------------------------

FEATURE_ALIASES: dict[str, str | list[str]] = {
    # Single-gate aliases
    "video-gate-v7": "V7",
    "director-panel": "H0",
    "humanizer": "G1",
    "fact-check": "G0",
    "tone-check": "G6",
    # Group aliases (multi-gate feature bundles)
    "video-gates": ["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"],
    "multi-platform-publish": ["D1", "D2", "D3", "D4", "D5", "D6", "D7"],
    "gate-history-dashboard": ["L1", "L2"],
    "sub-pipeline-repurpose": ["P1", "P2", "P3", "P4"],
    "platform-integrity": "L3",
}

# Tier rank used by the override semantics: core < pro < enterprise.
_TIER_RANK: dict[str, int] = {"core": 0, "pro": 1, "enterprise": 2}


# ---------------------------------------------------------------------------
# Override resolution (pure read — env var and user-level features.yaml)
# ---------------------------------------------------------------------------


def _resolve_override_tier() -> str | None:
    """Resolve the optional tier override, or None when unrestricted.

    Priority: ``AUTOMEDIA_FEATURE_TIER`` env var > ``features.yaml`` in the
    user config dir. Invalid values are ignored (treated as no override) so a
    typo never locks a deployment out of its gates.
    """
    env_value = os.environ.get("AUTOMEDIA_FEATURE_TIER", "").strip()
    if env_value:
        return env_value if env_value in _TIER_RANK else None

    config_dir = get_user_config_dir()
    yaml_path = config_dir / "features.yaml"
    if not yaml_path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not isinstance(data, dict):
        return None
    tier = data.get("tier")
    if isinstance(tier, str) and tier in _TIER_RANK:
        return tier
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _tier_of(gate_id: str) -> str | None:
    """Return the tier owning *gate_id*, or None if unknown."""
    for tier, names in FEATURE_TIERS.items():
        if gate_id in names:
            return tier
    return None


def check_tier(feature: str) -> dict[str, Any]:
    """Report the tier and availability for a feature.

    Parameters
    ----------
    feature:
        A canonical gate ID (e.g. ``"V7"``) or a roadmap-style alias
        (e.g. ``"video-gate-v7"``). Aliases are resolved first.

    Returns
    -------
    dict[str, Any]
        ``{"feature": canonical_id, "tier": core|pro|enterprise,
        "available": bool}``. With no override every tier is available
        (free local = everything open). With an override, gates in tiers
        above the override tier are unavailable.

        Unknown features return ``{"feature": <input>, "available": False,
        "error": "unknown feature"}`` — no exception is raised.
    """
    if feature is None:
        return {"feature": None, "available": False, "error": "unknown feature"}

    # Single-gate alias resolution first
    canonical: str | list[str] = FEATURE_ALIASES.get(feature, feature)

    # Group aliases map to a bundle: available only if EVERY member is.
    tier: str | None
    feature_id: str
    if isinstance(canonical, list):
        tiers = [_tier_of(g) for g in canonical]
        if any(t is None for t in tiers):
            return {"feature": feature, "available": False, "error": "unknown feature"}
        tier = max((t for t in tiers if t is not None), key=lambda t: _TIER_RANK[t])
        feature_id = feature
    else:
        tier = _tier_of(canonical)
        feature_id = canonical
        if tier is None:
            return {"feature": feature, "available": False, "error": "unknown feature"}

    override = _resolve_override_tier()
    available = True
    if override is not None:
        available = _TIER_RANK[tier] <= _TIER_RANK[override]

    return {"feature": feature_id, "tier": tier, "available": available}
