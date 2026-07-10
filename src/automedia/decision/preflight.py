"""Preflight phase transition checker.

Validates that all required nodes for a phase are complete before
allowing a transition to the next phase.
"""

from __future__ import annotations

from automedia.decision import dependency


def _get_nodes_for_phase(phase: str, mode: str) -> list[int]:
    """Return node IDs belonging to a specific phase string (``"0"``, ``"1b"``, etc.)."""
    nodes = dependency.list_all_nodes()
    phase_prefix = phase.rstrip("bs")
    return [
        n["node_id"]
        for n in nodes
        if str(n.get("phase", "")).startswith(phase_prefix) and n.get("mode") in (mode, "both")
    ]


def check(
    next_phase: str,
    mode: str,
    completed_set: set[int],
) -> list[str]:
    """Check whether all nodes for the phase before *next_phase* are complete.

    Returns a list of warning messages (empty = OK).
    """
    warnings: list[str] = []

    # Map phase to prior phases
    phase_order = ["0", "1b", "1s", "2", "2.5", "3", "4"]
    try:
        idx = phase_order.index(next_phase.rstrip("bs"))
    except ValueError:
        return [f"Unknown phase: {next_phase}"]

    prior_phases = phase_order[:idx]
    for p in prior_phases:
        required_ids = _get_nodes_for_phase(p, mode)
        for nid in required_ids:
            if nid not in completed_set:
                node = dependency.get_node(nid)
                name = node["name"] if node else f"node_{nid}"
                warnings.append(f"Phase {p}: node '{name}' ({nid}) not completed")

    return warnings
