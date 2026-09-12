"""Unit tests for the validation engine (W1-T7).

Covers the six-phase executor against synthetic fixtures only — the fake
server is a duck-typed FastMCP stand-in (never the real MCP server, no
network): full GREEN run and per-step trace fields, unconfigured
short-circuit, failure, recovery (passing and failing), error_boundary
probes (pass on raise / output-failure / expect-failure, fail on
unexpected success), TIMEOUT via a sleeping fake server, best-effort
cleanup, artifact collection with loud required-missing reporting,
argument/output secret redaction (shared util + local fallback), suite
load→run→persist integration, and the sync asyncio.run wrappers.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from automedia.validation import engine
from automedia.validation.adapters import CLIAdapter, FileAdapter
from automedia.validation.engine import (
    Adapters,
    make_adapters,
    run_validation_scenario,
    run_validation_scenario_async,
    run_validation_suite,
    run_validation_suite_async,
)
from automedia.validation.loader import LoadError
from automedia.validation.persist import latest_run, list_runs
from automedia.validation.schema import DEFAULT_TIMEOUT_SECONDS, Expect, Scenario, Step

_MISSING_ENV = "AUTOMEDIA_VALIDATION_ENGINE_TEST_ENV"
_STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)


class FakeServer:
    """Duck-typed FastMCP stand-in: per-tool results, errors, delays (synthetic)."""

    def __init__(
        self,
        results: dict[str, object] | None = None,
        errors: dict[str, Exception] | None = None,
        delays: dict[str, float] | None = None,
    ) -> None:
        self._results = dict(results or {})
        self._errors = dict(errors or {})
        self._delays = dict(delays or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        self.calls.append((name, arguments))
        delay = self._delays.get(name, 0.0)
        if delay:
            await asyncio.sleep(delay)
        if name in self._errors:
            raise self._errors[name]
        if name in self._results:
            return self._results[name]
        return {"success": True, "data": {"tool": name}}


def tool_step(**overrides: object) -> Step:
    """A valid tool-kind step, overridable per test."""
    data: dict[str, Any] = {
        "name": "call health_check",
        "kind": "tool",
        "check": "server responds",
        "standard": "founder-expectations.F01",
        "tool": "health_check",
        "arguments": {},
        "expect": {"success": True},
    }
    data.update(overrides)
    return Step.from_dict(data)


def cli_step(command: str, **overrides: object) -> Step:
    """A valid cli-kind step with the given command, overridable per test."""
    data: dict[str, Any] = {
        "name": "run command",
        "kind": "cli",
        "check": "command runs",
        "standard": "founder-expectations.F01",
        "command": command,
        "expect": {"success": True},
    }
    data.update(overrides)
    return Step.from_dict(data)


def make_scenario(steps: list[Step], **overrides: object) -> Scenario:
    """A Scenario built directly from Step objects (no YAML involved)."""
    base: dict[str, Any] = {
        "name": "probe-scenario",
        "description": "synthetic scenario",
        "intent": "prove engine behavior",
        "steps": steps,
        "cleanup_steps": [],
    }
    base.update(overrides)
    return Scenario(**base)


def ok_server() -> FakeServer:
    """A server whose every tool call succeeds (health_check included)."""
    return FakeServer(results={"health_check": {"success": True, "data": {"status": "ok"}}})


def run_scenario(
    scenario: Scenario, server_or_adapters: FakeServer | Adapters, **kwargs: object
) -> dict[str, object]:
    """Run one scenario through the async core; returns the scenario record.

    Accepts a FakeServer (wrapped via make_adapters) or a prebuilt Adapters
    table (e.g. one without a tool adapter).
    """
    if isinstance(server_or_adapters, Adapters):
        adapters = server_or_adapters
    else:
        adapters = make_adapters(server_or_adapters)
    return asyncio.run(run_validation_scenario_async(scenario, adapters, **kwargs))


class TestGreenRun:
    def test_full_green_trace_fields(self) -> None:
        """A passing scenario records every pinned trace field (guide §3.3)."""
        record = run_scenario(make_scenario([tool_step()]), ok_server())
        assert record["scenario"] == "probe-scenario"
        assert record["status"] == "passed"
        assert record["trace_id"]
        assert record["cleanup"] == []
        assert record["error_boundary"] is False
        summary = record["summary"]
        assert summary == {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "recovered": 0,
            "artifacts_missing": [],
        }
        (trace,) = record["steps"]
        assert trace["step_index"] == 1
        assert trace["target"] == "health_check"
        assert trace["surface"] == "tool"
        assert trace["arguments"] == {}
        assert trace["passed"] is True
        assert trace["status"] == "passed"
        assert trace["failures"] == []
        assert isinstance(trace["duration"], float) and trace["duration"] >= 0
        assert trace["trace_id"] == record["trace_id"]
        assert trace["check"] == "server responds"
        assert trace["standard"] == "founder-expectations.F01"
        assert trace["output"]["data"] == {"status": "ok"}

    def test_step_index_is_1_based(self) -> None:
        record = run_scenario(
            make_scenario([tool_step(), cli_step("python3 -c 'print(1)'")]), ok_server()
        )
        assert [step["step_index"] for step in record["steps"]] == [1, 2]

    def test_partial_pass_status(self) -> None:
        scenario = make_scenario(
            [tool_step(), tool_step(tool="failing", name="fails")],
            min_passing=1,
        )
        server = FakeServer(
            results={
                "health_check": {"success": True},
                "failing": {"success": False, "error": "no"},
            }
        )
        record = run_scenario(scenario, server)
        assert record["status"] == "partial-pass"
        assert record["summary"]["passed"] == 1
        assert record["summary"]["failed"] == 1

    def test_output_and_arguments_redacted(self) -> None:
        """Secrets never reach the trace: arguments AND output are redacted."""
        server = FakeServer(
            results={"health_check": {"success": True, "data": {"token": "sk-abc"}}}
        )
        record = run_scenario(
            make_scenario([tool_step(arguments={"api_key": "sk-super-secret-123", "topic": "x"})]),
            server,
        )
        (trace,) = record["steps"]
        assert trace["arguments"] == {"api_key": "***REDACTED***", "topic": "x"}
        assert trace["output"]["data"]["token"] == "***REDACTED***"
        assert "sk-super-secret-123" not in json.dumps(record)
        assert "sk-abc" not in json.dumps(record)

    def test_sync_wrapper(self) -> None:
        record = run_validation_scenario(make_scenario([tool_step()]), make_adapters(ok_server()))
        assert record["status"] == "passed"


class TestUnconfigured:
    def test_missing_env_short_circuits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_MISSING_ENV, raising=False)
        scenario = make_scenario([tool_step()], requires_env=[_MISSING_ENV])
        record = run_scenario(scenario, ok_server())
        assert record == {
            "scenario": "probe-scenario",
            "status": "unconfigured",
            "steps": [],
            "cleanup": [],
            "trace_id": record["trace_id"],
            "reason": f"missing env: {_MISSING_ENV}",
            "error_boundary": False,
            "hard_safety_violation": False,
        }

    def test_empty_value_is_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty env value is missing (honesty rule §2.5), never a silent pass."""
        monkeypatch.setenv(_MISSING_ENV, "")
        record = run_scenario(
            make_scenario([tool_step()], requires_env=[_MISSING_ENV]), ok_server()
        )
        assert record["status"] == "unconfigured"
        assert record["reason"] == f"missing env: {_MISSING_ENV}"
        assert record["steps"] == []

    def test_no_env_gate_needed_passes(self) -> None:
        record = run_scenario(make_scenario([tool_step()]), ok_server())
        assert record["status"] == "passed"


