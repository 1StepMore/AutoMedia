"""Dependency graph loader for the 27-node Decision Layer workflow.

Reads ``solution-wise/process/dependency-graph.yaml`` and provides
dependency validation for node execution order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_GRAPH_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "solution-wise"
    / "process"
    / "dependency-graph.yaml"
)


def _load_graph() -> dict[str, Any]:
    """Load and cache the dependency graph YAML."""
    if not _GRAPH_PATH.is_file():
        return {"nodes": []}
    with open(_GRAPH_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {"nodes": []}


def get_node(node_id: int) -> dict[str, Any] | None:
    """Return a single node dict by *node_id*, or ``None``."""
    for n in _load_graph().get("nodes", []):
        if n.get("node_id") == node_id:
            return n
    return None


def get_dependencies(node_id: int) -> list[int]:
    """Return the list of prerequisite node IDs for *node_id*."""
    node = get_node(node_id)
    if node is None:
        return []
    return node.get("dependencies", [])


def validate_prerequisites(
    node_id: int,
    completed_set: set[int],
) -> tuple[bool, list[int]]:
    """Check whether all prerequisites for *node_id* are in *completed_set*.

    Returns ``(ok, missing_ids)``.
    """
    deps = get_dependencies(node_id)
    missing = [d for d in deps if d not in completed_set]
    return len(missing) == 0, missing


def get_nodes_for_mode(mode: str) -> list[dict[str, Any]]:
    """Return all nodes that belong to a given *mode* (``"build"``, ``"scale"``, ``"both"``)."""
    return [n for n in _load_graph().get("nodes", []) if n.get("mode") in (mode, "both")]


def get_required_nodes_for_mode(mode: str) -> set[int]:
    """Return the set of required (non-optional) node IDs for *mode*."""
    optional_ids = {
        int(n["node_id"])
        for n in _load_graph().get("nodes", [])
        if n.get("optional") and n.get("node_id") is not None
    }
    all_ids = {int(n["node_id"]) for n in get_nodes_for_mode(mode) if n.get("node_id") is not None}
    return all_ids - optional_ids


def list_all_nodes() -> list[dict[str, Any]]:
    """Return the full list of node definitions."""
    return _load_graph().get("nodes", [])
