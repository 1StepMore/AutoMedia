"""Brand profile schema — dataclass and loader for multi-brand YAML file.

Public API
----------
- ``BrandProfile`` dataclass
- ``load_brand_profile(path) -> BrandProfile``
- ``load_brand_profiles() -> dict[str, BrandProfile]``
- ``save_brand_profile(brand_name, data) -> None``
- ``list_brand_names() -> list[str]``
- ``validate_brand_profile(data) -> bool``
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from automedia.core.paths import get_user_config_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constant (patched in tests)
# ---------------------------------------------------------------------------

_BRAND_PROFILES_PATH: Path = get_user_config_dir() / "brand_profiles.yaml"

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class BrandProfile:
    """Typed representation of a brand profile.

    All fields have safe defaults so that partial YAML files do not cause
    crashes.
    """

    brand_name: str = ""
    aliases: list[str] = field(default_factory=list)
    cta_principles: list[str] = field(default_factory=list)
    blocked_words: list[str] = field(default_factory=list)
    tone_guidelines: str = ""
    brand_identity: str = ""
    languages: dict[str, dict[str, Any]] = field(default_factory=dict)
    industry: str = ""
    target_audience: str = ""
    personality: str = ""
    platforms: list[str] = field(default_factory=list)
    automation: dict[str, str] = field(
        default_factory=lambda: {
            "wechat": "auto",
            "zhihu": "auto",
            "xiaohongshu": "manual",
            "feishu": "auto",
        }
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_KEYS: tuple[str, ...] = ("brand_name",)

# ---------------------------------------------------------------------------
# Platform name helpers
# ---------------------------------------------------------------------------


def _extract_platforms(raw: object) -> list[str]:
    """Extract a list of platform names from a raw YAML value.

    Supports both the new ``list[str]`` format and the legacy ``dict``
    format (where dict keys are treated as platform names for backward
    compatibility).
    """
    if isinstance(raw, list):
        return [str(p) for p in raw if isinstance(p, str)]
    if isinstance(raw, dict):
        # Legacy format: ``platforms: {wechat: {enabled: true}}``
        return list(raw.keys())
    return []


def _extract_automation(raw: object) -> dict[str, str]:
    """Extract a dict of platform -> automation level from a raw YAML value.

    Returns a dict with only valid automation values (``"auto"``, ``"review"``,
    or ``"manual"``).  Invalid values are logged and discarded.
    """
    VALID_LEVELS = {"auto", "review", "manual"}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if value in VALID_LEVELS:
            result[key] = value
        else:
            logger.warning(
                "Invalid automation level %r for platform %r; expected one of %s",
                value,
                key,
                sorted(VALID_LEVELS),
            )
    return result


def _get_registered_platform_names() -> set[str]:
    """Return the set of platform names registered via AdapterRegistry.

    Falls back to an empty set when the registry module is unavailable
    (e.g. during early imports or in test isolation).
    """
    try:
        from automedia.adapters.registry import AdapterRegistry  # noqa: PLC0415

        return set(AdapterRegistry.list())
    except Exception:
        return {
            "wechat",
            "zhihu",
            "xiaohongshu",
            "feishu",
        }


def _validate_platforms(platforms: list[str]) -> None:
    """Warn if any platform name does not match a registered adapter.

    This is a non-blocking check — unknown platform names are accepted
    with a warning rather than raising an error.
    """
    if not platforms:
        return

    registered = _get_registered_platform_names()
    if not registered:
        return  # No reference data available — skip validation

    for name in platforms:
        if name not in registered:
            warnings.warn(
                f"Platform {name!r} in brand profile is not a registered adapter. "
                f"Expected one of: {sorted(registered)}.",
                stacklevel=3,
            )


def validate_brand_profile(data: dict[str, Any]) -> bool:
    """Validate that *data* contains the minimum required keys for a brand profile.

    Rules:
    - *data* must be a non-None ``dict``.
    - ``brand_name`` must be present and be a non-empty ``str``.

    Returns ``True`` when valid; ``False`` otherwise (never raises).
    """
    if not isinstance(data, dict):
        return False

    for key in _REQUIRED_KEYS:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            return False

    return True


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_brand_profile(path: str) -> BrandProfile:
    """Load and validate a brand profile YAML file.

    Parameters
    ----------
    path:
        Filesystem path to the ``brand-profile.yaml`` file.

    Returns
    -------
    BrandProfile
        A populated dataclass with defaults for missing optional fields.

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    ValueError
        When the YAML content fails validation.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Brand profile not found: {path}")

    with open(file_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(f"Brand profile must be a YAML mapping, got {type(data).__name__}")

    if not validate_brand_profile(data):
        raise ValueError("Brand profile validation failed: 'brand_name' must be a non-empty string")

    platforms = _extract_platforms(data.get("platforms"))
    _validate_platforms(platforms)

    return BrandProfile(
        brand_name=data["brand_name"],
        aliases=data.get("aliases", []),
        cta_principles=data.get("cta_principles", []),
        blocked_words=data.get("blocked_words", []),
        tone_guidelines=data.get("tone_guidelines", ""),
        brand_identity=data.get("brand_identity", ""),
        languages=data.get("languages", {}),
        industry=data.get("industry", ""),
        target_audience=data.get("target_audience", ""),
        personality=data.get("personality", ""),
        platforms=platforms,
        automation=_extract_automation(data.get("automation")),
    )


# ---------------------------------------------------------------------------
# Multi-brand profile helpers
# ---------------------------------------------------------------------------


def load_brand_profiles() -> dict[str, BrandProfile]:
    """Load all brand profiles from ``~/.automedia/brand_profiles.yaml``.

    Returns
    -------
    dict[str, BrandProfile]
        Mapping of brand key → :class:`BrandProfile` for every valid profile
        in the file.  Returns an empty dict when the file is missing, empty,
        or contains no valid profiles — never raises.

    Notes
    -----
    The YAML file is expected to be a flat mapping::

        brand-key:
          brand_name: ...
          aliases: [...]
          ...
    """
    path = _BRAND_PROFILES_PATH
    if not path.is_file():
        return {}

    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    profiles: dict[str, BrandProfile] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        if not validate_brand_profile(value):
            continue
        platforms = _extract_platforms(value.get("platforms"))
        _validate_platforms(platforms)
        profiles[key] = BrandProfile(
            brand_name=value.get("brand_name", ""),
            aliases=value.get("aliases", []),
            cta_principles=value.get("cta_principles", []),
            blocked_words=value.get("blocked_words", []),
            tone_guidelines=value.get("tone_guidelines", ""),
            brand_identity=value.get("brand_identity", ""),
            languages=value.get("languages", {}),
            industry=value.get("industry", ""),
            target_audience=value.get("target_audience", ""),
            personality=value.get("personality", ""),
            platforms=platforms,
            automation=_extract_automation(value.get("automation")),
        )
    return profiles


def save_brand_profile(brand_name: str, data: dict[str, Any]) -> None:
    """Save or update a single brand profile.

    Parameters
    ----------
    brand_name:
        Key under which the profile is stored.
    data:
        Raw profile dict.  Must pass :func:`validate_brand_profile`.

    Raises
    ------
    ValueError
        When *data* fails validation.
    """
    if not validate_brand_profile(data):
        msg = f"Brand profile validation failed for {brand_name!r}"
        raise ValueError(msg)

    path = _BRAND_PROFILES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing profiles
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}

    existing[brand_name] = data

    # Atomic write — write to temp, then replace
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(existing, fh)
    tmp_path.replace(path)


def list_brand_names() -> list[str]:
    """Return sorted list of configured brand names.

    Returns
    -------
    list[str]
        Sorted brand keys.  Empty list when no brands are configured (not
        an error).
    """
    return sorted(load_brand_profiles().keys())
