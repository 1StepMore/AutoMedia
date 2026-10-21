#!/usr/bin/env python3
"""Regression lock for ADR-007: the gate verdict is an aggregate.

Before the fix, ``GateEngine.run()``'s ``success`` flag was a last-write-wins
accumulator: every passing gate reset it.  A ``failure_mode="retry"`` gate that
exhausted its retries in a mode with no ``CW`` gate — ``qa_only`` (G2) and
``video_only`` (V5) are both retry-mode and both CW-less — left a failed row in
``results`` while a later passing gate flipped the flag back, so the engine
reported success and ``PipelineResult.status`` became ``"success"``, which made
the CLI exit 0.

This driver runs the REAL gate classes in the REAL ``GateEngine`` with every
gate's ``execute`` replaced by a deterministic stub (only the target gate
fails), so no network or LLM call is made.  It asserts:

1. a failed retry gate in ``qa_only`` is NOT reported as success;
2. the same in ``video_only``;
3. the fixture really produced a failure (the check cannot pass vacuously);
4. an all-passing run of the same shape IS reported as success.
"""

from __future__ import annotations

import sys
import types
from typing import Any

MARKER = "ADR007_GATE_VERDICT_IS_AN_AGGREGATE"


def _gates_for(mode: str, failing: str) -> list[Any]:
    import automedia.gates  # noqa: F401 — import registers every gate class
    from automedia.gates.base import _registry
    from automedia.pipelines.runner import _MODE_MAP

    gates = [_registry.get(name)() for name in _MODE_MAP[mode]]
    for gate in gates:
        name = gate.gate_name
        passed = name != failing
        gate.execute = types.MethodType(
            lambda self, ctx, _name=name, _passed=passed: {
                "passed": _passed,
                "gate": _name,
                "error": "" if _passed else "forced failure",
            },
            gate,
        )
    return gates


def _run(mode: str, failing: str) -> tuple[bool, list[dict[str, Any]]]:
    from automedia.pipelines.gate_engine import GateEngine

    engine = GateEngine(
        gates=_gates_for(mode, failing),
        max_quality_retries=0,
        max_regenerations=2,
    )
    return engine.run({"content": "x"})


def main() -> int:
    failures: list[str] = []

    for mode, failing in (("qa_only", "G2"), ("video_only", "V5")):
        ok, results = _run(mode, failing)
        failed_rows = [r.get("gate") for r in results if not r.get("passed", True)]
        if not failed_rows:
            failures.append(f"{mode}: fixture produced no failing gate (vacuous)")
            continue
        if ok is not False:
            failures.append(f"{mode}: failed gate {failed_rows} reported success")

    ok_clean, clean_results = _run("qa_only", "")
    if not clean_results:
        failures.append("qa_only clean run executed no gates")
    elif ok_clean is not True:
        failures.append("qa_only clean run reported failure")

    if failures:
        for line in failures:
            print(f"ADR007_GUARD_MISSING: {line}", file=sys.stderr)
        return 1

    print(MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