class TestFailureAndRecovery:
    def test_failure_names_expect_key(self) -> None:
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        record = run_scenario(make_scenario([tool_step()]), server)
        assert record["status"] == "failed"
        (trace,) = record["steps"]
        assert trace["passed"] is False
        assert trace["status"] == "failed"
        assert any("expect.success" in failure for failure in trace["failures"])

    def test_recovery_passes_converts_to_recovered(self) -> None:
        """Primary fails, recovery passes -> 'recovered'; RED stays in failures."""
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        step = tool_step(
            recovery_steps=[
                {
                    "name": "recover",
                    "kind": "cli",
                    "check": "recovery command runs",
                    "standard": "founder-expectations.F01",
                    "command": "python3 -c 'print(\"fixed\")'",
                    "expect": {"success": True},
                }
            ]
        )
        record = run_scenario(make_scenario([step]), server)
        assert record["status"] == "recovered"
        (trace,) = record["steps"]
        assert trace["status"] == "recovered"
        assert trace["passed"] is True
        assert trace["failures"], "the primary failure must stay in the record"
        (recovery,) = trace["recovery"]
        assert recovery["passed"] is True
        assert recovery["surface"] == "cli"

    def test_recovery_failing_keeps_failed(self) -> None:
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        step = tool_step(
            recovery_steps=[
                {
                    "name": "recover",
                    "kind": "cli",
                    "check": "recovery command runs",
                    "standard": "founder-expectations.F01",
                    "command": "python3 -c 'import sys; sys.exit(2)'",
                    "expect": {"success": True},
                }
            ]
        )
        record = run_scenario(make_scenario([step]), server)
        assert record["status"] == "failed"
        (trace,) = record["steps"]
        assert trace["status"] == "failed"
        assert trace["passed"] is False

    def test_recovery_not_run_when_primary_passes(self) -> None:
        record = run_scenario(make_scenario([tool_step()]), ok_server())
        assert "recovery" not in record["steps"][0]


