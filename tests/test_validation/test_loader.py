"""Unit tests for the scenario loader (W1-T2).

Covers: recursive discovery with deterministic ordering; env override
(``AUTOMEDIA_VALIDATION_SCENARIOS_DIR``) replacing the default scenarios dir;
strict YAML (malformed -> file:line, empty/null/multi-document files rejected);
strict schema (unknown field, missing intent/check/standard); per-step
``standard`` cross-check against an injected fixture registry (including
recovery/cleanup steps); loud failure when the standards handbook is absent;
duplicate scenario names across files rejected with both paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from automedia.validation.loader import LoadError, load_scenarios
from automedia.validation.schema import SchemaError

KNOWN_STANDARDS = frozenset(
    {"founder-expectations.F01", "founder-expectations.F02", "evaluation-matrix.dim1"}
)


class FakeStandards:
    """Structural stand-in for ``automedia.validation.standards.StandardsRegistry``
    (the W1-T3 class may not exist yet; the loader depends on the shape only —
    ``validate_standard(key)`` + ``known_keys()``, matching the landed W1-T3)."""

    def validate_standard(self, key: str) -> bool:
        return key in KNOWN_STANDARDS

    def known_keys(self) -> set[str]:
        return set(KNOWN_STANDARDS)

    def check_type(self, key: str) -> tuple[str, ...] | None:
        if key not in KNOWN_STANDARDS:
            return None
        return ("artifact_exists",)

    def unimplemented_check_types(self) -> set[str]:
        return set()


def tool_step(**overrides: object) -> dict[str, object]:
    """A valid tool-kind step dict (health_check), overridable per test."""
    step: dict[str, object] = {
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


def scenario_dict(**overrides: object) -> dict[str, object]:
    """A valid minimal scenario dict, overridable per test."""
    base: dict[str, object] = {
        "name": "health-smoke",
        "description": "The MCP server reports health",
        "intent": "Prove the server health contract",
        "steps": [tool_step()],
    }
    base.update(overrides)
    return base


def write_yaml(root: Path, rel: str, data: object) -> Path:
    """Write ``data`` as YAML under ``root/rel`` and return the path."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class TestLoadsValid:
    def test_recursive_discovery_in_deterministic_order(self, tmp_path: Path) -> None:
        write_yaml(tmp_path, "a.yaml", scenario_dict(name="alpha"))
        write_yaml(tmp_path, "regression/r.yaml", scenario_dict(name="regression-r"))
        write_yaml(tmp_path, "zz.yaml", scenario_dict(name="zzz"))

        scenarios = load_scenarios(tmp_path, FakeStandards())

        assert [s.name for s in scenarios] == ["alpha", "regression-r", "zzz"]

    def test_loaded_scenario_carries_intent_check_standard(self, tmp_path: Path) -> None:
        write_yaml(tmp_path, "a.yaml", scenario_dict())

        (scenario,) = load_scenarios(tmp_path, FakeStandards())

        assert scenario.intent == "Prove the server health contract"
        assert scenario.steps[0].check == "server responds"
        assert scenario.steps[0].standard == "founder-expectations.F01"

    def test_accepts_str_path(self, tmp_path: Path) -> None:
        write_yaml(tmp_path, "s.yaml", scenario_dict(name="str-path"))

        scenarios = load_scenarios(str(tmp_path), FakeStandards())

        assert [s.name for s in scenarios] == ["str-path"]

    def test_explicit_dir_ignores_env_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_dir = tmp_path / "real"
        other_dir = tmp_path / "other"
        write_yaml(real_dir, "s.yaml", scenario_dict(name="real"))
        write_yaml(other_dir, "o.yaml", scenario_dict(name="other"))
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(other_dir))

        scenarios = load_scenarios(real_dir, FakeStandards())

        assert [s.name for s in scenarios] == ["real"]

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert load_scenarios(tmp_path, FakeStandards()) == []

    def test_missing_dir_returns_empty_list(self, tmp_path: Path) -> None:
        # Guide §7.1 phase 0: the engine lists zero scenarios cleanly.
        assert load_scenarios(tmp_path / "nope", FakeStandards()) == []


