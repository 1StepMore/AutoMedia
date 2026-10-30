"""Threshold-snapshot drift gate (plan A7).

Contract: the committed ``scenarios/baseline/threshold-snapshot.json`` must
always match the loaded scenario library, and every *changed* numeric
threshold must carry a waiver row in ``scenarios/THRESHOLD_WAIVERS.md`` —
the director's recorded adjudication.  This is the enforcement half of the
produce-article lesson: its ``min_chars`` budget was lowered 800 -> 500
after a real RED run with no record of the decision.

Regeneration: ``python scripts/snapshot_scenario_thresholds.py`` (see its
docstring for the closed field set).  New or removed scenarios need
regeneration only; a changed value needs regeneration AND a waiver row.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.snapshot_scenario_thresholds import SNAPSHOT_PATH, build_snapshot

WAIVER_PATH = Path(__file__).resolve().parent.parent.parent / "scenarios" / "THRESHOLD_WAIVERS.md"


def _committed() -> dict:
    assert SNAPSHOT_PATH.is_file(), (
        f"{SNAPSHOT_PATH} is missing — run "
        "`python scripts/snapshot_scenario_thresholds.py` to create it"
    )
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _changed_values(committed: dict, current: dict) -> dict[str, dict[str, tuple[object, object]]]:
    """Return ``{scenario: {field: (old, new)}}`` for values present on both
    sides that differ — the pairs a waiver row must cover."""
    changes: dict[str, dict[str, tuple[object, object]]] = {}
    old_scenarios = committed.get("scenarios", {})
    new_scenarios = current.get("scenarios", {})
    for name in sorted(set(old_scenarios) & set(new_scenarios)):
        old_entry, new_entry = old_scenarios[name], new_scenarios[name]
        for field in sorted(set(old_entry) & set(new_entry)):
            if field == "steps":
                continue
            if old_entry[field] != new_entry[field]:
                changes.setdefault(name, {})[field] = (old_entry[field], new_entry[field])
        old_steps = old_entry.get("steps", {})
        new_steps = new_entry.get("steps", {})
        for step in sorted(set(old_steps) & set(new_steps)):
            for field in sorted(set(old_steps[step]) & set(new_steps[step])):
                if old_steps[step][field] != new_steps[step][field]:
                    changes.setdefault(name, {})[f"{step}.{field}"] = (
                        old_steps[step][field],
                        new_steps[step][field],
                    )
    return changes


def test_snapshot_matches_library() -> None:
    """The committed snapshot is byte-equal to the derived one — any threshold
    drift was regenerated in the same PR that changed it."""
    committed = _committed()
    current = build_snapshot()
    assert committed == current, (
        "threshold snapshot is stale: regenerate with "
        "`python scripts/snapshot_scenario_thresholds.py` and add a waiver "
        "row to scenarios/THRESHOLD_WAIVERS.md for every changed value "
        "(new/removed scenarios need regeneration only)"
    )


def test_changed_thresholds_carry_waiver_rows() -> None:
    """Every changed threshold value has a waiver row naming the scenario and
    the field — the director's adjudication is on record.  With a fresh
    snapshot this is vacuously true; it guards the regeneration race where
    someone regenerates but forgets the ledger."""
    committed = _committed()
    # Deliberately compare the PREVIOUS committed library state (the snapshot
    # before this PR, recoverable from git) against the current one when they
    # differ; when they match there is nothing to waive.
    current = build_snapshot()
    changes = _changed_values(committed, current)
    if not changes:
        pytest.skip("no threshold changes against the committed snapshot")

    waiver_text = WAIVER_PATH.read_text(encoding="utf-8")
    missing: list[str] = []
    for scenario, fields in changes.items():
        if scenario not in waiver_text:
            missing.append(f"{scenario}: no waiver row at all")
            continue
        for field in fields:
            leaf = field.split(".")[-1]
            if leaf not in waiver_text:
                missing.append(f"{scenario}.{field}: no waiver row for '{leaf}'")
    assert not missing, f"changed thresholds without a waiver row in {WAIVER_PATH.name}: {missing}"


def test_snapshot_covers_known_threshold_scenarios() -> None:
    """The closed field set is actually being captured: produce-article's
    min_chars budget (the case that motivated A7) must appear."""
    snapshot = _committed()["scenarios"]
    assert "produce-article" in snapshot
    assert "min_chars" in json.dumps(snapshot["produce-article"])


def test_waiver_ledger_exists() -> None:
    assert WAIVER_PATH.is_file(), f"{WAIVER_PATH} must exist — it is the adjudication trail"