class TestErrorBoundary:
    def test_probe_passes_when_tool_raises(self) -> None:
        server = FakeServer(errors={"health_check": RuntimeError("denied")})
        record = run_scenario(make_scenario([tool_step(error_boundary=True)]), server)
        assert record["status"] == "passed"
        (trace,) = record["steps"]
        assert trace["status"] == "passed"
        assert trace["passed"] is True
        assert trace["note"] == "error_boundary: true"

    def test_probe_passes_when_output_reports_failure(self) -> None:
        """A tool reporting success:false is an error occurring — the probe passes."""
        server = FakeServer(results={"health_check": {"success": False, "error": "denied"}})
        step = tool_step(error_boundary=True, expect={"success": False})
        record = run_scenario(make_scenario([step]), server)
        assert record["status"] == "passed"
        assert record["steps"][0]["note"] == "error_boundary: true"

    def test_probe_passes_when_expect_fails(self) -> None:
        """A boundary step that FAILS counts as passing (pinned engine contract)."""
        server = FakeServer(results={"health_check": {"success": False, "error": "denied"}})
        record = run_scenario(make_scenario([tool_step(error_boundary=True)]), server)
        assert record["status"] == "passed"
        (trace,) = record["steps"]
        assert trace["status"] == "passed"
        assert trace["failures"], "the error manifestation stays documented"

    def test_probe_fails_on_unexpected_success(self) -> None:
        record = run_scenario(make_scenario([tool_step(error_boundary=True)]), ok_server())
        assert record["status"] == "failed"
        (trace,) = record["steps"]
        assert trace["status"] == "failed"
        assert trace["passed"] is False
        assert trace["failures"] == ["boundary probe expected an error, got success"]
        assert "note" not in trace

    def test_scenario_flag_copied_into_record(self) -> None:
        record = run_scenario(make_scenario([tool_step()], error_boundary=True), ok_server())
        assert record["error_boundary"] is True


class TestTimeout:
    def test_slow_tool_step_times_out(self) -> None:
        """A tool step sleeping past timeout_seconds fails with the timeout reason."""
        server = FakeServer(
            results={"health_check": {"success": True}},
            delays={"health_check": 0.3},
        )
        step = tool_step(timeout_seconds=0.05)
        record = run_scenario(make_scenario([step]), server)
        assert record["status"] == "failed"
        (trace,) = record["steps"]
        assert trace["status"] == "failed"
        assert trace["passed"] is False
        assert "timed out after 0.05s" in str(trace["output"])

    def test_default_timeout_applied(self) -> None:
        """Without timeout_seconds the project ceiling from the schema applies."""
        server = FakeServer(
            results={"health_check": {"success": True}},
            delays={"health_check": 0.05},
        )
        step = tool_step()
        record = run_scenario(make_scenario([step]), server)
        assert record["status"] == "passed", "default ceiling (180s) is far above the delay"

    def test_default_timeout_constant(self) -> None:
        assert DEFAULT_TIMEOUT_SECONDS == 180.0


