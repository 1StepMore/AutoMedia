"""Failure-injection recovery scenarios, one per mutating surface (gap R-01).

``recovery_steps`` was used by ZERO committed scenarios, so the engine's
``recovered`` verdict (:func:`automedia.validation.expects.apply_recovery`,
wired in ``engine._run_primary_step``) was unreachable in practice.  This
module builds one failure-injection + repair scenario for every mutating
surface the scenario library declares and runs each through the REAL engine
(``run_validation_scenario_async``), pinning:

* the scenario verdict is ``recovered`` — never ``passed``;
* the primary step's ORIGINAL failure stays in the run record (``failures``
  non-empty while ``status == "recovered"``): recovery downgrades the verdict,
  it never erases RED;
* the recovery step's trace is retained under ``trace["recovery"]``;
* a repair that itself fails leaves the verdict ``failed``.

The mutating surfaces are enumerated from the committed library's mutation
scenarios (``add-brand-isolated``, ``configure-llm-isolated``,
``init-config-tempdir``, ``add-pool-topic-tempdb``,
``add/remove-cron-schedule``, ``connect-account-masterkey``,
``archive-refusal-redline8``, ``rollback-cli-surface``,
``publish-content-probe``).  The failure injection is a sentinel argument the
fake dispatcher honours (``__inject_failure__``) for tool surfaces and a
non-zero CLI command for the CLI-only ``rollback`` surface.  All fixtures are
synthetic (Red Line 4); no network, no LLM, no credentials.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from automedia.validation.engine import make_adapters, run_validation_scenario_async
from automedia.validation.schema import Scenario, Step

_INJECT = "__inject_failure__"
"""Sentinel argument the injection dispatcher fails on (failure injection)."""

_RECOVERY_TMP = "/tmp/automedia"
"""Scratch root for the synthetic recovery arguments (never touched by the fake)."""


@dataclass(frozen=True)
class RecoverySurface:
    """One mutating surface and the call that repairs a failed mutation.

    ``kind`` is ``tool`` (``target`` is the MCP tool name) or ``cli``
    (``target`` is the failing command; ``repair_command`` is the repair).
    ``arguments`` are the valid mutation arguments for the recovery call.
    """

    name: str
    kind: str
    target: str
    arguments: dict[str, Any] = field(default_factory=dict)
    repair_command: str = ""

    def repair_dict(self) -> dict[str, Any]:
        """The repair step spec (valid mutation) following the failed primary."""
        if self.kind == "tool":
            return {
                "name": f"repair {self.name}",
                "kind": "tool",
                "check": f"{self.target} succeeds on the valid repair call",
                "standard": "tool.contract",
                "tool": self.target,
                "arguments": dict(self.arguments),
                "expect": {"success": True},
            }
        return {
            "name": f"repair {self.name}",
            "kind": "cli",
            "check": "the repair command exits 0",
            "standard": "founder-expectations.F01",
            "command": self.repair_command,
            "expect": {"success": True},
        }

    def recovery_step(self) -> Step:
        """The parsed repair step."""
        return Step.from_dict(self.repair_dict())

    def primary_step(self) -> Step:
        """The failure-injected mutation: fails, then runs its repair step."""
        if self.kind == "tool":
            injected = dict(self.arguments)
            injected[_INJECT] = True
            primary = {
                "name": f"injected failure on {self.name}",
                "kind": "tool",
                "check": f"{self.target} is deliberately failed (injected)",
                "standard": "tool.contract",
                "tool": self.target,
                "arguments": injected,
                "expect": {"success": True},
            }
        else:
            primary = {
                "name": f"injected failure on {self.name}",
                "kind": "cli",
                "check": "a deterministic non-zero command injects the failure",
                "standard": "founder-expectations.F01",
                "command": 'python3 -c "import sys; sys.exit(1)"',
                "expect": {"success": True},
            }
        return Step.from_dict({**primary, "recovery_steps": [self.repair_dict()]})


MUTATING_SURFACES: tuple[RecoverySurface, ...] = (
    RecoverySurface(
        "add_brand", "tool", "add_brand", {"name": "recovery-brand", "industry": "SaaS"}
    ),
    RecoverySurface(
        "configure_llm",
        "tool",
        "configure_llm",
        {"provider": "deepseek", "model": "deepseek-chat"},
    ),
    RecoverySurface(
        "init_config",
        "tool",
        "init_config",
        {"project_dir": f"{_RECOVERY_TMP}/recovery-initcfg"},
    ),
    RecoverySurface(
        "add_pool_topic",
        "tool",
        "add_pool_topic",
        {
            "title": "recovery-topic",
            "category": "tech",
            "pool_db_path": f"{_RECOVERY_TMP}/recovery-pool.db",
        },
    ),
    RecoverySurface(
        "add_cron_schedule",
        "tool",
        "add_cron_schedule",
        {"name": "recovery-cron", "expression": "0 8 * * *"},
    ),
    RecoverySurface(
        "remove_cron_schedule", "tool", "remove_cron_schedule", {"name": "recovery-cron"}
    ),
    RecoverySurface(
        "connect_account",
        "tool",
        "connect_account",
        {
            "platform": "wechat",
            "auth_type": "api_key",
            "credentials": {"api_key": "synthetic-recovery-key"},
            "label": "recovery",
        },
    ),
    RecoverySurface(
        "archive_project",
        "tool",
        "archive_project",
        {"project_id": "recoveryproj", "base_dir": f"{_RECOVERY_TMP}/recovery-projects"},
    ),
    RecoverySurface(
        "rollback",
        "cli",
        "rollback",
        repair_command="python3 -c \"print('rollback repair: reverted to draft')\"",
    ),
    RecoverySurface(
        "publish_content",
        "tool",
        "publish_content",
        {"project_id": "recoveryproj", "platform": "wechat"},
    ),
)
"""Every mutating surface the committed library exercises, one recovery scenario each."""


class InjectionServer:
    """Duck-typed FastMCP stand-in that fails calls carrying the sentinel.

    The failure injection lives in the call's arguments (``__inject_failure__``)
    so the primary step hits the SAME dispatch path as its repair, then the
    repair call (no sentinel) succeeds — exactly the failed-then-repaired
    lifecycle recovery exists for.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        self.calls.append((name, arguments))
        if arguments.get(_INJECT):
            return {"success": False, "error": f"injected failure on {name}"}
        return {"success": True, "data": {"repaired": name}}


