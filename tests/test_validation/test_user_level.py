"""User-level dimension (gap T-10): required ``user_level`` + data-driven
``automedia validate coverage --by-level``.

Covers the plan's acceptance:
* the schema validates ``user_level`` against the closed L0-L5 enum and
  rejects an invalid or absent level (load-time rejection is the contract);
* the committed library backfills every scenario with one of L0-L5 and the
  derived distribution is stable;
* ``coverage_audit`` carries a data-driven ``by_level`` matrix whose cells
  sum to the library size;
* the CLI ``automedia validate coverage --by-level`` renders the matrix.

The real-library assertions read ``scenarios/`` (the same committed library
the loader consumes) and are skipped when the env override points at a
non-existent directory, mirroring ``test_library_smoke``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.validation.coverage import coverage_audit
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import USER_LEVELS, Scenario, SchemaError

runner = CliRunner()


def _minimal_step() -> dict[str, object]:
    return {
        "name": "call the tool",
        "kind": "tool",
        "check": "The tool answers.",
        "standard": "tool.contract",
        "tool": "health_check",
        "arguments": {},
        "expect": {"success": True},
    }


def _scenario_doc(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "user-level-fixture",
        "description": "A synthetic scenario fixture.",
        "intent": "Prove the user_level schema field.",
        "user_level": "L0",
        "steps": [_minimal_step()],
    }
    base.update(overrides)
    return base


class TestSchemaUserLevel:
    def test_enum_constant(self) -> None:
        assert USER_LEVELS == ("L0", "L1", "L2", "L3", "L4", "L5")

    @pytest.mark.parametrize("level", ["L0", "L1", "L2", "L3", "L4", "L5"])
    def test_every_level_accepted(self, level: str) -> None:
        scenario = Scenario.from_dict(_scenario_doc(user_level=level))
        assert scenario.user_level == level

    def test_missing_user_level_rejected(self) -> None:
        doc = _scenario_doc()
        del doc["user_level"]
        with pytest.raises(SchemaError, match="user_level"):
            Scenario.from_dict(doc)

    @pytest.mark.parametrize("bad", ["L6", "l0", "L", "", "level0", 0])
    def test_invalid_user_level_rejected(self, bad: object) -> None:
        with pytest.raises(SchemaError, match="user_level"):
            Scenario.from_dict(_scenario_doc(user_level=bad))

    def test_user_level_is_a_closed_field(self) -> None:
        from automedia.validation import schema

        assert "user_level" in schema.SCENARIO_FIELDS


def _library_or_skip() -> list[Scenario]:
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override and not Path(override).expanduser().is_dir():
        pytest.skip("AUTOMEDIA_VALIDATION_SCENARIOS_DIR points at a missing dir")
    return load_scenarios(default_scenarios_dir())


class TestLibraryBackfill:
    def test_every_scenario_carries_a_valid_level(self) -> None:
        library = _library_or_skip()
        invalid = [
            (scenario.name, scenario.user_level)
            for scenario in library
            if scenario.user_level not in USER_LEVELS
        ]
        assert not invalid, f"invalid user_level values: {invalid}"

    def test_distribution_is_data_derived_and_total(self) -> None:
        library = _library_or_skip()
        distribution = {
            level: sum(1 for scenario in library if scenario.user_level == level)
            for level in USER_LEVELS
        }
        assert sum(distribution.values()) == len(library)
        # The derived backfill puts every committed scenario at L0/L1/L2
        # today (L3-L5 arrive with Wave-2 stage-gap scenarios).
        assert distribution["L0"] > 0
        assert distribution["L1"] > 0
        assert distribution["L2"] > 0
        print(f"user_level distribution: {distribution}")


class TestByLevelAudit:
    def test_by_level_is_a_data_driven_matrix(self) -> None:
        library = _library_or_skip()
        audit = coverage_audit()
        by_level = audit["by_level"]
        assert by_level["levels"] == list(USER_LEVELS)
        assert sum(by_level["distribution"].values()) == len(library)
        assert by_level["total"] == len(library)
        cell_total = sum(count for row in by_level["matrix"].values() for count in row.values())
        assert cell_total == len(library)

    def test_cli_by_level_renders_the_matrix(self) -> None:
        result = runner.invoke(app, ["validate", "coverage", "--by-level"])
        assert result.exit_code == 0, result.output
        assert "L0" in result.output
        assert "user level" in result.output.lower()