class TestCleanup:
    def test_cleanup_runs_after_failure_and_never_influences_status(self) -> None:
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        cleanup = cli_step("python3 -c 'import sys; sys.exit(3)'", name="cleanup")
        record = run_scenario(make_scenario([tool_step()], cleanup_steps=[cleanup]), server)
        assert record["status"] == "failed"
        (cleanup_trace,) = record["cleanup"]
        assert cleanup_trace["step_index"] == 0
        assert cleanup_trace["passed"] is False
        assert cleanup_trace["surface"] == "cli"

    def test_cleanup_failure_keeps_scenario_passed(self) -> None:
        cleanup = cli_step("python3 -c 'import sys; sys.exit(3)'", name="cleanup")
        record = run_scenario(make_scenario([tool_step()], cleanup_steps=[cleanup]), ok_server())
        assert record["status"] == "passed"
        assert record["cleanup"][0]["status"] == "failed"


class TestArtifacts:
    def test_green_step_artifacts_copied_and_missing_loud(self, tmp_path: Path) -> None:
        (tmp_path / "out.json").write_text("{}", encoding="utf-8")
        step = tool_step(
            name="collect outputs",
            collect_artifacts=[
                {"path": "out.json", "required": True},
                {"path": "missing.json", "required": True},
            ],
        )
        runs_root = tmp_path / "runs"
        record = run_scenario(make_scenario([step]), ok_server(), run_root=runs_root, cwd=tmp_path)
        (trace,) = record["steps"]
        (copied, missing) = trace["artifacts"]
        assert copied["ok"] is True
        assert copied["copied_to"].endswith("1-out.json")
        assert Path(copied["copied_to"]).is_file()
        assert missing["ok"] is False
        assert missing["reason"] == "missing"
        assert record["summary"]["artifacts_missing"] == [
            "step 1 (collect outputs): required artifact 'missing.json' missing"
        ]

    def test_no_run_root_skips_collection(self, tmp_path: Path) -> None:
        step = tool_step(collect_artifacts=[{"path": "out.json"}])
        record = run_scenario(make_scenario([step]), ok_server(), cwd=tmp_path)
        assert "artifacts" not in record["steps"][0]

    def test_failed_step_never_collects(self, tmp_path: Path) -> None:
        (tmp_path / "out.json").write_text("{}", encoding="utf-8")
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        step = tool_step(collect_artifacts=[{"path": "out.json"}])
        record = run_scenario(
            make_scenario([step]), server, run_root=tmp_path / "runs", cwd=tmp_path
        )
        assert "artifacts" not in record["steps"][0]


class TestDispatch:
    def test_tool_step_without_server_fails_loudly(self) -> None:
        record = run_scenario(
            make_scenario([tool_step()]), Adapters({"cli": CLIAdapter(), "file": FileAdapter()})
        )
        (trace,) = record["steps"]
        assert trace["status"] == "failed"
        assert "no MCP server" in str(trace["output"]["error"])

    def test_unknown_kind_fails_with_reason(self) -> None:
        step = Step(
            name="probe",
            kind="http",
            check="probe",
            standard="founder-expectations.F01",
            command="http://example.test",
            expect=Expect(),
        )
        record = run_scenario(make_scenario([step]), make_adapters(ok_server()))
        assert record["steps"][0]["status"] == "failed"
        assert "no adapter registered for step kind 'http'" in str(
            record["steps"][0]["output"]["error"]
        )

    def test_make_adapters_always_registers_cli_and_file(self) -> None:
        adapters = make_adapters(None)
        assert adapters.get("cli") is not None
        assert adapters.get("file") is not None
        assert adapters.get("tool") is None


