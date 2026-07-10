"""Overrides subsystem — loads user custom Gate rules and LLM prompt templates.

Two-layer model:
    1. Built-in defaults (from ``automedia/manifests/``)
    2. User overrides (from ``~/.automedia/overrides/``)

Public API
----------
- ``OverridesLoader(overrides_dir=None)``
  - ``load_rules(brand=None) -> list[dict]``
  - ``load_prompts(brand=None) -> dict[str, str]``
"""

from __future__ import annotations

from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_overrides_dir() -> Path:
    """Return ``~/.automedia/overrides`` (resolved lazily)."""
    return Path.home() / ".automedia" / "overrides"


def _load_yaml_files(directory: Path) -> list[dict]:
    """Load every ``*.yaml`` / ``*.yml`` in *directory* as individual rule dicts.

    Each file may contain a single dict (one rule) or a list of dicts
    (multiple rules).  Returns a flat list of all rule dicts found.

    Returns an empty list when the directory does not exist or contains
    no valid YAML files.
    """
    if not directory.is_dir():
        return []

    rules: list[dict] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix in (".yaml", ".yml"):
            try:
                with open(entry, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
            except Exception:  # noqa: S112 — skip malformed files
                continue

            if isinstance(data, dict):
                rules.append(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        rules.append(item)
    return rules


def _load_j2_files(directory: Path) -> dict[str, str]:
    """Load all ``*.j2`` files in *directory* as ``{stem: content}`` mapping.

    Returns an empty dict when the directory does not exist.
    """
    if not directory.is_dir():
        return {}

    prompts: dict[str, str] = {}
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix == ".j2":
            try:
                with open(entry, encoding="utf-8") as fh:
                    prompts[entry.stem] = fh.read()
            except Exception:  # noqa: S112 — skip malformed files
                continue
    return prompts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class OverridesLoader:
    """Load user-override Gate rules and LLM prompt templates.

    Parameters
    ----------
    overrides_dir:
        Root of the overrides directory.  Defaults to
        ``~/.automedia/overrides``.  Non-existent directories are silently
        skipped (empty results returned).
    """

    def __init__(self, overrides_dir: str | Path | None = None) -> None:
        self._overrides_dir = (
            Path(overrides_dir) if overrides_dir is not None else _default_overrides_dir()
        )

    # -- Properties ---------------------------------------------------------

    @property
    def overrides_dir(self) -> Path:
        """The resolved overrides root directory."""
        return self._overrides_dir

    @property
    def rules_dir(self) -> Path:
        """``<overrides_dir>/rules``."""
        return self._overrides_dir / "rules"

    @property
    def prompts_dir(self) -> Path:
        """``<overrides_dir>/prompts``."""
        return self._overrides_dir / "prompts"

    # -- Public methods -----------------------------------------------------

    def load_rules(self, brand: str | None = None) -> list[dict]:
        """Load custom Gate rules from ``<overrides_dir>/rules/*.yaml``.

        When *brand* is supplied, only rules whose ``brand`` key matches
        (case-insensitive) are returned.  Rules without a ``brand`` key are
        always included (they are global).

        Returns an empty list when the rules directory does not exist.
        """
        all_rules = _load_yaml_files(self.rules_dir)
        if brand is None:
            return all_rules

        brand_lower = brand.lower()
        filtered: list[dict] = []
        for rule in all_rules:
            rule_brand = rule.get("brand")
            if rule_brand is None or str(rule_brand).lower() == brand_lower:
                filtered.append(rule)
        return filtered

    def load_prompts(self, brand: str | None = None) -> dict[str, str]:
        """Load custom LLM prompt templates from ``<overrides_dir>/prompts/*.j2``.

        When *brand* is supplied, brand-scoped prompts are loaded first from
        ``<overrides_dir>/prompts/<brand>/*.j2`` (if that subdirectory exists),
        then merged with global prompts from ``<overrides_dir>/prompts/*.j2``.
        Brand-scoped prompts take precedence over global ones with the same
        stem name.

        Returns an empty dict when the prompts directory does not exist.
        """
        # Global prompts (top-level .j2 files only)
        global_prompts = _load_j2_files(self.prompts_dir)

        if brand is None:
            return global_prompts

        # Brand-scoped prompts from subdirectory
        brand_prompts_dir = self.prompts_dir / brand.lower()
        brand_prompts = _load_j2_files(brand_prompts_dir)

        # Merge: global as base, brand-scoped overrides
        merged = {**global_prompts, **brand_prompts}
        return merged
