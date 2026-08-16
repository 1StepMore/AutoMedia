"""Unit tests for the closed-field validation scenario schema (W1-T1).

Covers: valid dicts parse, unknown fields are rejected at every level, missing
required fields are rejected, ``timeout_seconds`` is accepted, wrong types are
rejected, and the cross-field rules hold (artifact_size_min needs
artifact_exists; regression needs regression_issue; pass_ratio bounds;
per-kind call specs).
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

import automedia.validation as validation
from automedia.validation.schema import (
    DEFAULT_TIMEOUT_SECONDS,
    ArtifactCheck,
    Expect,
    Scenario,
    SchemaError,
    Step,
)


def tool_step(**overrides: object) -> dict[str, Any]:
    """A valid tool-kind step dict (health_check), overridable per test."""
    step: dict[str, Any] = {
        "name": "call health_check",
        "kind": "tool",
        "check": "server responds",
        "standard": "founder-expectations.F01",
        "tool": "health_check",
        "arguments": {},
        "expect": {"success": True},
    }
    step.update(overrides)
    return step


def scenario(**overrides: object) -> dict[str, Any]:
    """A valid minimal scenario dict, overridable per test."""
    base: dict[str, Any] = {
        "name": "health-smoke",
        "description": "The MCP server reports health",
        "intent": "Prove the server health contract",
        "steps": [tool_step()],
    }
    base.update(overrides)
    return base


class TestAcceptsValid:
    def test_minimal_scenario_defaults(self) -> None:
        s = Scenario.from_dict(scenario())
        assert s.name == "health-smoke"
        assert s.category == "general"
        assert s.requires_env == []
        assert s.requires_http is False
        assert s.min_passing is None
        assert s.pass_ratio is None
        assert s.regression is False
        assert s.regression_issue is None
        assert s.error_boundary is False
        assert s.cleanup_steps == []
        assert len(s.steps) == 1
        assert s.steps[0].error_boundary is False
        assert s.steps[0].timeout_seconds is None

    def test_full_featured_scenario(self) -> None:
        data = scenario(
            category="system",
            requires_env=["AUTOMEDIA_LLM_API_KEY"],
            requires_http=True,
            min_passing=2,
            pass_ratio=0.75,
            regression=True,
            regression_issue="https://example.com/issues/42",
            error_boundary=True,
            cleanup_steps=[
                tool_step(name="cleanup", tool="disconnect_account", arguments={"account_id": "a1"})
            ],
        )
        s = Scenario.from_dict(data)
        assert s.min_passing == 2
        assert s.pass_ratio == 0.75
        assert s.regression is True
        assert s.regression_issue == "https://example.com/issues/42"
        assert s.error_boundary is True
        assert s.cleanup_steps[0].name == "cleanup"

    def test_step_all_fields(self) -> None:
        data = scenario(
            steps=[
                {
                    "name": "run doctor",
                    "kind": "cli",
                    "check": "doctor lists every dep with status",
                    "standard": "evaluation-matrix.dim1",
                    "command": "automedia doctor --output json",
                    "timeout_seconds": 30,
                    "error_boundary": True,
                    "expect": {"exit_code": 0, "stdout_has": ["ffmpeg"], "stderr_has": ["warning"]},
                    "recovery_steps": [tool_step(name="recover")],
                    "collect_artifacts": [{"path": "artifacts/doctor.json", "required": True}],
                },
                {
                    "name": "inspect log",
                    "kind": "file",
                    "check": "log is non-trivial",
                    "standard": "founder-expectations.F02",
                    "command": "output/log.txt",
                    "expect": {
                        "artifact_exists": "output/log.txt",
                        "artifact_size_min": 10,
                        "artifact_nonempty": "output/log.txt",
                    },
                },
            ]
        )
        s = Scenario.from_dict(data)
        cli, file_step = s.steps
        assert isinstance(cli, Step)
        assert cli.timeout_seconds == 30.0
        assert cli.error_boundary is True
        assert cli.recovery_steps[0].name == "recover"
        assert cli.collect_artifacts == [ArtifactCheck(path="artifacts/doctor.json", required=True)]
        assert file_step.expect.artifact_exists == "output/log.txt"
        assert file_step.expect.artifact_size_min == 10
        assert file_step.expect.artifact_nonempty == "output/log.txt"

    def test_public_api_exports(self) -> None:
        assert validation.Scenario is Scenario
        assert validation.Step is Step
        assert validation.Expect is Expect
        assert validation.ArtifactCheck is ArtifactCheck
        assert validation.SchemaError is SchemaError
        assert validation.DEFAULT_TIMEOUT_SECONDS == DEFAULT_TIMEOUT_SECONDS == 180.0
        assert validation.STEP_KINDS == ("tool", "cli", "file")
        assert validation.EXPECT_KEYS == (
            "success",
            "data_has",
            "exit_code",
            "stdout_has",
            "stderr_has",
            "artifact_exists",
            "artifact_size_min",
            "artifact_nonempty",
            "gate_records_pass",
        )
        assert "intent" in validation.SCENARIO_FIELDS
        assert "check" in validation.STEP_FIELDS
        assert "standard" in validation.STEP_FIELDS


class TestRejectsUnknownFields:
    @pytest.mark.parametrize("field", ["brand", "llm", "expects", "base_url", "url", "surface"])
    def test_unknown_top_level(self, field: str) -> None:
        with pytest.raises(SchemaError, match=field):
            Scenario.from_dict(scenario(**{field: "x"}))

    def test_arguments_rejects_non_str_key(self) -> None:
        with pytest.raises(SchemaError, match="key"):
            Scenario.from_dict(scenario(steps=[tool_step(arguments={1: "x"})]))

    def test_unknown_expect_key(self) -> None:
        with pytest.raises(SchemaError, match="status_code"):
            Scenario.from_dict(
                scenario(steps=[tool_step(expect={"success": True, "status_code": 200})])
            )

    def test_unknown_step_field(self) -> None:
        with pytest.raises(SchemaError, match="method"):
            Scenario.from_dict(scenario(steps=[tool_step(method="GET")]))

    def test_unknown_artifact_field(self) -> None:
        with pytest.raises(SchemaError, match="optional"):
            Scenario.from_dict(
                scenario(steps=[tool_step(collect_artifacts=[{"path": "a.txt", "optional": True}])])
            )


class TestMissingRequired:
    @pytest.mark.parametrize("field", ["name", "description", "intent", "steps"])
    def test_scenario_missing(self, field: str) -> None:
        data = scenario()
        del data[field]
        with pytest.raises(SchemaError, match=field):
            Scenario.from_dict(data)

    @pytest.mark.parametrize("field", ["name", "kind", "check", "standard", "expect"])
    def test_step_missing(self, field: str) -> None:
        step = tool_step()
        del step[field]
        with pytest.raises(SchemaError, match=field):
            Scenario.from_dict(scenario(steps=[step]))

    def test_empty_steps_rejected(self) -> None:
        with pytest.raises(SchemaError, match="empty"):
            Scenario.from_dict(scenario(steps=[]))

    def test_artifact_missing_path(self) -> None:
        with pytest.raises(SchemaError, match="path"):
            Scenario.from_dict(scenario(steps=[tool_step(collect_artifacts=[{"required": False}])]))


class TestTimeoutSeconds:
    @pytest.mark.parametrize("value", [1, 30, 30.5, 0.25])
    def test_accepts_positive_numbers(self, value: int | float) -> None:
        s = Scenario.from_dict(scenario(steps=[tool_step(timeout_seconds=value)]))
        assert s.steps[0].timeout_seconds == float(value)

    @pytest.mark.parametrize("value", [0, -5])
    def test_rejects_zero_and_negative(self, value: int) -> None:
        with pytest.raises(SchemaError, match="timeout_seconds"):
            Scenario.from_dict(scenario(steps=[tool_step(timeout_seconds=value)]))

    def test_rejects_non_number(self) -> None:
        with pytest.raises(SchemaError, match="timeout_seconds"):
            Scenario.from_dict(scenario(steps=[tool_step(timeout_seconds="fast")]))


class TestTypeErrors:
    @pytest.mark.parametrize(
        ("mutator", "match"),
        [
            ({"name": 42}, "scenario.name"),
            ({"description": ["x"]}, "scenario.description"),
            ({"intent": 1}, "scenario.intent"),
            ({"category": None}, "scenario.category"),
            ({"requires_env": "API_KEY"}, "scenario.requires_env"),
            ({"requires_env": [1]}, "scenario.requires_env"),
            ({"requires_http": "yes"}, "scenario.requires_http"),
            ({"min_passing": True}, "scenario.min_passing"),
            ({"min_passing": 1.5}, "scenario.min_passing"),
            ({"pass_ratio": "0.5"}, "scenario.pass_ratio"),
            ({"pass_ratio": True}, "scenario.pass_ratio"),
            ({"regression": 1}, "scenario.regression"),
            ({"regression_issue": 7}, "scenario.regression_issue"),
            ({"error_boundary": "x"}, "scenario.error_boundary"),
            ({"steps": {"name": "x"}}, "scenario.steps"),
        ],
    )
    def test_scenario_type(self, mutator: dict[str, Any], match: str) -> None:
        with pytest.raises(SchemaError, match=match):
            Scenario.from_dict(scenario(**mutator))

    @pytest.mark.parametrize(
        ("mutator", "match"),
        [
            ({"name": 1}, r"steps\[0\]\.name"),
            ({"kind": 3}, r"steps\[0\]\.kind"),
            ({"check": ["x"]}, r"steps\[0\]\.check"),
            ({"standard": 1}, r"steps\[0\]\.standard"),
            ({"expect": "pass"}, r"steps\[0\]\.expect"),
            ({"expect": {"success": "yes"}}, "expect.success"),
            ({"expect": {"exit_code": True}}, "expect.exit_code"),
            ({"expect": {"data_has": "key"}}, "expect.data_has"),
            ({"expect": {"data_has": [1]}}, "expect.data_has"),
            ({"expect": {"artifact_exists": 5}}, "expect.artifact_exists"),
            ({"expect": {"gate_records_pass": "y"}}, "expect.gate_records_pass"),
            ({"tool": 1}, r"steps\[0\]\.tool"),
            ({"arguments": "{}"}, r"steps\[0\]\.arguments"),
            ({"command": 1}, r"steps\[0\]\.command"),
            ({"error_boundary": "x"}, r"steps\[0\]\.error_boundary"),
            ({"recovery_steps": "none"}, r"steps\[0\]\.recovery_steps"),
            ({"collect_artifacts": "none"}, r"steps\[0\]\.collect_artifacts"),
            ({"collect_artifacts": [{"path": 1}]}, r"collect_artifacts\[0\]\.path"),
            (
                {"collect_artifacts": [{"path": "a", "required": "y"}]},
                r"collect_artifacts\[0\]\.required",
            ),
        ],
    )
    def test_step_type(self, mutator: dict[str, Any], match: str) -> None:
        with pytest.raises(SchemaError, match=match):
            Scenario.from_dict(scenario(steps=[tool_step(**mutator)]))


class TestCrossFieldRules:
    def test_artifact_size_min_requires_artifact_exists(self) -> None:
        with pytest.raises(SchemaError, match="artifact_exists"):
            Scenario.from_dict(scenario(steps=[tool_step(expect={"artifact_size_min": 10})]))

    def test_accepts_artifact_size_min_with_artifact_exists(self) -> None:
        s = Scenario.from_dict(
            scenario(steps=[tool_step(expect={"artifact_exists": "a.bin", "artifact_size_min": 0})])
        )
        assert s.steps[0].expect == Expect(artifact_exists="a.bin", artifact_size_min=0)

    def test_rejects_negative_artifact_size_min(self) -> None:
        with pytest.raises(SchemaError, match=">= 0"):
            Scenario.from_dict(
                scenario(
                    steps=[tool_step(expect={"artifact_exists": "a.bin", "artifact_size_min": -1})]
                )
            )

    def test_regression_requires_issue(self) -> None:
        with pytest.raises(SchemaError, match="regression_issue"):
            Scenario.from_dict(scenario(regression=True))

    def test_regression_issue_allowed_without_regression_flag(self) -> None:
        s = Scenario.from_dict(scenario(regression_issue="ISSUE-1"))
        assert s.regression is False
        assert s.regression_issue == "ISSUE-1"


class TestKindRules:
    def test_tool_kind_requires_tool(self) -> None:
        step = tool_step()
        del step["tool"]
        with pytest.raises(SchemaError, match="requires 'tool'"):
            Scenario.from_dict(scenario(steps=[step]))

    def test_tool_kind_requires_arguments(self) -> None:
        step = tool_step()
        del step["arguments"]
        with pytest.raises(SchemaError, match="requires 'arguments'"):
            Scenario.from_dict(scenario(steps=[step]))

    def test_tool_kind_rejects_command(self) -> None:
        with pytest.raises(SchemaError, match="must not carry 'command'"):
            Scenario.from_dict(scenario(steps=[tool_step(command="echo hi")]))

    def test_cli_kind_requires_command(self) -> None:
        step = tool_step(kind="cli")
        del step["tool"]
        del step["arguments"]
        with pytest.raises(SchemaError, match="requires 'command'"):
            Scenario.from_dict(scenario(steps=[step]))

    def test_cli_kind_rejects_tool(self) -> None:
        with pytest.raises(SchemaError, match="must not carry 'tool'"):
            Scenario.from_dict(scenario(steps=[tool_step(kind="cli", command="echo hi")]))

    def test_file_kind_requires_command(self) -> None:
        step = tool_step(kind="file")
        del step["tool"]
        del step["arguments"]
        with pytest.raises(SchemaError, match="requires 'command'"):
            Scenario.from_dict(scenario(steps=[step]))

    def test_file_kind_accepts_command_as_path(self) -> None:
        step = tool_step(
            kind="file", command="output/draft.md", expect={"artifact_exists": "output/draft.md"}
        )
        del step["tool"]
        del step["arguments"]
        s = Scenario.from_dict(scenario(steps=[step]))
        assert s.steps[0].kind == "file"
        assert s.steps[0].command == "output/draft.md"

    def test_unknown_kind_rejected(self) -> None:
        with pytest.raises(SchemaError, match="http"):
            Scenario.from_dict(scenario(steps=[tool_step(kind="http", command="GET /x")]))


class TestPartialPass:
    @pytest.mark.parametrize("value", [0, -1])
    def test_min_passing_bounds(self, value: int) -> None:
        with pytest.raises(SchemaError, match="min_passing"):
            Scenario.from_dict(scenario(min_passing=value))

    @pytest.mark.parametrize("value", [0, 1.5, -0.1])
    def test_pass_ratio_bounds(self, value: float) -> None:
        with pytest.raises(SchemaError, match="pass_ratio"):
            Scenario.from_dict(scenario(pass_ratio=value))

    @pytest.mark.parametrize("value", [0.01, 1.0, 0.5, 1])
    def test_pass_ratio_accepts(self, value: int | float) -> None:
        assert Scenario.from_dict(scenario(pass_ratio=value)).pass_ratio == float(value)


class TestErrorBoundary:
    def test_both_levels_accepted(self) -> None:
        s = Scenario.from_dict(
            scenario(error_boundary=True, steps=[tool_step(error_boundary=True)])
        )
        assert s.error_boundary is True
        assert s.steps[0].error_boundary is True


class TestProvesMetadata:
    """``proves_gates``/``proves_modes`` (issue #78): declarative coverage
    metadata consumed by the coverage audit, never by the engine.

    Both fields are optional (default []), parsed as lists of non-empty
    unique strings; wrong element types, empty names, duplicates and
    non-list values raise :class:`SchemaError` naming the field (the
    closed-schema contract)."""

    def test_parses_from_yaml_scenario(self) -> None:
        """A fixture YAML doc carrying both fields parses into the model."""
        doc = yaml.safe_load(
            """\
name: mode-run-fixture
description: A synthetic pipeline-mode fixture scenario.
intent: Prove the coverage audit reads proves_gates and proves_modes.
proves_gates: [G0, V1, L2]
proves_modes: [text_only, auto]
steps:
  - name: call the tool
    kind: tool
    check: The tool answers.
    standard: tool.contract
    tool: health_check
    arguments: {}
    expect:
      success: true
"""
        )
        s = Scenario.from_dict(doc)
        assert s.proves_gates == ["G0", "V1", "L2"]
        assert s.proves_modes == ["text_only", "auto"]

    def test_defaults_to_empty(self) -> None:
        s = Scenario.from_dict(scenario())
        assert s.proves_gates == []
        assert s.proves_modes == []

    def test_duplicates_rejected(self) -> None:
        with pytest.raises(SchemaError, match="duplicate"):
            Scenario.from_dict(scenario(proves_gates=["G0", "G0"]))
        with pytest.raises(SchemaError, match="duplicate"):
            Scenario.from_dict(scenario(proves_modes=["auto", "auto"]))

    def test_wrong_element_type_rejected(self) -> None:
        with pytest.raises(SchemaError, match=r"proves_gates\[0\]"):
            Scenario.from_dict(scenario(proves_gates=[1]))

    def test_empty_string_element_rejected(self) -> None:
        with pytest.raises(SchemaError, match=r"proves_gates\[0\]"):
            Scenario.from_dict(scenario(proves_gates=[""]))

    def test_non_list_rejected(self) -> None:
        with pytest.raises(SchemaError, match="proves_modes"):
            Scenario.from_dict(scenario(proves_modes="text_only"))


class TestNonDictInput:
    @pytest.mark.parametrize("bad", ["x", [1], None, 3])
    def test_scenario_from_dict_rejects_non_dict(self, bad: object) -> None:
        with pytest.raises(SchemaError, match="scenario"):
            Scenario.from_dict(bad)

    def test_step_in_steps_must_be_dict(self) -> None:
        with pytest.raises(SchemaError, match="step"):
            Scenario.from_dict(scenario(steps=["not a dict"]))

    def test_artifact_in_collect_artifacts_must_be_dict(self) -> None:
        with pytest.raises(SchemaError, match=r"collect_artifacts\[0\]"):
            Scenario.from_dict(scenario(steps=[tool_step(collect_artifacts=["not a dict"])]))


class TestNesting:
    def test_recovery_step_may_itself_have_recovery(self) -> None:
        data = scenario(
            steps=[
                tool_step(
                    recovery_steps=[
                        tool_step(
                            name="nested recovery",
                            tool="disconnect_account",
                            arguments={"account_id": "a1"},
                        )
                    ]
                )
            ]
        )
        s = Scenario.from_dict(data)
        assert s.steps[0].recovery_steps[0].name == "nested recovery"

    def test_unknown_key_in_recovery_step_names_index(self) -> None:
        with pytest.raises(SchemaError, match=r"recovery_steps\[0\]"):
            Scenario.from_dict(scenario(steps=[tool_step(recovery_steps=[tool_step(extra="x")])]))


class TestSchemaErrorClass:
    def test_is_valueerror_subclass(self) -> None:
        assert issubclass(SchemaError, ValueError)

    def test_message_names_offending_field(self) -> None:
        with pytest.raises(SchemaError, match="scenario.intent"):
            Scenario.from_dict(scenario(intent=1))
