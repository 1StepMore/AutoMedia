"""Library smoke test (plan W3-T9, C2/C4) — schema conformance across the
whole committed scenario library.

THIS IS THE ONE TEST FILE THAT READS THE REAL COMMITTED LIBRARY
(``scenarios/``) instead of synthetic fixtures.  It is the framework
validating its own framework: every committed scenario must load, all
standards must be known, the meta scenarios must carry the recursion-guard
design, and the 7 boundary-only control scenarios must exist.  It is a REAL
gate in CI — the library is committed, so a broken scenario file fails this
test, not just the next validation run.  It loads and inspects only: no
network, no LLM, no engine runs.

Skip rule (documented): when ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` is set
to a directory that does not exist, the library is intentionally unavailable
and this module skips.  Any other value — including the unset default
(repo-root ``scenarios/``) — runs the real gate.

Committed library as of 2026-08-14: 90 scenario files = 52 surface + 18 cli
+ 13 baseline (10 root + 3 depconfig) + 3 publish + 2 journeys + 2 quality;
28 known standard keys (``STANDARDS.md``); 5 keys actually cited across the
library (tool.contract 81, founder-expectations.F01 40, founder-expectations
.F02 24, cli.doctor 6, founder-expectations.true-test 3); 4 meta scenarios
(issue #86 added validation-matrix-meta + validate-matrix-meta);
7 boundary-only control scenarios.  These counts are asserted with
floor/threshold bounds (>= 80 scenarios) so deliberate library growth or
shrink does not re-pin the test; the actual counts are reported.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario, SchemaError
from automedia.validation.standards import StandardsRegistry

# The four meta scenarios that reference the validation surface itself.  They
# are EXPECTED-RED in the engine until W4 registers the surface, but they must
# LOAD fine — this module never runs them, only loads and inspects.  The
# issue #86 pair (validation-matrix-meta / validate-matrix-meta) covers the
# new validation_matrix tool and the validate matrix CLI command — both
# non-recursive (no scenario name), so the recursion guard stays intact.
META_SCENARIOS: tuple[str, ...] = (
    "list-validation-scenarios-meta",
    "validate-list-meta",
    "validation-matrix-meta",
    "validate-matrix-meta",
)

# The 7 boundary-only control scenarios (scenarios/surface/control/*.yaml):
# every control surface is covered by a scenario-level error_boundary probe,
# never a success-asserting scenario (coverage audit reads scenario-level
# error_boundary only).
CONTROL_SCENARIOS: tuple[str, ...] = (
    "approve-gate-boundary",
    "cancel-pipeline-boundary",
    "pause-pipeline-boundary",
    "reject-gate-boundary",
    "resume-pipeline-boundary",
    "retry-gate-boundary",
    "skip-gate-boundary",
)

_CMD_VALIDATE_RE = re.compile(r"\bvalidate\b")


def _scenarios_dir_or_skip() -> Path:
    """The scenarios dir to smoke; skip when the env override is broken."""
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override and not Path(override).expanduser().is_dir():
        pytest.skip(
            f"AUTOMEDIA_VALIDATION_SCENARIOS_DIR={override!r} points to a "
            "non-existent directory; the real-library smoke gate is skipped "
            "(documented W3-T9)"
        )
    return default_scenarios_dir()


@pytest.fixture(scope="module")
def library_root() -> Path:
    """The real committed scenarios directory (skip when unavailable)."""
    return _scenarios_dir_or_skip()


@pytest.fixture(scope="module")
def standards() -> StandardsRegistry:
    """The real standards registry from ``scenarios/STANDARDS.md``."""
    return StandardsRegistry.from_default()


@pytest.fixture(scope="module")
def library(library_root: Path, standards: StandardsRegistry) -> list[Scenario]:
    """Every committed scenario loaded through the real loader + registry."""
    return load_scenarios(library_root, standards=standards)


def _step_standards(scenario: Scenario) -> list[str]:
    """Every standard key cited by a scenario, recovery and cleanup included."""
    cited: list[str] = []
    for step in scenario.steps:
        cited.append(step.standard)
        cited.extend(recovery.standard for recovery in step.recovery_steps)
    cited.extend(step.standard for step in scenario.cleanup_steps)
    return cited


def _all_steps(doc: dict[str, object]) -> list[dict[str, object]]:
    """Every step of one raw YAML doc: primary + recovery + cleanup."""
    steps: list[dict[str, object]] = []
    raw = doc.get("steps", [])
    if not isinstance(raw, list):
        return steps
    for step in raw:
        if not isinstance(step, dict):
            continue
        steps.append(step)
        recovery = step.get("recovery_steps", [])
        if isinstance(recovery, list):
            steps.extend(item for item in recovery if isinstance(item, dict))
    cleanup = doc.get("cleanup_steps", [])
    if isinstance(cleanup, list):
        steps.extend(item for item in cleanup if isinstance(item, dict))
    return steps


def test_every_scenario_loads(library: list[Scenario], library_root: Path) -> None:
    """The whole committed tree loads with ZERO LoadError; >= 80 scenarios."""
    assert len(library) >= 80, (
        f"library shrank below the floor: loaded {len(library)} scenarios "
        f"(90 committed as of 2026-08-14)"
    )
    by_category = Counter(scenario.category for scenario in library)
    print(
        f"library smoke: {len(library)} scenarios "
        f"({dict(sorted(by_category.items()))}) from {library_root}"
    )


def test_names_unique(library: list[Scenario]) -> None:
    """All scenario names unique (loader enforces — regression pin)."""
    names = [scenario.name for scenario in library]
    assert len(names) == len(set(names)), "duplicate scenario names in library"


def test_all_standards_known(library: list[Scenario], standards: StandardsRegistry) -> None:
    """Every step's standard across the library is a known registry key."""
    known = standards.known_keys()
    cited = sorted({key for scenario in library for key in _step_standards(scenario)})
    unknown = [key for key in cited if key not in known]
    assert not unknown, f"unknown standard keys in library: {unknown}"
    assert cited, "library cites no standards at all"
    print(f"library smoke: {len(cited)} distinct standards cited: {cited}")


