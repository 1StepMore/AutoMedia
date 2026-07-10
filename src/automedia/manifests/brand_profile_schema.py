"""Brand profile schema — dataclass and loader for ``brand-profile.yaml``.

Public API
----------
- ``BrandProfile`` dataclass
- ``load_brand_profile(path) -> BrandProfile``
- ``validate_brand_profile(data) -> bool``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class BrandProfile:
    """Typed representation of a brand-profile.yaml file.

    All fields have safe defaults so that partial YAML files do not cause
    crashes.
    """

    brand_name: str = ""
    aliases: list[str] = field(default_factory=list)
    cta_principles: list[str] = field(default_factory=list)
    blocked_words: list[str] = field(default_factory=list)
    tone_guidelines: str = ""
    brand_identity: str = ""
    languages: dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_KEYS: tuple[str, ...] = ("brand_name",)


def validate_brand_profile(data: dict) -> bool:
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

    return BrandProfile(
        brand_name=data["brand_name"],
        aliases=data.get("aliases", []),
        cta_principles=data.get("cta_principles", []),
        blocked_words=data.get("blocked_words", []),
        tone_guidelines=data.get("tone_guidelines", ""),
        brand_identity=data.get("brand_identity", ""),
        languages=data.get("languages", {}),
    )
