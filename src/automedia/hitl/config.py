"""HITL Framework — config loader: preset loading, overrides merge, executor resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Static presets that do NOT require a NodeProvider.
_STATIC_PRESETS: dict[str, list[dict[str, Any]]] = {}

# Build the test_automated preset from automated.yaml at import time.
_automated_yaml = Path(__file__).parent / "presets" / "automated.yaml"
if _automated_yaml.is_file():
    with open(_automated_yaml, encoding="utf-8") as _fh:
        _parsed = yaml.safe_load(_fh)
    if isinstance(_parsed, dict):
        _nodes_dict = _parsed.get("nodes", {})
        if isinstance(_nodes_dict, dict):
            _test_nodes = [
                {"name": name, "autoset": cfg.get("autoset", "agent")}
                for name, cfg in _nodes_dict.items()
                if isinstance(cfg, dict)
            ]
            # brand_questionnaire is human in the test_automated preset
            for _node in _test_nodes:
                if _node["name"] == "brand_questionnaire":
                    _node["autoset"] = "human"
            _STATIC_PRESETS["test_automated"] = _test_nodes


class HITLConfig:
    """HITL node configuration — loads presets, merges overrides, resolves executors.

    Parameters
    ----------
    preset_name:
        Name of the built-in preset (``"test_automated"``, ``"automated"``, etc.).
    overrides_dir:
        Optional path to a directory containing ``*.yaml`` override files.
        Defaults to ``~/.automedia/hitl/overrides/``.
    node_provider:
        Deprecated. Kept for backward compatibility; value is ignored.
    """

    def __init__(
        self,
        preset_name: str = "automated",
        overrides_dir: str | None = None,
        node_provider: Any = None,  # noqa: ANN401 — kept for backward compat
    ) -> None:
        """Initialize from a preset, then merge user overrides.

        Args:
            preset_name: Name of the built-in HITL preset.
            overrides_dir: Optional override directory path.
            node_provider: Deprecated — kept for backward compatibility.
        """
        self._nodes: dict[str, dict[str, Any]] = {}

        # 1. Load preset
        preset_nodes = self._load_preset(preset_name)
        for n in preset_nodes:
            self._nodes[n["name"]] = dict(n)

        # 2. Merge overrides
        self._apply_overrides(overrides_dir or self._default_overrides_dir())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_executor(self, node_name: str) -> str:
        """Return ``"human"`` or ``"agent"`` for *node_name*.

        Raises ``KeyError`` when *node_name* is unknown.
        """
        node = self._nodes.get(node_name)
        if node is None:
            raise KeyError(f"Unknown HITL node: {node_name!r}")
        return node.get("autoset", "agent")

    def set_executor(self, node_name: str, executor: str) -> None:
        """Override the executor for *node_name*.

        Raises ``KeyError`` for unknown nodes, ``ValueError`` for invalid executor.
        """
        if executor not in ("human", "agent"):
            raise ValueError(f"Executor must be 'human' or 'agent', got {executor!r}")
        if node_name not in self._nodes:
            raise KeyError(f"Unknown HITL node: {node_name!r}")
        self._nodes[node_name]["autoset"] = executor

    def list_nodes(self) -> list[dict[str, Any]]:
        """Return all configured nodes with their current configuration."""
        return list(self._nodes.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_preset(self, name: str) -> list[dict[str, Any]]:
        """Load a preset by name — checks static, then filesystem."""
        # Static presets
        if name in _STATIC_PRESETS:
            return _STATIC_PRESETS[name]

        # Filesystem presets
        preset_path = Path(__file__).parent / "presets" / f"{name}.yaml"
        if preset_path.is_file():
            with open(preset_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                return []
            nodes = data.get("nodes", {})
            if isinstance(nodes, dict):
                return [
                    {"name": n, "autoset": c.get("autoset", "agent")}
                    for n, c in nodes.items()
                    if isinstance(c, dict)
                ]
            return nodes if isinstance(nodes, list) else []

        raise FileNotFoundError(f"HITL preset not found: {name!r}")

    def _apply_overrides(self, overrides_dir: str) -> None:
        """Merge user override YAML files into the node config."""
        override_path = Path(overrides_dir)
        if not override_path.is_dir():
            return

        for yaml_file in sorted(override_path.glob("*.yaml")):
            with open(yaml_file, encoding="utf-8") as fh:
                overrides = yaml.safe_load(fh)
            if not isinstance(overrides, dict):
                continue
            for node_name, node_config in overrides.items():
                if node_name in self._nodes and isinstance(node_config, dict):
                    self._nodes[node_name].update(node_config)

    @staticmethod
    def _default_overrides_dir() -> str:
        """Return the default HITL overrides directory path."""
        return os.path.join(os.path.expanduser("~"), ".automedia", "hitl", "overrides")