class TestMalformedYaml:
    def test_malformed_fails_with_file_and_line(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.yaml"
        # Tab indentation is a scanner error on line 5 (1-based).
        path.write_text(
            "name: smoke\ndescription: d\nintent: i\nsteps:\n\t- name: s\n",
            encoding="utf-8",
        )

        with pytest.raises(LoadError, match=rf"{re.escape(str(path))}:5:"):
            load_scenarios(tmp_path, FakeStandards())

    def test_empty_file_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")

        with pytest.raises(LoadError, match=str(path)):
            load_scenarios(tmp_path, FakeStandards())

    def test_null_document_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "null.yaml"
        path.write_text("---\n", encoding="utf-8")

        with pytest.raises(LoadError, match="empty"):
            load_scenarios(tmp_path, FakeStandards())

    def test_multiple_documents_fail(self, tmp_path: Path) -> None:
        path = tmp_path / "multi.yaml"
        path.write_text(
            yaml.safe_dump(scenario_dict())
            + "---\n"
            + yaml.safe_dump(scenario_dict(name="second")),
            encoding="utf-8",
        )

        with pytest.raises(LoadError, match="exactly one"):
            load_scenarios(tmp_path, FakeStandards())


class TestSchemaRejection:
    @pytest.mark.parametrize("field", ["brand", "llm"])
    def test_unknown_top_level_field_names_file_and_field(self, tmp_path: Path, field: str) -> None:
        path = write_yaml(tmp_path, "s.yaml", scenario_dict(**{field: "x"}))

        with pytest.raises(LoadError, match=field) as excinfo:
            load_scenarios(tmp_path, FakeStandards())

        assert str(path) in str(excinfo.value)

    def test_missing_intent_fails(self, tmp_path: Path) -> None:
        data = scenario_dict()
        del data["intent"]
        write_yaml(tmp_path, "s.yaml", data)

        with pytest.raises(LoadError, match="intent"):
            load_scenarios(tmp_path, FakeStandards())

    @pytest.mark.parametrize("field", ["check", "standard"])
    def test_missing_step_field_fails(self, tmp_path: Path, field: str) -> None:
        step = tool_step()
        del step[field]
        write_yaml(tmp_path, "s.yaml", scenario_dict(steps=[step]))

        with pytest.raises(LoadError, match=field):
            load_scenarios(tmp_path, FakeStandards())

    def test_wrong_type_names_dotted_field(self, tmp_path: Path) -> None:
        write_yaml(tmp_path, "s.yaml", scenario_dict(intent=42))

        with pytest.raises(LoadError, match=re.escape("scenario.intent")):
            load_scenarios(tmp_path, FakeStandards())


class TestStandardsCrossCheck:
    def test_known_standard_key_loads(self, tmp_path: Path) -> None:
        write_yaml(tmp_path, "s.yaml", scenario_dict())

        scenarios = load_scenarios(tmp_path, FakeStandards())

        assert len(scenarios) == 1

    def test_unknown_standard_key_names_scenario_and_step(self, tmp_path: Path) -> None:
        write_yaml(
            tmp_path,
            "s.yaml",
            scenario_dict(steps=[tool_step(standard="founder-expectations.Z99")]),
        )

        with pytest.raises(LoadError, match="Z99") as excinfo:
            load_scenarios(tmp_path, FakeStandards())

        msg = str(excinfo.value)
        assert "health-smoke" in msg
        assert "call health_check" in msg

    def test_unknown_standard_in_recovery_step_fails(self, tmp_path: Path) -> None:
        write_yaml(
            tmp_path,
            "s.yaml",
            scenario_dict(
                steps=[tool_step(recovery_steps=[tool_step(name="recover", standard="nope.x")])]
            ),
        )

        with pytest.raises(LoadError, match=re.escape("nope.x")):
            load_scenarios(tmp_path, FakeStandards())

    def test_unknown_standard_in_cleanup_step_fails(self, tmp_path: Path) -> None:
        write_yaml(
            tmp_path,
            "s.yaml",
            scenario_dict(cleanup_steps=[tool_step(name="cleanup", standard="nope.y")]),
        )

        with pytest.raises(LoadError, match=re.escape("nope.y")):
            load_scenarios(tmp_path, FakeStandards())

    def test_registry_absent_fails_loudly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Valid scenario, but no STANDARDS.md anywhere: loud LoadError, never a
        # silent pass (Momus improvement 3).
        write_yaml(tmp_path, "s.yaml", scenario_dict())
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(tmp_path))

        with pytest.raises(LoadError) as excinfo:
            load_scenarios()

        msg = str(excinfo.value)
        assert "STANDARDS.md" in msg
        assert str(tmp_path) in msg


