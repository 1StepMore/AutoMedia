"""Canonical gate DAG for the AutoMedia pipeline.

Part of the graph-engineering-rollout Wave 1 (P0 equivalence layer).

This module is a pure, declarative description of the pipeline's gate
dependency graph: ``AUTO_GATE_DAG`` maps every gate name to a ``GateNode``
carrying its ``depends_on`` edges, ``track``, and ``failure_mode``. Two pure
helpers operate on it:

- ``topological_order`` — topologically orders a mode-scoped gate-name list
  (``present-parents`` semantics: parents outside the mode subset are ignored).
  For every mode in ``automedia.pipelines.runner._MODE_MAP`` this reproduces
  the existing linear gate-name list byte-exact, proving the DAG is a drop-in
  replacement for the hardcoded mode lists.
- ``downstream`` — the reverse-topological closure of a gate: every gate that
  transitively depends on it, ordered dependencies-before-dependents.

Import-isolation contract (Metis G7): this module must NOT import anything
from ``automedia.pipelines.runner`` (or any other ``automedia`` subpackage) —
it is a standalone declarative layer. The ``failure_mode`` strings are literal
values mirrored from the registered gate classes; tests verify they agree with
the registry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateNode:
    """A single gate in the canonical pipeline DAG.

    Attributes:
        name: The gate's canonical name (e.g. ``"G6"``, ``"pre-gate"``).
        track: One of ``"copy"``, ``"video"``, ``"lifecycle"``, ``"qa"``.
        depends_on: Gates that must complete before this gate runs.
        failure_mode: Mirrors the registered gate class's ``_failure_mode`` —
            ``"stop"`` halts the pipeline, ``"retry"`` triggers regeneration.
        async_parallel: Documentation-only metadata (V0 may fork off CW in
            parallel); never used for execution semantics.
    """

    name: str
    track: str
    depends_on: tuple[str, ...]
    failure_mode: str
    async_parallel: bool = False


# ---------------------------------------------------------------------------
# Canonical gate DAG
#
# Dict insertion order is the canonical gate order: pre-gate → CW → copy track
# (G0..G6) + video track (V0..V7) → H0 → lifecycle track (L1..L4) → repurpose
# track (P1..P4). Every edge respects this order, so filtering it to any
# subset yields a valid topological order of that subset.
# ---------------------------------------------------------------------------

AUTO_GATE_DAG: dict[str, GateNode] = {
    "pre-gate": GateNode(name="pre-gate", track="qa", depends_on=(), failure_mode="stop"),
    "CW": GateNode(name="CW", track="copy", depends_on=("pre-gate",), failure_mode="stop"),
    "G0": GateNode(name="G0", track="copy", depends_on=("CW",), failure_mode="stop"),
    "G1": GateNode(name="G1", track="copy", depends_on=("G0",), failure_mode="retry"),
    "G2": GateNode(name="G2", track="copy", depends_on=("G1",), failure_mode="retry"),
    "G3": GateNode(name="G3", track="copy", depends_on=("G2",), failure_mode="stop"),
    "G4": GateNode(name="G4", track="copy", depends_on=("G3",), failure_mode="stop"),
    "G5": GateNode(name="G5", track="copy", depends_on=("G4",), failure_mode="stop"),
    "G6": GateNode(name="G6", track="copy", depends_on=("G5",), failure_mode="retry"),
    "V0": GateNode(
        name="V0",
        track="video",
        depends_on=("CW",),
        failure_mode="stop",
        async_parallel=True,
    ),
    "V1": GateNode(name="V1", track="video", depends_on=("V0",), failure_mode="stop"),
    "V2": GateNode(name="V2", track="video", depends_on=("V1",), failure_mode="stop"),
    "V3": GateNode(name="V3", track="video", depends_on=("V2",), failure_mode="stop"),
    "V4": GateNode(name="V4", track="video", depends_on=("V3",), failure_mode="stop"),
    "V5": GateNode(name="V5", track="video", depends_on=("V4",), failure_mode="retry"),
    "V6": GateNode(name="V6", track="video", depends_on=("V5",), failure_mode="stop"),
    "V7": GateNode(name="V7", track="video", depends_on=("V6",), failure_mode="stop"),
    "H0": GateNode(name="H0", track="qa", depends_on=("G6", "V7"), failure_mode="stop"),
    "L1": GateNode(
        name="L1",
        track="lifecycle",
        depends_on=("H0", "G6", "V7"),
        failure_mode="stop",
    ),
    "L2": GateNode(name="L2", track="lifecycle", depends_on=("L1",), failure_mode="stop"),
    "L3": GateNode(name="L3", track="lifecycle", depends_on=("L2",), failure_mode="stop"),
    "L4": GateNode(name="L4", track="lifecycle", depends_on=("L3",), failure_mode="stop"),
    "P1": GateNode(name="P1", track="qa", depends_on=("L4",), failure_mode="retry"),
    "P2": GateNode(name="P2", track="qa", depends_on=("P1",), failure_mode="retry"),
    "P3": GateNode(name="P3", track="qa", depends_on=("P2",), failure_mode="retry"),
    "P4": GateNode(name="P4", track="qa", depends_on=("P3",), failure_mode="retry"),
}


def topological_order(dag: dict[str, GateNode], mode_gates: list[str]) -> list[str]:
    """Topologically order a mode-scoped gate-name subset of ``dag``.

    Only gates present in ``mode_gates`` are considered. A gate is "ready" when
    every parent in ``depends_on`` that is ALSO in ``mode_gates`` has already
    been emitted; parents outside the mode subset are ignored ("present-parents
    semantics" — this is what lets ``qa_only``/``text_only`` run without
    pre-gate/CW). Among ready gates, emit in ``mode_gates`` order, which
    reproduces the runner's existing linear lists byte-exact for every mode.

    Raises:
        ValueError: If a cycle or an unsatisfiable dependency leaves gates
            un-emittable.
    """
    emitted: list[str] = []
    remaining: list[str] = [g for g in mode_gates if g in dag]
    while remaining:
        progress = False
        for gate in list(remaining):  # iterate in mode_gates order
            parents = dag[gate].depends_on
            if all(p not in mode_gates or p in emitted for p in parents):
                emitted.append(gate)
                remaining.remove(gate)
                progress = True
        if not progress:
            raise ValueError(f"Cycle or unsatisfiable dependency: {remaining}")
    return emitted


def downstream(dag: dict[str, GateNode], gate: str) -> list[str]:
    """Reverse-topological closure: every gate transitively depending on ``gate``.

    Collects all gates reachable from ``gate`` via forward (depends-on) edges —
    i.e. the gates that depend, directly or transitively, on ``gate`` — and
    returns them in dependency-before-dependent order. Because every DAG edge
    respects the canonical ``AUTO_GATE_DAG`` insertion order, filtering that
    canonical order to the reachable set is a valid topological order.

    The queried gate itself is not part of its own downstream closure.
    """
    # Forward adjacency: parent -> list of dependents, in canonical order.
    forward: dict[str, list[str]] = {name: [] for name in dag}
    for name, node in dag.items():
        for parent in node.depends_on:
            if parent in dag:
                forward[parent].append(name)

    # BFS/DFS over forward edges to find the reachable (downstream) set.
    reachable: set[str] = set()
    stack = list(forward.get(gate, ()))
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        stack.extend(forward.get(current, ()))

    # Canonical order filtered to the reachable set = valid topological order.
    return [name for name in dag if name in reachable]
