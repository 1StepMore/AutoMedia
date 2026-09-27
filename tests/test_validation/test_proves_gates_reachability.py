"""Issue #99 guard: every scenario's ``proves_gates`` binding is executable.

The drift behind issue #99: nine journey scenarios declared G4/G5/L1-L4 in
``proves_gates`` although no pipeline preset and no shipped command path
executes them.  ``automedia validate coverage`` read those declarations
blindly, so the audit reported 33/33 gates covered while the truth was 27/33.

This guard binds each declaration to the code that can actually execute it,
reading the authoritative sources live (never a hardcoded gate table):

* A scenario whose steps invoke a pipeline run — CLI ``automedia run --mode X``
  or the MCP ``run_pipeline`` tool with ``mode: X`` — must declare EXACTLY the
  union of ``_MODE_MAP[X]`` over the modes it runs, and ``proves_modes`` must
  name exactly those modes.  A declaration the preset does not carry
  (G4/G5/L1-L4) fails here.
* A scenario with no pipeline run must declare only gates a standalone command
  executes — ``COMMAND_PATH_REACHABLE_GATES`` in ``validation/coverage.py``,
  each entry citing its execution surface.

The rule encodes reachability, not a ban-list: a future preset gate works
automatically, and a future registered-but-unreachable gate is rejected by the
same rule that rejects G4/G5 today.

Same skip rule as the other real-library tests: when
``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` points to a non-existent directory the
library is intentionally unavailable and this module skips.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

import pytest

from automedia.pipelines.runner import _MODE_MAP
from automedia.validation.coverage import COMMAND_PATH_REACHABLE_GATES
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario


def _library_or_skip() -> list[Scenario]:
    """The real committed library; skip when the env override is broken."""
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override and not Path(override).expanduser().is_dir():
        pytest.skip(
            f"AUTOMEDIA_VALIDATION_SCENARIOS_DIR={override!r} points to a "
            "non-existent directory; the #99 reachability guard is skipped"
        )
    return load_scenarios(default_scenarios_dir())


def _pipeline_modes(scenario: Scenario) -> set[str]:
    """Pipeline modes the scenario's steps invoke.

    Recognizes the two shipped pipeline entry points that name a mode: the CLI
    ``automedia run ... --mode X`` and the MCP ``run_pipeline`` tool with a
    ``mode`` argument.  Recovery steps are walked too: they are real adapter
    calls whose mode is equally executable.
    """
    modes: set[str] = set()

    def walk(step: object) -> None:
        kind = getattr(step, "kind", None)
        if kind == "tool" and getattr(step, "tool", None) == "run_pipeline":
            mode = (getattr(step, "arguments", None) or {}).get("mode")
            if isinstance(mode, str) and mode:
                modes.add(mode)
        elif kind == "cli" and getattr(step, "command", None):
            tokens = shlex.split(step.command)
            if tokens[:2] == ["automedia", "run"] and "--mode" in tokens:
                index = tokens.index("--mode")
                if index + 1 < len(tokens):
                    modes.add(tokens[index + 1])
        for recovery in getattr(step, "recovery_steps", []):
            walk(recovery)

    for step in [*scenario.steps, *scenario.cleanup_steps]:
        walk(step)
    return modes


@pytest.fixture(scope="module")
def library() -> list[Scenario]:
    """The real committed library (skip when unavailable)."""
    return _library_or_skip()


def test_pipeline_scenarios_declare_exactly_their_preset_gates(library: list[Scenario]) -> None:
    """A pipeline scenario's declarations equal the ``_MODE_MAP`` gate union.

    A scenario that merely starts a pipeline and asserts no gate claim (e.g.
    the async-start probe) declares nothing and is bound by nothing; the guard
    binds *declarations*, never invents them.  Once a scenario declares gates
    for a pipeline run, G4/G5/L1-L4 are in no preset, so re-declaring one fails
    here with the phantom set named.
    """
    for scenario in library:
        modes = _pipeline_modes(scenario)
        if not modes or not (scenario.proves_gates or scenario.proves_modes):
            continue
        unknown = sorted(modes - set(_MODE_MAP))
        assert not unknown, f"{scenario.name}: pipeline mode(s) not in _MODE_MAP: {unknown}"
        expected = set().union(*(set(_MODE_MAP[mode]) for mode in modes))
        if scenario.proves_gates:
            declared = set(scenario.proves_gates)
            phantom = sorted(declared - expected)
            undeclared = sorted(expected - declared)
            assert declared == expected, (
                f"{scenario.name}: proves_gates drift for mode(s) {sorted(modes)}; "
                f"phantom (declared but not preset-executable)={phantom}; "
                f"undeclared={undeclared}"
            )
        if scenario.proves_modes:
            assert set(scenario.proves_modes) == modes, (
                f"{scenario.name}: proves_modes {sorted(scenario.proves_modes)} != "
                f"the pipeline mode(s) its steps run {sorted(modes)}"
            )


def test_command_path_scenarios_declare_only_reachable_gates(library: list[Scenario]) -> None:
    """A declared gate set with no pipeline run is command-path-reachable only.

    The positive reachability set replaces a ban-list: G4/G5 are simply absent
    from both preset reachability and the command-path set, so the same rule
    that admits D1-D7/L1-L4 rejects them.
    """
    for scenario in library:
        if _pipeline_modes(scenario) or not scenario.proves_gates:
            continue
        unreachable = sorted(set(scenario.proves_gates) - set(COMMAND_PATH_REACHABLE_GATES))
        assert not unreachable, (
            f"{scenario.name}: proves_gates names gate(s) no preset or shipped "
            f"command executes: {unreachable}; command-path-reachable gates are "
            f"{sorted(COMMAND_PATH_REACHABLE_GATES)}"
        )