def test_intent_present(library: list[Scenario]) -> None:
    """Every scenario carries a non-empty intent (schema enforces — pin)."""
    for scenario in library:
        assert scenario.intent.strip(), f"scenario {scenario.name!r} has an empty intent"


def test_meta_self_validation(
    library: list[Scenario],
    library_root: Path,
    standards: StandardsRegistry,
) -> None:
    """The meta scenarios exist, are env-free, cite real standards, and are
    the ONLY scenarios touching the validation surface (recursion guard)."""
    by_name = {scenario.name: scenario for scenario in library}
    for name in META_SCENARIOS:
        assert name in by_name, f"meta scenario {name!r} missing from library"
    meta = [by_name[name] for name in META_SCENARIOS]
    known = standards.known_keys()
    for scenario in meta:
        assert scenario.requires_env == [], (
            f"meta scenario {scenario.name!r} must not require env "
            f"(recursion guard: the meta surface must be callable anywhere)"
        )
        cited = _step_standards(scenario)
        assert cited, f"meta scenario {scenario.name!r} cites no standards"
        unknown = [key for key in cited if key not in known]
        assert not unknown, f"meta scenario {scenario.name!r} cites unknown standards: {unknown}"

    # Recursion guard: scan the RAW committed files (not the parsed library)
    # for `validate` in command strings and `list_validation_scenarios` in
    # tool names; only the two meta files may reference them.
    cmd_offenders: set[Path] = set()
    tool_offenders: set[Path] = set()
    for path in sorted(library_root.rglob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        for step in _all_steps(doc):
            command = step.get("command")
            if isinstance(command, str) and _CMD_VALIDATE_RE.search(command):
                cmd_offenders.add(path)
            tool = step.get("tool")
            if isinstance(tool, str) and "list_validation_scenarios" in tool:
                tool_offenders.add(path)
    assert cmd_offenders == {
        library_root / "cli" / "validate-list-meta.yaml",
        library_root / "cli" / "validate-matrix-meta.yaml",
    }, (
        f"recursion guard violated: scenarios invoking `automedia validate`: "
        f"{sorted(p.relative_to(library_root) for p in cmd_offenders)}"
    )
    assert tool_offenders == {library_root / "list-validation-scenarios.yaml"}, (
        f"recursion guard violated: scenarios invoking the "
        f"list_validation_scenarios tool: "
        f"{sorted(p.relative_to(library_root) for p in tool_offenders)}"
    )


def test_error_boundary_scenarios_present(library: list[Scenario], library_root: Path) -> None:
    """The 7 boundary-only control scenarios exist with scenario-level
    error_boundary: true (what the coverage audit reads)."""
    control_dir = library_root / "surface" / "control"
    files = sorted(control_dir.glob("*.yaml"))
    assert len(files) == len(CONTROL_SCENARIOS), (
        f"surface/control/ holds {len(files)} files, expected "
        f"{len(CONTROL_SCENARIOS)}: {[f.name for f in files]}"
    )
    by_name = {scenario.name: scenario for scenario in library}
    for filename, name in zip(files, CONTROL_SCENARIOS, strict=True):
        assert filename.stem == name, (
            f"control file {filename.name!r} does not match its scenario name {name!r}"
        )
        scenario = by_name[name]
        assert scenario.error_boundary is True, (
            f"control scenario {name!r} must be scenario-level error_boundary: true"
        )


def test_schema_conformance(library_root: Path) -> None:
    """Belt-and-braces: every raw YAML doc parses via Scenario.from_dict,
    independent of the loader's own parse path."""
    checked = 0
    for path in sorted(library_root.rglob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            scenario = Scenario.from_dict(doc)
        except SchemaError as exc:
            raise AssertionError(f"{path}: schema conformance failed: {exc}") from exc
        assert scenario.steps, f"{path}: scenario has no steps"
        checked += 1
    assert checked >= 80, f"schema conformance checked only {checked} files"
