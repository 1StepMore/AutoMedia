"""Unit tests for the expect evaluator (W1-T6).

Covers: every assertion type pass + fail, conjoined multi-key blocks,
artifact checks against ``tmp_path`` (never the repo tree), gate_records_pass
against a synthetic project-info JSON, recovery verdict logic, and
aggregate_status under all-or-nothing / min_passing / pass_ratio policies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automedia.validation.expects import (
    SimpleRecord,
    aggregate_status,
    apply_recovery,
    evaluate_expect,
    should_run_recovery,
)
from automedia.validation.schema import Expect, Scenario, Step

# --- helpers ---------------------------------------------------------------


def expect(**fields: object) -> Expect:
    """Build an Expect from field overrides (all fields optional)."""
    return Expect.from_dict(fields)


def step_dict(
    *, kind: str = "file", command: str | None = None, **overrides: object
) -> dict[str, object]:
    """A valid step dict; call-spec fields depend on kind."""
    base: dict[str, object] = {
        "name": "s",
        "kind": kind,
        "check": "c",
        "standard": "st",
        "expect": {},
    }
    if kind == "tool":
        base["tool"] = "health_check"
        base["arguments"] = {}
    else:
        base["command"] = command or "output/log.txt"
    base.update(overrides)
    return base


def step(*, kind: str = "file", command: str | None = None, **overrides: object) -> Step:
    """A parsed Step (for evaluate_expect's ``step`` parameter)."""
    return Step.from_dict(step_dict(kind=kind, command=command, **overrides))


def scenario(**overrides: object) -> Scenario:
    base: dict[str, object] = {
        "name": "s",
        "description": "d",
        "intent": "i",
        "steps": [step_dict()],
    }
    base.update(overrides)
    return Scenario.from_dict(base)


def gate_json(data: object) -> str:
    """Serialized synthetic project-info JSON (tests write it into tmp_path)."""
    return json.dumps(data)


@pytest.fixture()
def cwd(tmp_path: Path) -> Path:
    return tmp_path


# --- success ---------------------------------------------------------------


class TestSuccess:
    def test_passes_when_envelope_reports_success(self) -> None:
        r = evaluate_expect(expect(success=True), {"success": True})
        assert r.passed is True
        assert r.failures == []

    def test_fails_naming_key_and_observed_value(self) -> None:
        r = evaluate_expect(expect(success=True), {"success": False})
        assert r.passed is False
        assert r.failures[0] == "expect.success: expected True, observed False"
        assert any("expect.error_expected" in f for f in r.failures)

    def test_not_evaluated_when_absent(self) -> None:
        # output carries no "success" key; block asserts only exit_code
        r = evaluate_expect(expect(exit_code=0), {"exit_code": 0})
        assert r.passed is True


# --- data_has --------------------------------------------------------------


class TestDataHas:
    def test_passes_when_all_keys_present(self) -> None:
        r = evaluate_expect(expect(data_has=["a", "b"]), {"data": {"a": 1, "b": 2, "c": 3}})
        assert r.passed is True

    def test_fails_naming_missing_keys_and_observed_keys(self) -> None:
        r = evaluate_expect(expect(data_has=["a", "z"]), {"data": {"a": 1, "b": 2}})
        assert r.passed is False
        assert "expect.data_has" in r.failures[0]
        assert "'z'" in r.failures[0]
        assert "'a'" in r.failures[0]  # present keys shown too

    def test_fails_when_data_missing(self) -> None:
        r = evaluate_expect(expect(data_has=["a"]), {})
        assert r.passed is False
        assert "expect.data_has" in r.failures[0]

    def test_fails_when_data_not_a_dict(self) -> None:
        r = evaluate_expect(expect(data_has=["a"]), {"data": [1, 2]})
        assert r.passed is False
        assert "expect.data_has" in r.failures[0]


# --- exit_code -------------------------------------------------------------


class TestExitCode:
    def test_passes_on_exact_match(self) -> None:
        r = evaluate_expect(expect(exit_code=0), {"exit_code": 0})
        assert r.passed is True

    def test_fails_naming_key_and_observed_value(self) -> None:
        r = evaluate_expect(expect(exit_code=0), {"exit_code": 2})
        assert r.passed is False
        assert r.failures[0] == "expect.exit_code: expected 0, observed 2"
        assert any("expect.error_expected" in f for f in r.failures)

    def test_fails_when_missing_from_output(self) -> None:
        r = evaluate_expect(expect(exit_code=0), {})
        assert r.passed is False
        assert "expected 0, observed None" in r.failures[0]


# --- stdout_has / stderr_has ------------------------------------------------


class TestStdoutHas:
    def test_passes_on_substring_containment(self) -> None:
        r = evaluate_expect(expect(stdout_has=["ffmpeg"]), {"stdout": "ffmpeg 6.1 ready"})
        assert r.passed is True

    def test_requires_every_listed_substring(self) -> None:
        r = evaluate_expect(expect(stdout_has=["a", "b"]), {"stdout": "a only"})
        assert r.passed is False
        assert "expect.stdout_has" in r.failures[0]
        assert "'b'" in r.failures[0]

    def test_fails_when_stdout_missing(self) -> None:
        r = evaluate_expect(expect(stdout_has=["x"]), {})
        assert r.passed is False
        assert "expect.stdout_has" in r.failures[0]


class TestStderrHas:
    def test_passes_on_substring_containment(self) -> None:
        r = evaluate_expect(expect(stderr_has=["warn"]), {"stderr": "warning: dep"})
        assert r.passed is True

    def test_fails_naming_key_and_observed(self) -> None:
        r = evaluate_expect(expect(stderr_has=["boom"]), {"stderr": "all good"})
        assert r.passed is False
        assert "expect.stderr_has" in r.failures[0]
        assert "'boom'" in r.failures[0]

    def test_fails_without_crashing_when_stderr_not_a_str(self) -> None:
        r = evaluate_expect(expect(stderr_has=["x"]), {"stderr": None})
        assert r.passed is False
        assert "expect.stderr_has" in r.failures[0]


# --- artifact_exists ----------------------------------------------------------


class TestArtifactExists:
    def test_passes_when_file_exists(self, cwd: Path) -> None:
        (cwd / "out.txt").write_text("data", encoding="utf-8")
        r = evaluate_expect(expect(artifact_exists="out.txt"), {}, cwd=cwd)
        assert r.passed is True

    def test_fails_when_missing(self, cwd: Path) -> None:
        r = evaluate_expect(expect(artifact_exists="nope.txt"), {}, cwd=cwd)
        assert r.passed is False
        assert "expect.artifact_exists" in r.failures[0]
        assert "nope.txt" in r.failures[0]

    def test_directory_is_not_a_file(self, cwd: Path) -> None:
        (cwd / "adir").mkdir()
        r = evaluate_expect(expect(artifact_exists="adir"), {}, cwd=cwd)
        assert r.passed is False


# --- artifact_size_min ---------------------------------------------------------


class TestArtifactSizeMin:
    def test_passes_when_size_equals_min(self, cwd: Path) -> None:
        (cwd / "out.txt").write_text("12345", encoding="utf-8")  # 5 bytes
        r = evaluate_expect(expect(artifact_exists="out.txt", artifact_size_min=5), {}, cwd=cwd)
        assert r.passed is True

    def test_passes_when_larger(self, cwd: Path) -> None:
        (cwd / "out.txt").write_text("123456", encoding="utf-8")
        r = evaluate_expect(expect(artifact_exists="out.txt", artifact_size_min=5), {}, cwd=cwd)
        assert r.passed is True

    def test_fails_naming_observed_size(self, cwd: Path) -> None:
        (cwd / "out.txt").write_text("1234", encoding="utf-8")  # 4 bytes
        r = evaluate_expect(expect(artifact_exists="out.txt", artifact_size_min=5), {}, cwd=cwd)
        assert r.passed is False
        assert "expect.artifact_size_min" in r.failures[0]
        assert "4" in r.failures[0]
        assert "5" in r.failures[0]

    def test_fails_defensively_without_artifact_exists(self, cwd: Path) -> None:
        # schema rejects this, but Expect built programmatically must not crash
        e = Expect(artifact_size_min=5)
        r = evaluate_expect(e, {}, cwd=cwd)
        assert r.passed is False
        assert "expect.artifact_size_min" in r.failures[0]

    def test_fails_when_target_file_missing(self, cwd: Path) -> None:
        r = evaluate_expect(expect(artifact_exists="gone.txt", artifact_size_min=5), {}, cwd=cwd)
        assert r.passed is False
        assert any("expect.artifact_size_min" in f for f in r.failures)


# --- artifact_nonempty -----------------------------------------------------------


class TestArtifactNonempty:
    def test_passes_when_file_has_content(self, cwd: Path) -> None:
        (cwd / "log.txt").write_text("x", encoding="utf-8")
        r = evaluate_expect(expect(artifact_nonempty="log.txt"), {}, cwd=cwd)
        assert r.passed is True

    def test_fails_on_empty_file(self, cwd: Path) -> None:
        (cwd / "log.txt").write_text("", encoding="utf-8")
        r = evaluate_expect(expect(artifact_nonempty="log.txt"), {}, cwd=cwd)
        assert r.passed is False
        assert "expect.artifact_nonempty" in r.failures[0]

    def test_fails_on_missing_file(self, cwd: Path) -> None:
        r = evaluate_expect(expect(artifact_nonempty="log.txt"), {}, cwd=cwd)
        assert r.passed is False
        assert "expect.artifact_nonempty" in r.failures[0]


# --- gate_records_pass -----------------------------------------------------------


class TestGateRecordsPass:
    def _file_step(self) -> Step:
        return step(kind="file", command="info.json")

    def test_passes_on_gates_list(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(
            gate_json({"status": "passed", "gates": [{"name": "G0", "passed": True}]}),
            encoding="utf-8",
        )
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is True

    def test_passes_on_gate_results_key(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(
            gate_json({"gate_results": [{"gate": "V1"}]}), encoding="utf-8"
        )
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is True

    def test_passes_on_passed_gates_key(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(gate_json({"passed_gates": ["G0", "G1"]}), encoding="utf-8")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is True

    def test_bare_status_no_longer_passes(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(gate_json({"status": "passed"}), encoding="utf-8")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False
        assert "no gate records" in r.failures[0]

    def test_fails_on_one_failed_gate_entry(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(
            gate_json(
                {
                    "gates": [
                        {"name": "G0", "passed": True},
                        {"name": "G1", "passed": False},
                    ]
                }
            ),
            encoding="utf-8",
        )
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False
        assert "expect.gate_records_pass" in r.failures[0]
        assert "G1" in r.failures[0]

    def test_fails_on_failed_status_entry(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(
            gate_json({"gates": [{"name": "G0", "status": "failed"}]}),
            encoding="utf-8",
        )
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False
        assert "expect.gate_records_pass" in r.failures[0]
        assert "G0" in r.failures[0]

    def test_passes_when_every_entry_passes(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(
            gate_json(
                {
                    "gate_results": [
                        {"gate": "G0", "status": "passed"},
                        {"gate": "G1", "passed": True},
                    ]
                }
            ),
            encoding="utf-8",
        )
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is True

    def test_fails_on_non_passing_status(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(gate_json({"status": "running"}), encoding="utf-8")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False
        assert "expect.gate_records_pass" in r.failures[0]

    def test_fails_on_empty_gates_list(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(gate_json({"gates": []}), encoding="utf-8")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False

    def test_fails_on_gates_not_a_list(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(gate_json({"gates": {"G0": True}}), encoding="utf-8")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False

    def test_fails_on_invalid_json(self, cwd: Path) -> None:
        (cwd / "info.json").write_text("{not json", encoding="utf-8")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False
        assert "expect.gate_records_pass" in r.failures[0]

    def test_fails_on_non_object_json(self, cwd: Path) -> None:
        (cwd / "info.json").write_text(gate_json(["not", "an", "object"]), encoding="utf-8")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False
        assert "expect.gate_records_pass" in r.failures[0]

    def test_fails_when_artifact_missing(self, cwd: Path) -> None:
        # resolvable path (step.command) but no file on disk
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=self._file_step(), cwd=cwd)
        assert r.passed is False
        assert "expect.gate_records_pass" in r.failures[0]
        assert "does not exist" in r.failures[0]

    def test_no_resolvable_path_fails(self) -> None:
        s = step(kind="tool")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=s)
        assert r.passed is False
        assert "no artifact path resolvable" in r.failures[0]

    def test_resolution_order_artifact_exists_wins(self, cwd: Path) -> None:
        (cwd / "win.json").write_text(
            gate_json({"gates": [{"name": "G0", "passed": True}]}), encoding="utf-8"
        )
        (cwd / "command.json").write_text(
            gate_json({"gates": [{"name": "G0", "passed": False}]}), encoding="utf-8"
        )
        s = step(kind="file", command="command.json")
        e = expect(gate_records_pass=True, artifact_exists="win.json")
        r = evaluate_expect(e, {}, step=s, cwd=cwd)
        assert r.passed is True

    def test_resolution_falls_back_to_step_command_for_file_kind(self, cwd: Path) -> None:
        (cwd / "command.json").write_text(
            gate_json({"gates": [{"name": "G0", "passed": True}]}), encoding="utf-8"
        )
        s = step(kind="file", command="command.json")
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=s, cwd=cwd)
        assert r.passed is True

    def test_resolution_falls_back_to_first_collect_artifact(self, cwd: Path) -> None:
        (cwd / "collected.json").write_text(
            gate_json({"gates": [{"name": "G0", "passed": True}]}), encoding="utf-8"
        )
        s = step(
            kind="tool",
            collect_artifacts=[{"path": "collected.json"}, {"path": "other.json"}],
        )
        r = evaluate_expect(expect(gate_records_pass=True), {}, step=s, cwd=cwd)
        assert r.passed is True


# --- conjoined semantics ---------------------------------------------------------


class TestConjoined:
    def test_all_assertions_must_hold(self) -> None:
        r = evaluate_expect(
            expect(success=True, exit_code=0, stdout_has=["ok"]),
            {"success": True, "exit_code": 1, "stdout": "ok"},
        )
        assert r.passed is False
        # the mismatching assertion and the error-envelope default are reported
        assert r.failures[0] == "expect.exit_code: expected 0, observed 1"
        assert any("expect.error_expected" in f for f in r.failures)

    def test_all_failures_are_collected(self) -> None:
        r = evaluate_expect(
            expect(success=True, exit_code=0, stdout_has=["x"]),
            {"success": False, "exit_code": 3, "stdout": "y"},
        )
        assert r.passed is False
        assert len(r.failures) == 4
        assert sum(1 for f in r.failures if "expect.error_expected" in f) == 1

    def test_empty_block_passes_trivially_on_success(self) -> None:
        r = evaluate_expect(expect(), {"success": True})
        assert r.passed is True
        assert r.failures == []

    def test_mixed_artifact_and_envelope(self, cwd: Path) -> None:
        (cwd / "out.txt").write_text("data", encoding="utf-8")
        r = evaluate_expect(
            expect(success=True, artifact_exists="out.txt"),
            {"success": True},
            cwd=cwd,
        )
        assert r.passed is True


# --- cwd isolation ----------------------------------------------------------------


class TestCwdIsolation:
    def test_relative_paths_resolve_against_cwd(self, cwd: Path) -> None:
        (cwd / "only-here.txt").write_text("x", encoding="utf-8")
        r = evaluate_expect(expect(artifact_exists="only-here.txt"), {}, cwd=cwd)
        assert r.passed is True

    def test_default_cwd_is_process_cwd(self, tmp_path: Path) -> None:
        # no cwd passed: the path must NOT be found under tmp_path
        (tmp_path / "x.txt").write_text("x", encoding="utf-8")
        r = evaluate_expect(expect(artifact_exists="x.txt"), {})
        assert r.passed is False

    def test_absolute_paths_are_resolved_as_is(self, cwd: Path) -> None:
        p = cwd / "abs.txt"
        p.write_text("x", encoding="utf-8")
        r = evaluate_expect(expect(artifact_exists=str(p)), {}, cwd=cwd)
        assert r.passed is True


# --- recovery logic ----------------------------------------------------------------


class TestRecovery:
    def test_should_run_recovery_only_when_primary_failed(self) -> None:
        assert should_run_recovery(SimpleRecord(passed=True, status="passed")) is False
        assert should_run_recovery(SimpleRecord(passed=False, status="failed")) is True

    def test_primary_passed_never_triggered_recovery(self) -> None:
        assert apply_recovery(True, []) == "passed"
        assert apply_recovery(True, [True, False]) == "passed"

    def test_primary_failed_with_any_recovery_pass_is_recovered(self) -> None:
        assert apply_recovery(False, [False, True, False]) == "recovered"

    def test_primary_failed_with_all_recoveries_failing_is_failed(self) -> None:
        assert apply_recovery(False, [False, False]) == "failed"

    def test_primary_failed_without_recovery_steps_is_failed(self) -> None:
        assert apply_recovery(False, []) == "failed"

    def test_recovery_never_erases_red(self) -> None:
        # "recovered", never "passed": the failure stays on the record
        assert apply_recovery(False, [True]) == "recovered"


# --- aggregate_status ----------------------------------------------------------------


class TestAggregate:
    def test_all_passed_is_passed(self) -> None:
        s = scenario(steps=[step_dict()])
        assert aggregate_status(s, [SimpleRecord(True, "passed"), True]) == "passed"

    def test_all_passed_with_one_recovered_is_recovered(self) -> None:
        s = scenario(steps=[step_dict()])
        r = aggregate_status(
            s,
            [
                SimpleRecord(True, "recovered"),
                SimpleRecord(True, "passed"),
            ],
        )
        assert r == "recovered"

    def test_all_or_nothing_default_fails_on_any_failure(self) -> None:
        s = scenario(steps=[step_dict()])
        assert aggregate_status(s, [SimpleRecord(False, "failed"), True]) == "failed"

    def test_min_passing_met_is_partial_pass(self) -> None:
        s = scenario(min_passing=2, steps=[step_dict()])
        r = aggregate_status(s, [SimpleRecord(False, "failed"), True, True])
        assert r == "partial-pass"

    def test_min_passing_not_met_is_failed(self) -> None:
        s = scenario(min_passing=3, steps=[step_dict()])
        r = aggregate_status(s, [SimpleRecord(False, "failed"), True, True])
        assert r == "failed"

    def test_pass_ratio_met_is_partial_pass(self) -> None:
        s = scenario(pass_ratio=0.5, steps=[step_dict()])
        r = aggregate_status(s, [SimpleRecord(False, "failed"), True])
        assert r == "partial-pass"

    def test_pass_ratio_not_met_is_failed(self) -> None:
        s = scenario(pass_ratio=0.9, steps=[step_dict()])
        r = aggregate_status(s, [SimpleRecord(False, "failed"), True])
        assert r == "failed"

    def test_min_passing_takes_precedence_over_pass_ratio(self) -> None:
        s = scenario(min_passing=2, pass_ratio=0.99, steps=[step_dict()])
        r = aggregate_status(s, [SimpleRecord(False, "failed"), True, True])
        assert r == "partial-pass"

    def test_recovered_counts_as_passed_for_partial_policy(self) -> None:
        s = scenario(min_passing=1, steps=[step_dict()])
        r = aggregate_status(s, [SimpleRecord(False, "failed"), SimpleRecord(True, "recovered")])
        assert r == "partial-pass"


# --- T-02: output_has (top-level envelope keys) -------------------------------


class TestOutputHas:
    def test_passes_when_all_top_level_keys_present(self) -> None:
        r = evaluate_expect(
            expect(output_has=["categories", "tool_count"]),
            {"categories": {"a": []}, "tool_count": 3},
        )
        assert r.passed is True

    def test_fails_naming_missing_keys_and_observed_keys(self) -> None:
        r = evaluate_expect(
            expect(output_has=["categories", "hint"]),
            {"categories": {}, "tool_count": 3},
        )
        assert r.passed is False
        assert "expect.output_has" in r.failures[0]
        assert "'hint'" in r.failures[0]

    def test_fails_when_output_not_a_dict(self) -> None:
        r = evaluate_expect(expect(output_has=["a"]), {"output": "not a dict"})  # type: ignore[arg-type]
        assert r.passed is False
        assert "expect.output_has" in r.failures[0]


# --- T-02: quality_spot_check score/state assertions --------------------------


class TestQualitySpotCheck:
    def test_min_score_passes_at_threshold(self) -> None:
        r = evaluate_expect(expect(min_score=0.7), {"quality_score": 0.7})
        assert r.passed is True

    def test_min_score_fails_below_threshold(self) -> None:
        r = evaluate_expect(expect(min_score=0.7), {"quality_score": 0.4})
        assert r.passed is False
        assert "expect.min_score" in r.failures[0]
        assert "0.4" in r.failures[0]

    def test_min_score_reads_nested_data_score(self) -> None:
        r = evaluate_expect(expect(min_score=0.5), {"data": {"quality_score": 0.9}})
        assert r.passed is True

    def test_min_score_fails_when_score_missing(self) -> None:
        r = evaluate_expect(expect(min_score=0.5), {"success": True})
        assert r.passed is False
        assert "expect.min_score" in r.failures[0]

    def test_score_state_passes_when_state_allowed(self) -> None:
        r = evaluate_expect(
            expect(score_state=["pass", "revise"]),
            {"quality_state": "pass"},
        )
        assert r.passed is True

    def test_score_state_fails_when_state_not_allowed(self) -> None:
        r = evaluate_expect(
            expect(score_state=["pass"]),
            {"quality_state": "reject"},
        )
        assert r.passed is False
        assert "expect.score_state" in r.failures[0]

    def test_score_state_fails_when_state_missing(self) -> None:
        r = evaluate_expect(expect(score_state=["pass"]), {"quality_score": 0.9})
        assert r.passed is False
        assert "expect.score_state" in r.failures[0]


# --- T-04: error envelopes fail steps unless opted out ------------------------


class TestErrorExpectedOptOut:
    def test_unasserted_error_envelope_fails(self) -> None:
        r = evaluate_expect(Expect(), {"success": False})
        assert r.passed is False
        assert "expect.error_expected" in r.failures[0]

    def test_error_envelope_with_assertion_still_fails_without_opt_out(self) -> None:
        r = evaluate_expect(expect(data_has=["x"]), {"success": False, "data": {"x": 1}})
        assert r.passed is False
        assert any("expect.error_expected" in f for f in r.failures)

    def test_error_envelope_passes_with_opt_out(self) -> None:
        r = evaluate_expect(expect(success=False, error_expected=True), {"success": False})
        assert r.passed is True

    def test_cli_nonzero_exit_fails_without_opt_out(self) -> None:
        r = evaluate_expect(expect(exit_code=1), {"exit_code": 1})
        assert r.passed is False
        assert any("expect.error_expected" in f for f in r.failures)

    def test_cli_nonzero_exit_passes_with_opt_out(self) -> None:
        r = evaluate_expect(expect(exit_code=1, error_expected=True), {"exit_code": 1})
        assert r.passed is True

    def test_success_output_not_flagged(self) -> None:
        r = evaluate_expect(expect(success=True), {"success": True, "exit_code": 0})
        assert r.passed is True
        assert r.failures == []