class TestRedaction:
    def test_uses_shared_util(self) -> None:
        assert engine._redact({"api_key": "sk-1", "topic": "x"}) == {
            "api_key": "***REDACTED***",
            "topic": "x",
        }

    def test_local_fallback_when_import_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If _shared._redact_secrets cannot be imported, the local redactor applies."""
        stub = types.ModuleType("automedia.mcp.tools._shared")
        monkeypatch.setitem(sys.modules, "automedia.mcp.tools._shared", stub)
        assert engine._redact({"token": "sk-123", "topic": "x"}) == {
            "token": "***REDACTED***",
            "topic": "x",
        }
        assert engine._redact("plain string") == "plain string"


class TestHardSafety:
    """Hard-safety semantics (issue #86): ``scenario.hard and status != "passed"``.

    The formula is pure and independent of aggregate_status, partial-pass,
    and recovery — only "passed" clears a hard scenario.  Unconfigured is
    never "passed", so a hard scenario that cannot configure BLOCKS.
    """

    def test_hard_scenario_passed_no_violation(self) -> None:
        record = run_scenario(make_scenario([tool_step()], hard=True), ok_server())
        assert record["status"] == "passed"
        assert record["hard_safety_violation"] is False

    def test_hard_scenario_failed_violation_true(self) -> None:
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        record = run_scenario(make_scenario([tool_step()], hard=True), server)
        assert record["status"] == "failed"
        assert record["hard_safety_violation"] is True

    def test_hard_unconfigured_violation_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """KEY hard-safety behavior: unconfigured is never passed — it blocks."""
        monkeypatch.delenv(_MISSING_ENV, raising=False)
        scenario = make_scenario([tool_step()], hard=True, requires_env=[_MISSING_ENV])
        record = run_scenario(scenario, ok_server())
        assert record["status"] == "unconfigured"
        assert record["hard_safety_violation"] is True

    def test_non_hard_failed_not_violation(self) -> None:
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        record = run_scenario(make_scenario([tool_step()]), server)
        assert record["status"] == "failed"
        assert record["hard_safety_violation"] is False

    def test_hard_recovered_violation_true(self) -> None:
        """Recovery never masks hard safety: recovered != passed."""
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        step = tool_step(
            recovery_steps=[
                {
                    "name": "recover",
                    "kind": "cli",
                    "check": "recovery command runs",
                    "standard": "founder-expectations.F01",
                    "command": "python3 -c 'print(\"fixed\")'",
                    "expect": {"success": True},
                }
            ]
        )
        record = run_scenario(make_scenario([step], hard=True), server)
        assert record["status"] == "recovered"
        assert record["hard_safety_violation"] is True

    def test_hard_partial_pass_violation_true(self) -> None:
        """Partial-pass never masks hard safety either."""
        scenario = make_scenario(
            [tool_step(), tool_step(tool="failing", name="fails")],
            hard=True,
            min_passing=1,
        )
        server = FakeServer(
            results={
                "health_check": {"success": True},
                "failing": {"success": False, "error": "no"},
            }
        )
        record = run_scenario(scenario, server)
        assert record["status"] == "partial-pass"
        assert record["hard_safety_violation"] is True


GREEN_YAML = """\
name: green-suite
description: suite green path
intent: prove tool and cli steps pass
steps:
  - name: health
    kind: tool
    check: server responds
    standard: founder-expectations.F01
    tool: health_check
    arguments: {}
    expect:
      success: true
  - name: echo
    kind: cli
    check: stdout carries marker
    standard: builtin.data_has
    command: python3 -c "print('suite-ok')"
    expect:
      success: true
      stdout_has:
        - suite-ok
"""

RED_YAML = """\
name: red-suite
description: suite red path
intent: prove a failing step is recorded loudly
steps:
  - name: failing
    kind: tool
    check: tool succeeds
    standard: founder-expectations.F01
    tool: failing_tool
    arguments: {}
    expect:
      success: true
"""

UNCONFIGURED_YAML = f"""\
name: unconfigured-suite
description: env-gated suite scenario
intent: prove unconfigured honesty
requires_env:
  - {_MISSING_ENV}
steps:
  - name: never runs
    kind: cli
    check: never dispatched
    standard: builtin.unconfigured
    command: python3 -c "raise SystemExit(1)"
    expect:
      success: true
"""


HARD_FAIL_YAML = """\
name: hard-fail-suite
description: hard-safety scenario that fails
intent: prove a failing hard scenario records a violation and blocks the suite
hard: true
steps:
  - name: failing
    kind: tool
    check: tool succeeds
    standard: founder-expectations.F01
    tool: failing_tool
    arguments: {}
    expect:
      success: true
"""

HARD_PASS_YAML = """\
name: hard-pass-suite
description: hard-safety scenario that passes
intent: prove a passing hard scenario clears hard safety
hard: true
steps:
  - name: health
    kind: tool
    check: server responds
    standard: founder-expectations.F01
    tool: health_check
    arguments: {}
    expect:
      success: true
"""


@pytest.fixture
def suite_scenarios_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scenarios library: three committed YAMLs + the standards handbook."""
    root = tmp_path / "scenarios"
    root.mkdir()
    shutil.copy2(_STANDARDS_FIXTURE, root / "STANDARDS.md")
    (root / "green.yaml").write_text(GREEN_YAML, encoding="utf-8")
    (root / "red.yaml").write_text(RED_YAML, encoding="utf-8")
    (root / "unconfigured.yaml").write_text(UNCONFIGURED_YAML, encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))
    monkeypatch.delenv(_MISSING_ENV, raising=False)
    return root


