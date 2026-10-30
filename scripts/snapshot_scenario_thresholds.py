#!/usr/bin/env python3
"""Snapshot the numeric assertion thresholds of the scenario library (A7).

Every numeric quality threshold a scenario asserts — ``min_passing`` /
``pass_ratio`` at scenario level, ``min_score`` / ``artifact_size_min``, the
``text`` / ``subtitle`` / ``media`` / ``keyword_coverage`` /
``text_similarity`` probe bounds — is derived from the loaded library and
written to ``scenarios/baseline/threshold-snapshot.json``.

Why: the produce-article ``min_chars`` budget was lowered 800 -> 500 after a
real RED run with no record of the decision (infrastructure-audit-20261030
§4.2.2).  This snapshot makes any threshold drift visible: the committed
snapshot must be regenerated in the same PR, and every *changed* value must
carry a row in ``scenarios/THRESHOLD_WAIVERS.md`` — the director's recorded
adjudication.  ``tests/test_validation/test_threshold_snapshot.py`` enforces
both halves; this script only builds and checks.

Usage:
    python scripts/snapshot_scenario_thresholds.py           # (re)write
    python scripts/snapshot_scenario_thresholds.py --check   # exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "scenarios" / "baseline" / "threshold-snapshot.json"

# The closed set of numeric threshold leaves, per container.  Booleans and
# path/keyword lists are assertions but not *budgets*; only numbers a director
# could raise or lower are snapshotted.
_STEP_NUMERIC_FIELDS: tuple[str, ...] = ("min_score", "artifact_size_min")
_MEDIA_NUMERIC_FIELDS: tuple[str, ...] = (
    "min_count",
    "min_width",
    "min_height",
    "min_duration_s",
    "max_duration_s",
    "min_bitrate_kbps",
)
_TEXT_NUMERIC_FIELDS: tuple[str, ...] = ("min_paragraphs", "min_chars", "min_headings")
_SCENARIO_NUMERIC_FIELDS: tuple[str, ...] = ("min_passing", "pass_ratio")


def build_snapshot(scenarios: list[Any] | None = None) -> dict[str, Any]:
    """Derive the threshold snapshot from the loaded scenario library.

    Pure derivation from :func:`automedia.validation.loader.load_scenarios`
    (pass ``scenarios`` to inject a library, as the tests do).  Absent fields
    are omitted; keys are sorted so the JSON is byte-stable for the drift
    check.
    """
    if scenarios is None:
        from automedia.validation.loader import load_scenarios

        scenarios = load_scenarios()

    out: dict[str, Any] = {}
    for scenario in scenarios:
        entry: dict[str, Any] = {}
        for field in _SCENARIO_NUMERIC_FIELDS:
            value = getattr(scenario, field, None)
            if value is not None:
                entry[field] = value

        steps: dict[str, Any] = {}
        for index, step in enumerate(scenario.steps):
            expect = getattr(step, "expect", None)
            if expect is None:
                continue
            step_entry: dict[str, Any] = {}
            for field in _STEP_NUMERIC_FIELDS:
                value = getattr(expect, field, None)
                if value is not None:
                    step_entry[f"expect.{field}"] = value
            for prefix, container, fields in (
                ("expect.text", getattr(expect, "text", None), _TEXT_NUMERIC_FIELDS),
                (
                    "expect.media",
                    getattr(expect, "media", None),
                    _MEDIA_NUMERIC_FIELDS,
                ),
            ):
                if container is None:
                    continue
                for field in fields:
                    value = getattr(container, field, None)
                    if value is not None:
                        step_entry[f"{prefix}.{field}"] = value
            subtitle = getattr(expect, "subtitle", None)
            if subtitle is not None and subtitle.min_cues is not None:
                step_entry["expect.subtitle.min_cues"] = subtitle.min_cues
            for prefix, container in (
                ("expect.keyword_coverage", getattr(expect, "keyword_coverage", None)),
                ("expect.text_similarity", getattr(expect, "text_similarity", None)),
            ):
                if container is not None:
                    value = getattr(container, "min_ratio", None)
                    if value is not None:
                        step_entry[f"{prefix}.min_ratio"] = value
            if step_entry:
                steps[f"{index:02d}:{step.name}"] = step_entry
        if steps:
            entry["steps"] = steps
        if entry:
            out[scenario.name] = entry

    return {
        "_comment": (
            "AUTO-GENERATED: numeric assertion thresholds per scenario. "
            "Regenerate: python scripts/snapshot_scenario_thresholds.py. "
            "A changed value requires a row in scenarios/THRESHOLD_WAIVERS.md "
            "(director adjudication record, plan A7)."
        ),
        "scenarios": dict(sorted(out.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the committed snapshot against the library; exit 1 on drift.",
    )
    args = parser.parse_args(argv)

    current = build_snapshot()
    rendered = json.dumps(current, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    if not args.check:
        SNAPSHOT_PATH.write_text(rendered, encoding="utf-8")
        scenario_count = len(current["scenarios"])
        print(f"Wrote {SNAPSHOT_PATH} ({scenario_count} scenarios with thresholds)")
        return 0

    if not SNAPSHOT_PATH.is_file():
        print(f"FAIL: {SNAPSHOT_PATH} missing — run without --check to create it")
        return 1
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if committed != rendered:
        print("FAIL: threshold snapshot is stale — threshold(s) changed without")
        print("  regeneration.  Run: python scripts/snapshot_scenario_thresholds.py")
        print("  AND add a waiver row to scenarios/THRESHOLD_WAIVERS.md for every")
        print("  changed value (new/removed scenarios need regeneration only).")
        return 1
    print(f"OK: {SNAPSHOT_PATH} matches the loaded library")
    return 0


if __name__ == "__main__":
    sys.exit(main())
