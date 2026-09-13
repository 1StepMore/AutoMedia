"""T-13: the committed coverage baseline and AGENTS scenario claim track the library.

RED before T-13: ``scenarios/baseline/coverage-audit.json`` carried
``scenario_count`` 126 while the committed library had grown to 142, and
AGENTS.md still claimed 107 scenarios.  The committed audit is the tracked
baseline the CI drift check compares against, so a stale count falsifies the
"baseline count == HEAD scenario count" acceptance.
"""

from __future__ import annotations

import json
from pathlib import Path

from automedia.validation.loader import load_scenarios

REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED_AUDIT = REPO_ROOT / "scenarios" / "baseline" / "coverage-audit.json"
_AGENTS = REPO_ROOT / "AGENTS.md"


def _library_count() -> int:
    return len(load_scenarios())


def test_committed_coverage_baseline_matches_library_count() -> None:
    committed = json.loads(_COMMITTED_AUDIT.read_text(encoding="utf-8"))
    assert committed["scenario_count"] == _library_count()


def test_committed_baseline_by_level_total_matches_scenario_count() -> None:
    committed = json.loads(_COMMITTED_AUDIT.read_text(encoding="utf-8"))
    assert committed["by_level"]["total"] == committed["scenario_count"]


def test_agents_scenario_count_claim_matches_library() -> None:
    assert f"{_library_count()} scenarios" in _AGENTS.read_text(encoding="utf-8")
