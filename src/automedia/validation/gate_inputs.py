"""Static input-reachability audit for gates (issue #285).

Several V gates declare "these context keys are my inputs" via
``missing_input_result(gate, ctx, REQUIRED_KEYS)``.  When nothing in the
pipeline ever writes those keys, the gate honestly reports ``skipped`` — but a
headline that still says "33 quality gates" is misleading: some of them cannot
inspect anything in this pipeline, by construction.

This module answers that question WITHOUT RUNNING anything and WITHOUT
inventing data:

* which keys each gate declares as required (from the ``missing_input_result``
  call sites, statically);
* which keys some producer actually writes (``<ctx>["key"] = ...`` assignments
  in the pipeline sources, plus dataclass fields the pipeline sets);
* therefore which gates have reachable inputs and which are structurally
  input-less.

It is a REPORTING layer, not a gate: an input-less gate is not a failure, it is
a fact an operator must be able to see.  A gate with no declared required keys
is treated as ``unknown`` — never as reachable, because claiming reachability
without evidence is exactly the fake data this exists to prevent.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

#: Names the pipeline uses for the shared gate context.  A producer assignment
#: is ``<one of these>["key"] = value``.
_CONTEXT_NAMES: frozenset[str] = frozenset({"gate_context", "context", "ctx", "_ctx", "_context"})

#: Where producers live, relative to the package root.
_PRODUCER_SOURCES: tuple[str, ...] = ("pipelines", "gates", "omni", "engines")


@dataclass(frozen=True)
class GateInputRequirement:
    """One gate's declared input keys, plus the gate's declaring module."""

    gate: str
    required_keys: tuple[str, ...]
    source: str


def _is_context_subscript(node: ast.AST) -> str | None:
    """Return the key when *node* is ``<context>["key"]``, else ``None``."""
    if not isinstance(node, ast.Subscript):
        return None
    target = node.value
    if not isinstance(target, ast.Name) or target.id not in _CONTEXT_NAMES:
        return None
    key = node.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    return None


def _string_tuple(node: ast.AST) -> tuple[str, ...] | None:
    """Return the literal strings of a tuple/list of constants, else ``None``."""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    values: list[str] = []
    for element in node.elts:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            return None
        values.append(element.value)
    return tuple(values)


def declared_gate_inputs(gates_root: Path) -> dict[str, GateInputRequirement]:
    """Scan gate modules for ``missing_input_result`` declarations.

    Returns one entry per gate that declares required keys.  A gate calling it
    more than once keeps the FIRST declaration (they are per-gate constants in
    practice; taking the union would overstate what the gate needs).
    """
    found: dict[str, GateInputRequirement] = {}
    for path in sorted(gates_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # a broken module is another gate's problem
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "missing_input_result"):
                continue
            if len(node.args) < 3:
                continue
            gate_arg, keys_arg = node.args[0], node.args[2]
            if not (isinstance(gate_arg, ast.Constant) and isinstance(gate_arg.value, str)):
                continue
            keys = _string_tuple(keys_arg)
            if keys is None:
                continue
            found.setdefault(
                gate_arg.value,
                GateInputRequirement(
                    gate=gate_arg.value,
                    required_keys=keys,
                    source=path.name,
                ),
            )
    return found


def produced_context_keys(src_root: Path) -> set[str]:
    """Every context key some module ASSIGNS, statically.

    Detects ``ctx["key"] = ...``, ``ctx.setdefault("key", ...)`` and
    ``ctx.update({"key": ...})``.  A key that is only ever READ is not
    produced — which is precisely the condition that makes a gate skip.
    """
    keys: set[str] = set()
    for sub in _PRODUCER_SOURCES:
        base = src_root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        key = _is_context_subscript(target)
                        if key is not None:
                            keys.add(key)
                elif isinstance(node, ast.AnnAssign):
                    key = _is_context_subscript(node.target)
                    if key is not None:
                        keys.add(key)
                elif isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr in (
                        "setdefault",
                        "update",
                    ):
                        target = func.value
                        if not (isinstance(target, ast.Name) and target.id in _CONTEXT_NAMES):
                            continue
                        if func.attr == "setdefault" and node.args:
                            first = node.args[0]
                            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                                keys.add(first.value)
                        elif func.attr == "update" and node.args:
                            mapping = node.args[0]
                            if isinstance(mapping, ast.Dict):
                                for k in mapping.keys:
                                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                        keys.add(k.value)
    return keys


@dataclass(frozen=True)
class InputReachability:
    """The fifth coverage dimension: can a gate's inputs ever exist?"""

    reachable_gates: tuple[str, ...]
    """Gates whose every declared required key has a producer."""

    unreachable_gates: tuple[str, ...]
    """Gates that will always skip: at least one required key has no producer."""

    unknown_gates: tuple[str, ...]
    """Gates that declare no required keys — reachability is not asserted."""

    missing_keys: dict[str, tuple[str, ...]]
    """Per unreachable gate, the required keys nothing produces."""

    @property
    def inspectable(self) -> int:
        """How many declared gates can actually inspect an artifact."""
        return len(self.reachable_gates)


def audit_input_reachability(
    gates_root: Path,
    src_root: Path,
    declared_gates: set[str],
) -> InputReachability:
    """Cross the gates' declared inputs with the keys the pipeline produces."""
    requirements = declared_gate_inputs(gates_root)
    produced = produced_context_keys(src_root)

    reachable: list[str] = []
    unreachable: list[str] = []
    unknown: list[str] = []
    missing: dict[str, tuple[str, ...]] = {}

    for gate in sorted(declared_gates):
        requirement = requirements.get(gate)
        if requirement is None:
            unknown.append(gate)
            continue
        absent = tuple(key for key in requirement.required_keys if key not in produced)
        if absent:
            unreachable.append(gate)
            missing[gate] = absent
        else:
            reachable.append(gate)

    return InputReachability(
        reachable_gates=tuple(reachable),
        unreachable_gates=tuple(unreachable),
        unknown_gates=tuple(unknown),
        missing_keys=missing,
    )


def input_reachability_note(reachability: InputReachability) -> str:
    """One honest sentence for the audit output and the gate report.

    States all THREE buckets, because the honest reading is not
    "3 of 33 gates work": most gates declare no required keys at all, so their
    input reachability is simply not asserted by this audit.
    """
    declared_with = len(reachability.reachable_gates) + len(reachability.unreachable_gates)
    if not declared_with:
        return (
            "No gate declares required inputs, so input reachability is not "
            "asserted for any of them."
        )
    head = (
        f"{len(reachability.reachable_gates)} of the {declared_with} gates that "
        "DECLARE required inputs have them produced by this pipeline; "
        f"{len(reachability.unknown_gates)} gates declare no required inputs "
        "(reachability not asserted)."
    )
    if not reachability.unreachable_gates:
        return head
    return (
        head + f" {len(reachability.unreachable_gates)} will always report skipped "
        "because no module produces a required key: "
        + ", ".join(
            f"{gate}({','.join(keys)})" for gate, keys in sorted(reachability.missing_keys.items())
        )
        + "."
    )


__all__ = [
    "GateInputRequirement",
    "InputReachability",
    "audit_input_reachability",
    "declared_gate_inputs",
    "input_reachability_note",
    "produced_context_keys",
]