def suite_server() -> FakeServer:
    return FakeServer(
        results={
            "health_check": {"success": True, "data": {"status": "ok"}},
            "failing_tool": {"success": False, "error": "boom"},
        }
    )


class TestSuite:
    def test_suite_run_persists(self, suite_scenarios_dir: Path, tmp_path: Path) -> None:
        runs_root = tmp_path / "runs"
        record = asyncio.run(
            run_validation_suite_async(suite_server(), suite_scenarios_dir, runs_root=runs_root)
        )
        assert record["trace_id"]
        assert record["generated_at"]
        assert len(record["scenarios"]) == 3
        statuses = {r["scenario"]: r["status"] for r in record["scenarios"]}
        assert statuses == {
            "green-suite": "passed",
            "red-suite": "failed",
            "unconfigured-suite": "unconfigured",
        }
        # ONE UUID per run, threaded into every scenario (guide §3.1 phase 5).
        assert all(r["trace_id"] == record["trace_id"] for r in record["scenarios"])
        unconfigured = next(r for r in record["scenarios"] if r["scenario"] == "unconfigured-suite")
        assert unconfigured["reason"] == f"missing env: {_MISSING_ENV}"
        red = next(r for r in record["scenarios"] if r["scenario"] == "red-suite")
        assert any("expect.success" in f for f in red["steps"][0]["failures"])
        # Persisted: immutable run dir + latest.txt pointer.
        run_names = list_runs(runs_root)
        assert len(run_names) == 1
        assert latest_run(runs_root) == run_names[0]
        stored = json.loads(
            (runs_root / run_names[0] / "scenarios.json").read_text(encoding="utf-8")
        )
        assert stored["trace_id"] == record["trace_id"]
        assert stored["generated_at"] == record["generated_at"]
        assert len(stored["scenarios"]) == 3

    def test_suite_aggregates_violations_and_blocked(
        self, suite_scenarios_dir: Path, tmp_path: Path
    ) -> None:
        """A hard-failed scenario plus a hard-passed one: only the failed blocks."""
        (suite_scenarios_dir / "hard-fail.yaml").write_text(HARD_FAIL_YAML, encoding="utf-8")
        (suite_scenarios_dir / "hard-pass.yaml").write_text(HARD_PASS_YAML, encoding="utf-8")
        runs_root = tmp_path / "runs"
        record = asyncio.run(
            run_validation_suite_async(suite_server(), suite_scenarios_dir, runs_root=runs_root)
        )
        statuses = {r["scenario"]: r["status"] for r in record["scenarios"]}
        assert statuses["hard-fail-suite"] == "failed"
        assert statuses["hard-pass-suite"] == "passed"
        assert record["hard_safety_violations"] == ["hard-fail-suite"]
        assert record["blocked"] is True

    def test_suite_no_violations_not_blocked(
        self, suite_scenarios_dir: Path, tmp_path: Path
    ) -> None:
        """All hard scenarios pass -> no violations, nothing blocked."""
        (suite_scenarios_dir / "hard-pass.yaml").write_text(HARD_PASS_YAML, encoding="utf-8")
        runs_root = tmp_path / "runs"
        record = asyncio.run(
            run_validation_suite_async(suite_server(), suite_scenarios_dir, runs_root=runs_root)
        )
        assert record["hard_safety_violations"] == []
        assert record["blocked"] is False

    def test_suite_save_requires_runs_root(self, suite_scenarios_dir: Path) -> None:
        with pytest.raises(ValueError, match="runs_root"):
            asyncio.run(run_validation_suite_async(suite_server(), suite_scenarios_dir))

    def test_suite_save_false_leaves_no_evidence(
        self, suite_scenarios_dir: Path, tmp_path: Path
    ) -> None:
        runs_root = tmp_path / "runs"
        record = asyncio.run(
            run_validation_suite_async(
                suite_server(), suite_scenarios_dir, runs_root=runs_root, save=False
            )
        )
        assert len(record["scenarios"]) == 3
        assert not runs_root.exists()

    def test_suite_without_server_fails_tool_steps_loudly(
        self, suite_scenarios_dir: Path, tmp_path: Path
    ) -> None:
        record = asyncio.run(
            run_validation_suite_async(None, suite_scenarios_dir, runs_root=tmp_path / "runs")
        )
        green = next(r for r in record["scenarios"] if r["scenario"] == "green-suite")
        assert green["status"] == "failed"
        assert "no MCP server" in str(green["steps"][0]["output"]["error"])
        # The cli step of the same scenario still ran (per-step dispatch).
        assert green["steps"][1]["status"] == "passed"

    def test_suite_sync_wrapper(self, suite_scenarios_dir: Path, tmp_path: Path) -> None:
        record = run_validation_suite(
            suite_server(), suite_scenarios_dir, runs_root=tmp_path / "runs"
        )
        assert len(record["scenarios"]) == 3

    def test_load_error_propagates_loudly(self, suite_scenarios_dir: Path, tmp_path: Path) -> None:
        (suite_scenarios_dir / "bad.yaml").write_text("name: [broken", encoding="utf-8")
        with pytest.raises(LoadError, match=r"bad\.yaml"):
            asyncio.run(
                run_validation_suite_async(
                    suite_server(), suite_scenarios_dir, runs_root=tmp_path / "runs"
                )
            )

    def test_empty_scenarios_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        shutil.copy2(_STANDARDS_FIXTURE, empty / "STANDARDS.md")
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(empty))
        record = asyncio.run(
            run_validation_suite_async(suite_server(), empty, runs_root=tmp_path / "runs")
        )
        assert record["scenarios"] == []


