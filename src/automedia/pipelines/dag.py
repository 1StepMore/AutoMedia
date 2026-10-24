"""Gate dependency graph for the AutoMedia pipeline.

The AUTHORITY for gate ORDER is :mod:`automedia.pipelines.gate_plan`; this
module describes the dependency EDGES among the same gates.  A test asserts
the topological order of every mode's gate subset reproduces the plan's list
exactly, so "canonical" is a verified claim rather than a label (issue #282).

This module is a pure, declarative description of the pipeline's gate
dependency graph: ``AUTO_GATE_DAG`` maps every gate name to a ``GateNode``
carrying its ``depends_on`` edges, ``track``, and ``failure_mode``. Two pure
helpers operate on it:

- ``topological_order`` — topologically orders a mode-scoped gate-name list
  (``present-parents`` semantics: parents outside the mode subset are ignored).
  For every mode in :data:`automedia.pipelines.gate_plan.MODE_GATE_NAMES` this
  reproduces the plan's linear gate-name list byte-exact.
- ``downstream`` — the reverse-topological closure of a gate: every gate that
  transitively depends on it, ordered dependencies-before-dependents.

DECLARATION ORDER IS SEMANTIC (pinned). ``AUTO_GATE_DAG``'s insertion order
is the canonical gate order — ``topological_order`` uses it as its tie-break,
so two ready gates always resolve the same way and a shuffled caller input
cannot change the result.  That means REORDERING THE DICT IS A BEHAVIOUR
CHANGE, which is exactly why it is not left implicit:

* :data:`GATE_ORDER` materialises the order as data, so it can be asserted;
* ``tests/test_runner/test_dag.py`` pins the literal 26-name sequence, so a
  reorder fails a test instead of silently changing pipeline behaviour;
* every edge must point at a gate declared EARLIER (a test enforces it), which
  is what makes the insertion order a valid topological order by construction.

Import-isolation contract (Metis G7): this module must NOT import anything
from ``automedia.pipelines.runner`` — a fresh interpreter importing only
``dag`` must not load the runner.  The only ``automedia`` import permitted is
``gate_plan``, which itself imports nothing from ``automedia``.

The ``failure_mode`` strings are literal values mirrored from the registered
gate classes; tests verify they agree with the registry.
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
# INSERTION ORDER IS THE CANONICAL GATE ORDER (see the module docstring): pre-gate
# → CW → copy track (G0..G6) + video track (V0..V7) → H0 → lifecycle track
# (L1..L4) → repurpose track (P1..P4).  Every edge points at an earlier gate, so
# filtering this order to any subset yields a valid topological order of that
# subset — and ``topological_order`` uses it as its tie-break.
#
# Reordering these lines changes pipeline behaviour.  GATE_ORDER below pins the
# sequence so that cannot happen silently.
# ---------------------------------------------------------------------------

AUTO_GATE_DAG: dict[str, GateNode] = {
    "pre-gate": GateNode(name="pre-gate", track="qa", depends_on=(), failure_mode="stop"),
    "CW": GateNode(name="CW", track="copy", depends_on=("pre-gate",), failure_mode="stop"),
    "G0": GateNode(name="G0", track="copy", depends_on=("CW",), failure_mode="retry"),
    "G1": GateNode(name="G1", track="copy", depends_on=("G0",), failure_mode="retry"),
    "G2": GateNode(name="G2", track="copy", depends_on=("G1",), failure_mode="retry"),
    "G3": GateNode(name="G3", track="copy", depends_on=("G2",), failure_mode="stop"),
    "G4": GateNode(name="G4", track="copy", depends_on=("G3",), failure_mode="stop"),
    "G5": GateNode(name="G5", track="copy", depends_on=("G4",), failure_mode="stop"),
    "G6": GateNode(name="G6", track="copy", depends_on=("G3",), failure_mode="retry"),
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
    "P1": GateNode(name="P1", track="qa", depends_on=("H0",), failure_mode="retry"),
    "P2": GateNode(name="P2", track="qa", depends_on=("P1",), failure_mode="retry"),
    "P3": GateNode(name="P3", track="qa", depends_on=("P2",), failure_mode="retry"),
    "P4": GateNode(name="P4", track="qa", depends_on=("P3",), failure_mode="retry"),
}

#: The canonical gate order, as an explicit tuple.
#:
#: This is ``AUTO_GATE_DAG``'s insertion order materialised as data.  It exists
#: because that order is SEMANTIC (``topological_order`` tie-breaks on it) and
#: a semantic ordering that only lives in dict insertion order is one careless
#: edit away from a silent behaviour change.
#:
#: A test pins this exact sequence.  Do NOT edit it to match a reordered dict —
#: if the pipeline order genuinely changes, the gate plan (``MODE_GATE_NAMES``)
#: changes first and this tuple follows with its test updated deliberately.
GATE_ORDER: tuple[str, ...] = tuple(AUTO_GATE_DAG)


def _validate_declaration_order() -> None:
    """Fail at import if the DAG contradicts its own declaration order.

    Two invariants make declaration order a usable tie-break:

    1. :data:`GATE_ORDER` covers exactly the DAG's keys (no drift);
    2. every ``depends_on`` parent is declared EARLIER than its dependent —
       which is what makes "filter the declaration order to a subset" a valid
       topological order rather than an accident.

    Checked here, not only in tests, because ``dag`` is a leaf module with no
    side effects: a contradiction is a programming error that should never
    survive to runtime, and an import-time check cannot be skipped by a caller
    that does not run the suite.
    """
    position = {name: index for index, name in enumerate(GATE_ORDER)}
    if set(position) != set(AUTO_GATE_DAG):
        raise RuntimeError(
            "GATE_ORDER drifted from AUTO_GATE_DAG: "
            f"missing={sorted(set(AUTO_GATE_DAG) - set(position))} "
            f"extra={sorted(set(position) - set(AUTO_GATE_DAG))}"
        )
    for name, node in AUTO_GATE_DAG.items():
        for parent in node.depends_on:
            if parent not in position:
                raise RuntimeError(f"{name} depends on unknown gate {parent!r}")
            if position[parent] > position[name]:
                raise RuntimeError(
                    f"{name} (position {position[name]}) depends on {parent} "
                    f"(position {position[parent]}), which is declared LATER — "
                    "declaration order is the topological tie-break, so an edge "
                    "must point backwards"
                )


_validate_declaration_order()


def topological_order(dag: dict[str, GateNode], mode_gates: list[str]) -> list[str]:
    """Topologically order a mode-scoped gate-name subset of ``dag``.

    Only gates present in ``mode_gates`` are considered. A gate is "ready" when
    every parent in ``depends_on`` that is ALSO in ``mode_gates`` has already
    been emitted; parents outside the mode subset are ignored ("present-parents
    semantics" — this is what lets ``qa_only``/``text_only`` run without
    pre-gate/CW).

    TIE-BREAK: among ready gates, emit in **``dag`` declaration order**, not in
    the caller's order.  This is what makes the result a property of the graph
    rather than of the input list:

    * With the old input-order tie-break, a mode's declared list was the only
      thing that ever produced the expected answer, so "topological_order
      reproduces the plan" was true by construction and proved nothing.  Worse,
      a shuffled input could legally emit ``G6`` before ``CW`` (``G6``'s parent
      ``G5`` is in no preset, so it looked ready) — a valid topological order
      that would make G6 check content CW had not written yet.
    * With declaration order, any input permutation of the same gate set yields
      the same output, and that output is exactly the canonical gate order.

    Raises:
        ValueError: If a cycle or an unsatisfiable dependency leaves gates
            un-emittable.
    """
    canonical = [name for name in dag if name in set(mode_gates)]
    emitted: list[str] = []
    remaining: list[str] = list(canonical)
    while remaining:
        progress = False
        for gate in list(remaining):
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


__all__ = [
    "AUTO_GATE_DAG",
    "GATE_ORDER",
    "GateNode",
    "downstream",
    "topological_order",
]
