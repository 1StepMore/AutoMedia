#!/usr/bin/env python3
"""Regression check for issue #100: journey scenarios run unattended.

Every scenario under ``scenarios/journeys/`` that invokes ``automedia run``
must pass ``--skip-review``.  Without it the H0 human-review gate pauses the
pipeline on its hardcoded 24h (86400s) timeout — ``runner.py`` hardcodes
``hitl_config["timeout_s"] = 86400`` and nothing overrides it — and the only
approval channel is the MCP ``review_decision`` tool, which resolves the wait
in-process and is therefore unreachable from a separate CLI process.  An
unattended run then exhausts the step's ``timeout_seconds`` instead of
completing.

The helper parses the committed journey YAML files and fails unless every
``automedia run`` command carries ``--skip-review``.  It also fails when it
finds no such command, so the check can never pass vacuously.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_JOURNEYS_DIR = _REPO_ROOT / "scenarios" / "journeys"
_MARKER = "REG100_JOURNEY_SKIP_REVIEW_INVARIANT_HOLDS"


def _run_commands(scenario: dict[str, object]) -> list[str]:
    commands: list[str] = []
    steps = scenario.get("steps")
    if not isinstance(steps, list):
        return commands
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") != "cli":
            continue
        command = step.get("command")
        if isinstance(command, str) and "automedia run" in command:
            commands.append(command)
    return commands


def main() -> int:
    offenders: list[str] = []
    checked = 0
    for path in sorted(_JOURNEYS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        for command in _run_commands(data):
            checked += 1
            if "--skip-review" not in command:
                offenders.append(f"{path.name}: {command}")

    if checked == 0:
        print("REG100_NO_JOURNEY_RUN_COMMANDS: no `automedia run` step under scenarios/journeys/")
        return 1
    if offenders:
        for line in offenders:
            print(f"REG100_MISSING_SKIP_REVIEW: {line}")
        return 1

    print(f"{_MARKER} ({checked} journey run command(s) checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
