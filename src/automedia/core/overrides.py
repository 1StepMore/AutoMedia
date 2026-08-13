"""Overrides subsystem — loads user custom Gate rules and LLM prompt templates.

Two-layer model:
    1. Built-in defaults (from ``automedia/manifests/``)
    2. User overrides (from ``~/.automedia/overrides/``)

Public API
----------
- ``OverridesLoader(overrides_dir=None)``
  - ``load_rules(brand=None) -> list[dict]``
  - ``load_gate_modifiers(brand=None) -> dict[str, Any] | None``
  - ``load_prompts(brand=None, platform=None) -> dict[str, str]``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from automedia.core.paths import get_user_config_dir

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_overrides_dir() -> Path:
    """Return ``~/.automedia/overrides`` (resolved lazily)."""
    return get_user_config_dir() / "overrides"


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
            except Exception:  # noqa: S112, BLE001 — skip malformed files
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
            except Exception:  # noqa: S112, BLE001 — skip malformed files
                continue
    return prompts


# ---------------------------------------------------------------------------
# Gate modifiers helpers
# ---------------------------------------------------------------------------


def _merge_gate_modifiers(rules: list[dict]) -> dict[str, Any] | None:
    """Merge ``gates`` keys from *rules* with union semantics.

    For each rule that contains a ``gates`` dict, the following keys are
    merged:

    * **include** — union: a gate is added if *any* rule requests it.
    * **exclude** — union: a gate is removed if *any* rule excludes it.
    * **override_failure_mode** — last-rule wins for conflicting keys.

    Parameters
    ----------
    rules:
        List of rule dicts (as returned by ``load_rules()``).

    Returns
    -------
    dict[str, Any] or None
        Merged modifiers dict with ``include``, ``exclude``, and/or
        ``override_failure_mode`` keys, or ``None`` if no rule has
        a ``gates`` key.
    """
    combined: dict[str, set[str]] = {"include": set(), "exclude": set()}
    override_fm: dict[str, str] = {}
    has_modifiers = False

    for rule in rules:
        gates_cfg = rule.get("gates")
        if not isinstance(gates_cfg, dict):
            continue

        inc = gates_cfg.get("include", [])
        if isinstance(inc, list):
            combined["include"].update(inc)
            if inc:
                has_modifiers = True

        exc = gates_cfg.get("exclude", [])
        if isinstance(exc, list):
            combined["exclude"].update(exc)
            if exc:
                has_modifiers = True

        ofm = gates_cfg.get("override_failure_mode", {})
        if isinstance(ofm, dict):
            override_fm.update(ofm)
            if ofm:
                has_modifiers = True

    if not has_modifiers:
        return None

    result: dict[str, Any] = {}
    if combined["include"]:
        result["include"] = list(combined["include"])
    if combined["exclude"]:
        result["exclude"] = list(combined["exclude"])
    if override_fm:
        result["override_failure_mode"] = override_fm
    return result


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

    def load_gate_modifiers(self, brand: str | None = None) -> dict[str, Any] | None:
        """Load and merge gate modifiers from override rules.

        Collects all rules that have a ``gates`` key (via ``load_rules()``),
        then merges them with union semantics:

        * **include** — union across all matching rules.
        * **exclude** — union across all matching rules.
        * **override_failure_mode** — last-matching rule wins for a given gate.

        When *brand* is supplied, only rules matching that brand (plus
        global rules without a brand key) are considered.

        Returns
        -------
        dict[str, Any] or None
            Merged modifiers dict, or ``None`` when no rule defines
            a ``gates`` key.
        """
        rules = self.load_rules(brand=brand)
        return _merge_gate_modifiers(rules)

    def load_prompts(
        self,
        brand: str | None = None,
        platform: str | None = None,
    ) -> dict[str, str]:
        """Load custom LLM prompt templates from ``<overrides_dir>/prompts/*.j2``.

        When *platform* is supplied, platform-scoped prompts are loaded from
        ``<overrides_dir>/prompts/<platform>/*.j2`` and merged over global
        prompts (platform takes precedence over global).

        When *brand* is supplied, brand-scoped prompts are loaded from
        ``<overrides_dir>/prompts/<brand>/*.j2`` and merged on top of any
        platform-scoped prompts (brand takes highest precedence).

        Resolution order (lowest → highest priority):
        1. Global prompts from ``<overrides_dir>/prompts/*.j2``
        2. Platform-scoped prompts from ``<overrides_dir>/prompts/<platform>/*.j2``
        3. Brand-scoped prompts from ``<overrides_dir>/prompts/<brand>/*.j2``

        Returns an empty dict when the prompts directory does not exist.
        """
        # Global prompts (top-level .j2 files only)
        result = _load_j2_files(self.prompts_dir)

        if platform is not None:
            platform_prompts_dir = self.prompts_dir / platform.lower()
            platform_prompts = _load_j2_files(platform_prompts_dir)
            result.update(platform_prompts)

        if brand is not None:
            brand_prompts_dir = self.prompts_dir / brand.lower()
            brand_prompts = _load_j2_files(brand_prompts_dir)
            result.update(brand_prompts)

        return result