def _scenario(surface: RecoverySurface) -> Scenario:
    return Scenario(
        name=f"recovery-{surface.name}",
        description=f"failure injection + repair for {surface.name}",
        intent="prove recovery_steps is reachable and RED is retained (R-01)",
        steps=[surface.primary_step()],
    )


def _run(surface: RecoverySurface, cwd: Path) -> dict[str, object]:
    scenario = _scenario(surface)
    adapters = make_adapters(InjectionServer())
    return asyncio.run(run_validation_scenario_async(scenario, adapters, cwd=cwd))


class TestMutatingSurfaceRecovery:
    """One recovery scenario per mutating surface: recovered + RED retained."""

    def test_surface_set_is_non_trivial(self) -> None:
        names = {surface.name for surface in MUTATING_SURFACES}
        assert len(MUTATING_SURFACES) >= 9
        assert names == {
            "add_brand",
            "configure_llm",
            "init_config",
            "add_pool_topic",
            "add_cron_schedule",
            "remove_cron_schedule",
            "connect_account",
            "archive_project",
            "rollback",
            "publish_content",
        }

    @pytest.mark.parametrize("surface", MUTATING_SURFACES, ids=lambda s: s.name)
    def test_mutating_surface_yields_recovered_with_red_retained(
        self, surface: RecoverySurface, tmp_path: Path
    ) -> None:
        record = _run(surface, tmp_path)

        assert record["status"] == "recovered", (
            f"{surface.name}: a passing repair must yield `recovered`, "
            f"observed {record['status']!r}"
        )
        summary = record["summary"]
        assert summary["recovered"] == 1
        assert summary["failed"] == 0

        (trace,) = record["steps"]
        assert trace["status"] == "recovered"
        assert trace["passed"] is True
        # RED is retained: the original failure stays on the record.
        assert trace["failures"], "the primary failure must stay in the record"
        assert any("expect.success" in failure for failure in trace["failures"])

        (recovery,) = trace["recovery"]
        assert recovery["passed"] is True
        assert recovery["status"] == "passed"

    @pytest.mark.parametrize("surface", MUTATING_SURFACES, ids=lambda s: s.name)
    def test_repaired_call_reaches_the_surface(
        self, surface: RecoverySurface, tmp_path: Path
    ) -> None:
        """The repair dispatch reaches the surface again (not a no-op script)."""
        record = _run(surface, tmp_path)
        (trace,) = record["steps"]
        (recovery,) = trace["recovery"]
        expected_target = surface.target if surface.kind == "tool" else surface.repair_command
        assert recovery["target"] == expected_target

    def test_failed_repair_keeps_failed(self, tmp_path: Path) -> None:
        """A repair that also fails leaves the verdict `failed` (never recovered)."""
        surface = RecoverySurface(
            "flake",
            "cli",
            "flake",
            repair_command='python3 -c "import sys; sys.exit(2)"',
        )
        record = _run(surface, tmp_path)
        assert record["status"] == "failed"
        (trace,) = record["steps"]
        assert trace["status"] == "failed"
        assert trace["passed"] is False

    def test_committed_library_has_a_recovery_scenario(self) -> None:
        """The committed library carries a real recovery_steps scenario (R-01)."""
        from automedia.validation.loader import load_scenarios

        scenarios = load_scenarios()
        with_recovery = [
            scenario.name
            for scenario in scenarios
            for step in scenario.steps
            if step.recovery_steps
        ]
        assert with_recovery, "no committed scenario declares recovery_steps"
