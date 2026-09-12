"""Rerun-stability / order-isolation gate for the validation suite (gap R-11).

The engine's in-process isolation is documented but unproven: MCP-driven runs
share ``GateRegistry`` and active-pipeline state, so a scenario's verdict can
depend on execution order or leftover state rather than on the capability
under test.  This module makes that risk observable: it runs the same library
twice and compares every scenario's status.  Any per-scenario status change
between identical runs is an instability and fails the gate loudly.

A deliberately order-dependent fixture is detected the same way — its status
differs across the two runs, so it appears in the report's ``differences``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from automedia.validation.adapters import ToolCallable
from automedia.validation.engine import run_validation_suite_async
from automedia.validation.persist import latest_run


class RerunInstabilityError(Exception):
    """Two consecutive suite runs produced different per-scenario statuses."""


def scenario_statuses(record: dict[str, Any]) -> dict[str, str]:
    """Map scenario name -> status for one suite record (stable key order)."""
    raw = record.get("scenarios")
    statuses: dict[str, str] = {}
    if not isinstance(raw, list):
        return statuses
    for entry in raw:
        if isinstance(entry, dict) and entry.get("scenario") is not None:
            statuses[str(entry["scenario"])] = str(entry.get("status"))
    return statuses


def compare_statuses(
    first: dict[str, str], second: dict[str, str]
) -> dict[str, dict[str, str | None]]:
    """Per-scenario status differences between two runs (empty = stable).

    A scenario present in only one run is a difference too: its status is
    reported as ``None`` on the missing side.
    """
    differences: dict[str, dict[str, str | None]] = {}
    for name in sorted(set(first) | set(second)):
        before = first.get(name)
        after = second.get(name)
        if before != after:
            differences[name] = {"first": before, "second": after}
    return differences


@dataclass(frozen=True)
class StabilityReport:
    """The result of running one library ``runs`` times back to back."""

    runs: tuple[dict[str, str], ...]
    run_dirs: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        if len(self.runs) < 2:
            raise ValueError("a stability report needs at least two runs")

    @property
    def statuses(self) -> dict[str, str]:
        """The first run's status map (the reference)."""
        return self.runs[0]

    @property
    def differences(self) -> dict[str, dict[str, str | None]]:
        """Per-scenario differences across every consecutive run pair."""
        merged: dict[str, dict[str, str | None]] = {}
        for first, second in zip(self.runs, self.runs[1:], strict=False):
            merged.update(compare_statuses(first, second))
        return merged

    @property
    def stable(self) -> bool:
        """True when every run produced identical per-scenario statuses."""
        return not self.differences

    def require_stable(self) -> None:
        """Raise :class:`RerunInstabilityError` when any status changed."""
        if self.stable:
            return
        names = ", ".join(sorted(self.differences))
        raise RerunInstabilityError(
            f"rerun instability: {len(self.differences)} scenario(s) changed status "
            f"across {len(self.runs)} identical suite runs: {names}"
        )


async def verify_rerun_stability_async(
    server: ToolCallable | None,
    scenarios_dir: str | Path | None = None,
    *,
    runs_root: Path,
    runs: int = 2,
) -> StabilityReport:
    """Run the library ``runs`` times and compare per-scenario statuses.

    Each run persists its own immutable record under ``runs_root`` (the run
    dirs are captured via ``latest.txt``), so the two per-scenario status maps
    are real run-record evidence, not in-memory snapshots.
    """
    if runs < 2:
        raise ValueError("rerun stability needs at least two runs")
    status_maps: list[dict[str, str]] = []
    run_dirs: list[str | None] = []
    for _ in range(runs):
        record = await run_validation_suite_async(server, scenarios_dir, runs_root=runs_root)
        status_maps.append(scenario_statuses(record))
        run_dirs.append(latest_run(runs_root))
    return StabilityReport(tuple(status_maps), tuple(run_dirs))