class TestEnvOverride:
    def test_env_override_replaces_default_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_yaml(tmp_path, "s.yaml", scenario_dict(name="env-override"))
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(tmp_path))

        scenarios = load_scenarios(standards=FakeStandards())

        assert [s.name for s in scenarios] == ["env-override"]


class TestDuplicateNames:
    def test_duplicate_across_files_lists_both_files(self, tmp_path: Path) -> None:
        write_yaml(tmp_path, "a.yaml", scenario_dict())
        write_yaml(tmp_path, "b.yaml", scenario_dict())

        with pytest.raises(LoadError) as excinfo:
            load_scenarios(tmp_path, FakeStandards())

        msg = str(excinfo.value)
        assert str(tmp_path / "a.yaml") in msg
        assert str(tmp_path / "b.yaml") in msg


class TestLoadErrorClass:
    def test_is_schema_error_subclass(self) -> None:
        assert issubclass(LoadError, SchemaError)

    def test_messages_name_file(self, tmp_path: Path) -> None:
        path = write_yaml(tmp_path, "s.yaml", scenario_dict(intent=42))

        with pytest.raises(LoadError) as excinfo:
            load_scenarios(tmp_path, FakeStandards())

        assert str(path) in str(excinfo.value)


# --- T-02: check-type binding + non-empty expects ---------------------------


BOGUS_CHECK_TYPE_HANDBOOK = """
## Standards

| Key | Check type | Standard | Source doc | Clause |
| --- | --- | --- | --- | --- |
| x.y | bogus_check | an unimplemented check | docs/x.md | §1 |
"""


class TestCheckTypeBinding:
    def test_unimplemented_check_type_fails_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A handbook standard whose check type has no evaluator is rejected
        at load, naming the check type (T-02)."""
        root = tmp_path / "scenarios"
        root.mkdir()
        (root / "STANDARDS.md").write_text(BOGUS_CHECK_TYPE_HANDBOOK, encoding="utf-8")
        write_yaml(root, "s.yaml", scenario_dict(steps=[tool_step(standard="x.y")]))
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))

        with pytest.raises(LoadError, match="bogus_check"):
            load_scenarios()


class TestNonEmptyExpect:
    def test_non_boundary_empty_expect_rejected(self, tmp_path: Path) -> None:
        write_yaml(tmp_path, "s.yaml", scenario_dict(steps=[tool_step(expect={})]))

        with pytest.raises(SchemaError, match="expect"):
            load_scenarios(tmp_path, FakeStandards())

    def test_boundary_step_empty_expect_allowed(self, tmp_path: Path) -> None:
        write_yaml(
            tmp_path,
            "s.yaml",
            scenario_dict(steps=[tool_step(expect={}, error_boundary=True)]),
        )

        scenarios = load_scenarios(tmp_path, FakeStandards())

        assert len(scenarios) == 1

    def test_scenario_level_boundary_empty_expect_allowed(self, tmp_path: Path) -> None:
        write_yaml(
            tmp_path,
            "s.yaml",
            scenario_dict(error_boundary=True, steps=[tool_step(expect={})]),
        )

        scenarios = load_scenarios(tmp_path, FakeStandards())

        assert len(scenarios) == 1

    def test_cleanup_empty_expect_is_rejected(self, tmp_path: Path) -> None:
        """Cleanup steps that can be graded are held to the same rule (T-02)."""
        write_yaml(
            tmp_path,
            "s.yaml",
            scenario_dict(cleanup_steps=[tool_step(name="cleanup", expect={})]),
        )

        with pytest.raises(SchemaError, match="expect"):
            load_scenarios(tmp_path, FakeStandards())

    def test_recovery_empty_expect_is_rejected(self, tmp_path: Path) -> None:
        """Recovery steps that can be graded are held to the same rule (T-02)."""
        write_yaml(
            tmp_path,
            "s.yaml",
            scenario_dict(steps=[tool_step(recovery_steps=[tool_step(name="recover", expect={})])]),
        )

        with pytest.raises(SchemaError, match="expect"):
            load_scenarios(tmp_path, FakeStandards())
