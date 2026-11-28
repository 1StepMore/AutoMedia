"""Partial-pass policy across multi-step integration scenarios (gap R-04).

The partial-success policy existed but was used by only two scenarios, so
graceful degradation was never exercised.  This module pins:

* at least five committed scenarios declare a ``min_passing``/``pass_ratio``
  policy;
* every committed env-free policy scenario that produces a ``partial-pass``
  verdict names EVERY failed step in the run record (the plan's
  "hidden-failure-free" definition: the record's failed steps each carry
  their expect failures and the summary count matches the failed step
  count — partial-pass never hides a failure);
* the three deterministic integration scenarios each PASS — since #719
  their degradation legs assert the structured refusal the product actually
  owes (NOT_FOUND / allowlist deny) instead of a red ``expect.success`` that
  contradicted correct behaviour.

Synthetic/dispatch fixtures only (Red Line 4); the degradation steps are real
shipped-surface calls with a deterministic error (unknown project id /
allowlist-refused source), never a fabricated pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from automedia.mcp.server import create_server
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.loader import load_scenarios
from automedia.validation.schema import Scenario

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NEW_PARTIAL_PASS = (
    "partial-pass-omni-extraction",
    "partial-pass-progress-surface",
    "partial-pass-cli-contract",
)


def _run(scenario: Scenario) -> dict[str, Any]:
    return run_validation_scenario(scenario, make_adapters(create_server()), cwd=_REPO_ROOT)


def _committed(name: str) -> Scenario:
    for scenario in load_scenarios():
        if scenario.name == name:
            return scenario
    raise AssertionError(f"committed scenario {name!r} not found in the library")


class TestPolicyIsAdopted:
    def test_at_least_five_scenarios_declare_partial_pass_policy(self) -> None:
        policy = [
            scenario.name
            for scenario in load_scenarios()
            if scenario.min_passing is not None or scenario.pass_ratio is not None
        ]
        assert len(policy) >= 5, f"only {len(policy)} scenarios declare a policy: {policy}"

    def test_new_scenarios_are_partial_pass_policy_scenarios(self) -> None:
        for name in _NEW_PARTIAL_PASS:
            scenario = _committed(name)
            assert scenario.min_passing is not None or scenario.pass_ratio is not None, name
            assert scenario.requires_env == [], f"{name} must be env-free"


class TestNoHiddenFailure:
    @pytest.mark.parametrize("name", _NEW_PARTIAL_PASS)
    def test_committed_scenarios_pass_with_asserted_refusals(self, name: str) -> None:
        """Since #719 the degradation legs assert the honest refusal, so every
        step passes — correct behaviour is green, never partial-pass."""
        record = _run(_committed(name))
        assert record["status"] == "passed", (name, record["status"], record["summary"])
        failed = [step for step in record["steps"] if not step["passed"]]
        assert not failed, f"{name}: failed steps {[step['name'] for step in failed]}"

    def test_multi_failure_scenario_lists_both_failed_steps(self) -> None:
        """A scenario with two failing steps must name both."""
        scenario = Scenario.from_dict(
            {
                "name": "runtime-partial-pass-two-failures",
                "description": "Two failing steps under a pass-ratio policy.",
                "intent": "Prove every failed step is listed under partial-pass.",
                "user_level": "L0",
                "requires_env": [],
                "pass_ratio": 0.3,
                "steps": [
                    {
                        "name": "passing baseline",
                        "kind": "cli",
                        "check": "echo exits zero",
                        "standard": "founder-expectations.F02",
                        "command": "echo ok",
                        "expect": {"exit_code": 0},
                    },
                    {
                        "name": "first injected failure",
                        "kind": "cli",
                        "check": "a nonzero exit fails the step",
                        "standard": "founder-expectations.F01",
                        "command": 'python3 -c "import sys; sys.exit(1)"',
                        "expect": {"exit_code": 0},
                    },
                    {
                        "name": "second injected failure",
                        "kind": "cli",
                        "check": "a nonzero exit fails the step",
                        "standard": "founder-expectations.F01",
                        "command": 'python3 -c "import sys; sys.exit(2)"',
                        "expect": {"exit_code": 0},
                    },
                ],
            }
        )
        record = _run(scenario)
        assert record["status"] == "partial-pass", record
        failed_names = [step["name"] for step in record["steps"] if not step["passed"]]
        assert failed_names == ["first injected failure", "second injected failure"]
        assert record["summary"]["failed"] == 2
