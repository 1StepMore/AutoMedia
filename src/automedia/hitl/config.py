"""HITL Framework — config loader: preset loading, overrides merge, executor resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from automedia.hitl.protocol import NodeProvider


def _classify(node_name: str) -> str:
    """Classify a node by name into decision / preference / execution."""
    decision_keywords = (
        "diagnosis",
        "positioning",
        "strategy",
        "optimization",
        "questionnaire",
        "routing",
        "confirmation",
        "planning",
        "audit",
        "refresh",
    )
    preference_keywords = (
        "segmentation",
        "persona",
        "audience",
        "calendar",
        "tracking",
        "revalidation",
        "deepening",
    )
    for kw in decision_keywords:
        if kw in node_name:
            return "decision"
    for kw in preference_keywords:
        if kw in node_name:
            return "preference"
    return "execution"


# Static presets that do NOT require a NodeProvider.
_STATIC_PRESETS: dict[str, list[dict[str, Any]]] = {}


def _build_automated_preset(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the ``test_automated`` preset from raw node dicts."""
    preset = [
        {"name": node["name"], "type": _classify(node["name"]), "autoset": "agent"}
        for node in nodes
    ]
    # Override brand_questionnaire to human
    for node in preset:
        if node["name"] == "brand_questionnaire":
            node["autoset"] = "human"
    return preset


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
        Optional ``NodeProvider`` that supplies decision node metadata.
        When provided (and *preset_name* is ``"test_automated"``), auto-generated
        presets are built from the provider's node list.  When ``None``,
        only static and filesystem presets are available.
    """

    def __init__(
        self,
        preset_name: str = "automated",
        overrides_dir: str | None = None,
        node_provider: NodeProvider | None = None,
    ) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._node_provider = node_provider

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

    def _get_dynamic_presets(self) -> dict[str, list[dict[str, Any]]]:
        """Build presets that require a ``NodeProvider``.

        Returns an empty dict when no provider is wired.
        """
        if self._node_provider is None:
            return {}
        nodes = self._node_provider.list_all_nodes()
        return {"test_automated": _build_automated_preset(nodes)}

    def _load_preset(self, name: str) -> list[dict[str, Any]]:
        """Load a preset by name — checks dynamic, static, then filesystem."""
        # Dynamic presets (require NodeProvider)
        dynamic = self._get_dynamic_presets()
        if name in dynamic:
            return dynamic[name]

        # Static presets
        if name in _STATIC_PRESETS:
            return _STATIC_PRESETS[name]

        # Filesystem presets
        preset_path = Path(__file__).parent / "presets" / f"{name}.yaml"
        if preset_path.is_file():
            with open(preset_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            return data.get("nodes", []) if isinstance(data, dict) else []

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
        return os.path.join(os.path.expanduser("~"), ".automedia", "hitl", "overrides")
