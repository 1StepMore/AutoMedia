"""Meta/surface scenario separation (gap T-09) and the SDK scope marker.

A ``meta: true`` scenario tests the validation harness or CLI registration,
not a product surface.  The audit must report ``surface_scenarios`` and
``meta_scenarios`` separately, and the stage×user surface matrix must exclude
meta scenarios.  Synthetic fixtures only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.validation.coverage import coverage_audit
from automedia.validation.loader import load_scenarios
from automedia.validation.schema import Scenario, SchemaError

_TOOL_STEP = """\
  - name: call the tool
    kind: tool
    check: the tool answers
    standard: tool.contract
    tool: health_check
    arguments: {}
    expect:
      success: true
"""

_STANDARDS = """\
## Standards

| Key | Check type | Standard | Source doc | Clause |
| --- | --- | --- | --- | --- |
| tool.contract | data_has | Tool return contract | api-reference | PipelineResult |
| founder-expectations.F02 | non_empty | F02 first command | founder-expectations | F02 |
"""


def _scenario_doc(name: str, *, meta: bool = False) -> str:
    meta_line = "meta: true\n" if meta else ""
    return (
        f"name: {name}\n"
        f"description: synthetic {name}\n"
        f"intent: exercise meta/surface separation\n"
        f"category: baseline\n"
        f"user_level: L0\n"
        f"{meta_line}"
        f"requires_env: []\n"
        f"steps:\n{_TOOL_STEP}"
    )


def _write_lib(tmp_path: Path, docs: dict[str, str]) -> Path:
    lib = tmp_path / "scenarios"
    lib.mkdir()
    (lib / "STANDARDS.md").write_text(_STANDARDS, encoding="utf-8")
    for filename, content in docs.items():
        path = lib / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return lib


class TestMetaField:
    def test_meta_defaults_false(self) -> None:
        scenario = Scenario.from_dict(
            {
                "name": "s",
                "description": "d",
                "intent": "i",
                "user_level": "L0",
                "steps": [
                    {
                        "name": "n",
                        "kind": "tool",
                        "check": "c",
                        "standard": "tool.contract",
                        "tool": "health_check",
                        "arguments": {},
                        "expect": {"success": True},
                    }
                ],
            }
        )
        assert scenario.meta is False

    def test_meta_true_parses(self) -> None:
        scenario = Scenario.from_dict(
            {
                "name": "s",
                "description": "d",
                "intent": "i",
                "user_level": "L0",
                "meta": True,
                "steps": [
                    {
                        "name": "n",
                        "kind": "tool",
                        "check": "c",
                        "standard": "tool.contract",
                        "tool": "health_check",
                        "arguments": {},
                        "expect": {"success": True},
                    }
                ],
            }
        )
        assert scenario.meta is True

    def test_meta_wrong_type_rejected(self) -> None:
        with pytest.raises(SchemaError, match="meta"):
            Scenario.from_dict(
                {
                    "name": "s",
                    "description": "d",
                    "intent": "i",
                    "user_level": "L0",
                    "meta": "yes",
                    "steps": [
                        {
                            "name": "n",
                            "kind": "tool",
                            "check": "c",
                            "standard": "tool.contract",
                            "tool": "health_check",
                            "arguments": {},
                            "expect": {"success": True},
                        }
                    ],
                }
            )


class TestAuditSeparation:
    def test_surface_and_meta_are_disjoint_and_partitioned(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "surface.yaml": _scenario_doc("surface-one"),
                "meta/self.yaml": _scenario_doc("meta-one", meta=True),
            },
        )
        audit = coverage_audit(lib)
        assert audit["surface_scenarios"] == ["surface-one"]
        assert audit["meta_scenarios"] == ["meta-one"]
        assert audit["surface_scenario_count"] == 1
        assert audit["meta_scenario_count"] == 1
        assert (
            audit["surface_scenario_count"] + audit["meta_scenario_count"]
            == audit["scenario_count"]
        )

    def test_surface_by_level_excludes_meta(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "surface.yaml": _scenario_doc("surface-one"),
                "meta/self.yaml": _scenario_doc("meta-one", meta=True),
            },
        )
        audit = coverage_audit(lib)
        assert audit["by_level"]["total"] == audit["scenario_count"]
        assert audit["surface_by_level"]["total"] == audit["surface_scenario_count"]

    def test_untagged_scenario_is_surface(self, tmp_path: Path) -> None:
        lib = _write_lib(tmp_path, {"plain.yaml": _scenario_doc("plain")})
        audit = coverage_audit(lib)
        assert "plain" in audit["surface_scenarios"]
        assert "plain" not in audit["meta_scenarios"]


class TestCommittedLibrary:
    def test_audit_partitions_the_committed_library(self) -> None:
        audit = coverage_audit()
        surface = set(audit["surface_scenarios"])
        meta = set(audit["meta_scenarios"])
        assert not surface & meta
        assert len(surface) + len(meta) == audit["scenario_count"]

    def test_help_only_registration_scripts_are_meta(self) -> None:
        audit = coverage_audit()
        meta = set(audit["meta_scenarios"])
        for name in (
            "adapter-cli-surface",
            "account-cli-surface",
            "pool-cli-surface",
            "onboard-cli-surface",
        ):
            assert name in meta, f"{name} must be tagged meta: true"

    def test_validation_self_tests_are_meta(self) -> None:
        audit = coverage_audit()
        meta = set(audit["meta_scenarios"])
        for name in (
            "validation-self-check",
            "validation-suite-boundary",
            "validation-matrix-meta",
            "validate-list-meta",
            "validate-matrix-meta",
        ):
            assert name in meta, f"{name} must be tagged meta: true"

    def test_behavioral_scenarios_are_surface(self) -> None:
        from automedia.validation.loader import default_scenarios_dir

        library = {s.name: s for s in load_scenarios(default_scenarios_dir())}
        audit = coverage_audit()
        for name in ("health-check-baseline", "pause-pipeline-positive", "cli-surface-behavior"):
            assert name in library, f"{name} missing from library"
            assert name in audit["surface_scenarios"], f"{name} must be a surface scenario"

    def test_cli_coverage_reports_surface_and_meta_counts(self) -> None:
        from typer.testing import CliRunner

        from automedia.cli.app import app

        result = CliRunner().invoke(app, ["validate", "coverage"])
        assert result.exit_code == 1
        assert "surface=" in result.output
        assert "meta=" in result.output
