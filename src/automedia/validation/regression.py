"""Regression flywheel helpers (plan W4-T6, C4).

The regression flywheel (guide §5.2) closes the loop between a found bug and
a forgotten one: every bug is pinned by a scenario marked ``regression: true``
and carrying a ``regression_issue`` reference, and that scenario must stay
GREEN forever — a RED regression scenario IS the bug, re-surfaced.  This
module is the machine-readable surface of the flywheel: it lists the pinned
scenarios, their issue references, and verifies the discipline holds.

The schema already enforces ``regression=True ⇒ regression_issue`` at load
time (W1-T1), so :func:`verify_regression_discipline` is belt-and-braces: it
re-checks the invariant (any violation is reported in ``missing_issue``) and
reports the placement of each pinned scenario — the canonical ``regression/``
subdirectory or the marker carried in place next to its family.  The loader's
recursive glob picks up ``scenarios/regression/*.yaml`` automatically;
nothing needs registration (guide §3.1, plan review fix m10).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario

_REGRESSION_SUBDIR = "regression"
"""Canonical subdirectory for regression scenarios (guide §5.2)."""


def _root(scenarios_dir: str | Path | None) -> Path:
    """Resolve the scenarios root, honoring the env override like the loader."""
    return default_scenarios_dir() if scenarios_dir is None else Path(scenarios_dir)


def _name_to_path(scenarios_dir: str | Path | None) -> dict[str, Path]:
    """Map scenario names to their file paths by scanning the tree.

    The loader validates the content; this helper only reads the ``name:``
    field, so it stays tolerant of files the loader would reject.
    """
    root = _root(scenarios_dir)
    mapping: dict[str, Path] = {}
    if not root.is_dir():
        return mapping
    for path in sorted(root.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("name"), str):
            mapping[doc["name"]] = path
    return mapping


def regression_scenarios(scenarios_dir: str | Path | None = None) -> list[Scenario]:
    """Load the library and return the scenarios pinned with
    ``regression: true``, in deterministic load order."""
    return [s for s in load_scenarios(scenarios_dir) if s.regression]


def regression_issues(scenarios_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """The pinned bug references: ``[{name, regression_issue, file}]`` in load
    order.  ``file`` is the scenario's path within the library tree."""
    paths = _name_to_path(scenarios_dir)
    issues: list[dict[str, Any]] = []
    for scenario in regression_scenarios(scenarios_dir):
        entry: dict[str, Any] = {
            "name": scenario.name,
            "regression_issue": scenario.regression_issue,
        }
        path = paths.get(scenario.name)
        if path is not None:
            entry["file"] = str(path)
        issues.append(entry)
    return issues


def verify_regression_discipline(
    scenarios_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Belt-and-braces flywheel discipline check (guide §5.2).

    (a) Every ``regression: true`` scenario carries a ``regression_issue`` —
    the schema enforces this at load; the re-check here is belt-and-braces,
    with any violation reported in ``missing_issue``.  (b) Placement: pinned
    scenarios either live under the canonical ``regression/`` subdirectory or
    carry the marker in place next to their family; both classes are
    reported.  Returns ``{regression_scenarios, issues, count,
    missing_issue, in_regression_dir, in_place}`` in deterministic load
    order.
    """
    regressions = regression_scenarios(scenarios_dir)
    issues = regression_issues(scenarios_dir)
    regression_dir = _root(scenarios_dir) / _REGRESSION_SUBDIR
    in_dir: list[str] = []
    in_place: list[str] = []
    for issue in issues:
        path = issue.get("file")
        if isinstance(path, str) and Path(path).is_relative_to(regression_dir):
            in_dir.append(issue["name"])
        else:
            in_place.append(issue["name"])
    return {
        "regression_scenarios": [s.name for s in regressions],
        "issues": issues,
        "count": len(regressions),
        "missing_issue": [s.name for s in regressions if not s.regression_issue],
        "in_regression_dir": in_dir,
        "in_place": in_place,
    }