class TestErrorEnvelopeDefault:
    """T-04: an error envelope fails a step unless ``error_expected`` opts in."""

    def test_tool_error_step_fails_without_opt_out(self) -> None:
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        step = tool_step(expect={"data_has": ["x"]})
        record = run_scenario(make_scenario([step]), server)

        assert record["status"] == "failed"
        assert any("expect.error_expected" in f for f in record["steps"][0]["failures"])

    def test_tool_error_step_passes_with_opt_out(self) -> None:
        server = FakeServer(results={"health_check": {"success": False, "error": "boom"}})
        step = tool_step(expect={"success": False, "error_expected": True})
        record = run_scenario(make_scenario([step]), server)

        assert record["status"] == "passed"

    def test_cli_nonzero_step_fails_without_opt_out(self) -> None:
        step = cli_step("python3 -c 'import sys; sys.exit(3)'", expect={"exit_code": 3})
        record = run_scenario(make_scenario([step]), make_adapters(ok_server()))

        assert record["status"] == "failed"
        assert any("expect.error_expected" in f for f in record["steps"][0]["failures"])

    def test_cli_nonzero_step_passes_with_opt_out(self) -> None:
        step = cli_step(
            "python3 -c 'import sys; sys.exit(3)'",
            expect={"exit_code": 3, "error_expected": True},
        )
        record = run_scenario(make_scenario([step]), make_adapters(ok_server()))

        assert record["status"] == "passed"
