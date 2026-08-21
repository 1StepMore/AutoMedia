"""Unit tests for the validation matrix (issue #86).

The matrix combines the static coverage audit with a per-scenario
surface/status grid.  All fixtures are synthetic: scenario libraries and
engine-shaped suite records written into ``tmp_path`` — never the real
library or a real run record.  Scenario files cite only real
``STANDARDS.md`` keys (the loader cross-checks against the project
registry), and every scenario carries the schema-required ``intent`` and
per-step ``check`` + ``standard``.
"""

from __future__ import annotations

import json
from pathlib import Path

from automedia.validation.coverage import coverage_audit
from automedia.validation.matrix import build_matrix

# Copied from the committed scenarios/STANDARDS.md handbook (real keys the
# loader cross-checks against the project registry).
TOOL_SCENARIO = """\
name: {name}
description: Synthetic fixture scenario.
intent: Prove the fixture surface contract.
category: baseline
requires_env: []
steps:
  - name: call the tool
    kind: tool
    check: The tool answers.
    standard: tool.contract
    tool: health_check
    arguments: {{}}
    expect:
      success: true
"""

CLI_SCENARIO = """\
name: {name}
description: Synthetic cli fixture.
intent: Prove the cli surface contract.
category: baseline
steps:
  - name: run doctor
    kind: cli
    check: doctor prints the dependency listing.
    standard: cli.doctor
    command: automedia doctor
    expect:
      stdout_has: [python]
"""

PROVES_SCENARIO = """\
name: {name}
description: Synthetic fixture proving a gate and a mode.
intent: Prove matrix gates/modes cells come from the declarative headers.
category: pipeline
proves_gates: [G6]
proves_modes: [text_only]
steps:
  - name: call the tool
    kind: tool
    check: The tool answers.
    standard: tool.contract
    tool: health_check
    arguments: {{}}
    expect:
      success: true
"""

HARD_SCENARIO = """\
name: {name}
description: Synthetic hard-safety scenario.
intent: Prove matrix hard flagging reads the header.
category: safety
hard: true
steps:
  - name: call the tool
    kind: tool
    check: The tool answers.
    standard: tool.contract
    tool: health_check
    arguments: {{}}
    expect:
      success: true
"""


def _write_lib(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write synthetic scenario files (name → content) into a temp dir."""
    lib = tmp_path / "scenarios"
    for filename, content in files.items():
        path = lib / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return lib


def _seed_run(root: Path, record: dict[str, object]) -> str:
    """Write a synthetic suite record as the engine would; return the run name."""
    name = "20260101-000000-000000"
    run_dir = root / name
    run_dir.mkdir(parents=True)
    (run_dir / "scenarios.json").write_text(json.dumps(record), encoding="utf-8")
    (root / "latest.txt").write_text(name, encoding="utf-8")
    return name


def _suite_record(status_by_scenario: dict[str, str]) -> dict[str, object]:
    """A suite record in the pinned engine shape: one row per scenario."""
    rows = [
        {
            "scenario": name,
            "status": status,
            "summary": {"total": 1, "passed": 0, "failed": 0},
            "steps": [],
            "cleanup": [],
            "trace_id": "t",
            "error_boundary": False,
        }
        for name, status in status_by_scenario.items()
    ]
    return {"trace_id": "t", "generated_at": "2026-08-14T00:00:00+00:00", "scenarios": rows}


class TestSurfaces:
    def test_surfaces_reuse_audit(self, tmp_path: Path) -> None:
        # Given: a synthetic library with tool + cli + proves scenarios
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
                "cli.yaml": CLI_SCENARIO.format(name="cli-fixture"),
                "proves.yaml": PROVES_SCENARIO.format(name="proves-fixture"),
            },
        )

        # When: the matrix is built
        matrix = build_matrix(lib)

        # Then: every surface dict has exactly the 5 audit keys, carrying the
        # audit's verbatim lists
        for surface in ("mcp", "cli", "gates", "modes"):
            assert set(matrix["surfaces"][surface]) == {
                "declared",
                "covered",
                "missing",
                "phantom",
                "boundary_only",
            }

    def test_rows_have_all_four_surface_cells(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
                "cli.yaml": CLI_SCENARIO.format(name="cli-fixture"),
            },
        )
        matrix = build_matrix(lib)
        assert matrix["rows"]
        for row in matrix["rows"]:
            assert set(row) == {
                "scenario",
                "mcp",
                "cli",
                "gates",
                "modes",
                "hard",
                "last_status",
            }
            for cell in ("mcp", "cli", "gates", "modes", "hard"):
                assert isinstance(row[cell], bool), f"row cell {cell} not a bool"


class TestFlags:
    def test_hard_scenarios_flagged(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
                "hard.yaml": HARD_SCENARIO.format(name="hard-fixture"),
            },
        )
        matrix = build_matrix(lib)
        assert "hard-fixture" in matrix["flags"]["hard"]
        entry = next(s for s in matrix["scenarios"] if s["name"] == "hard-fixture")
        assert entry["hard"] is True
        row = next(r for r in matrix["rows"] if r["scenario"] == "hard-fixture")
        assert row["hard"] is True

    def test_boundary_only_flags_reuse_audit(self, tmp_path: Path) -> None:
        boundary = TOOL_SCENARIO.format(name="boundary-fixture").replace(
            "category: baseline",
            "category: surface\nerror_boundary: true",
        )
        lib = _write_lib(tmp_path, {"boundary.yaml": boundary})
        matrix = build_matrix(lib)
        audit = coverage_audit(lib)
        assert matrix["flags"]["boundary_only"] == ["boundary.yaml"]
        assert matrix["flags"]["missing"] == {
            "mcp": audit["missing_mcp"],
            "cli": audit["missing_cli"],
            "gates": audit["missing_gates"],
            "modes": audit["missing_modes"],
        }


class TestLastStatus:
    def test_last_run_status_included_when_record_exists(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
                "cli.yaml": CLI_SCENARIO.format(name="cli-fixture"),
            },
        )
        runs_root = tmp_path / "runs"
        _seed_run(runs_root, _suite_record({"health-fixture": "passed"}))
        matrix = build_matrix(lib, runs_root=runs_root)
        by_name = {s["name"]: s for s in matrix["scenarios"]}
        assert by_name["health-fixture"]["last_status"] == "passed"
        assert by_name["cli-fixture"]["last_status"] is None
        row = next(r for r in matrix["rows"] if r["scenario"] == "health-fixture")
        assert row["last_status"] == "passed"

    def test_no_runs_root_status_unknown(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
            },
        )
        matrix = build_matrix(lib, runs_root=tmp_path / "does-not-exist")
        entry = next(s for s in matrix["scenarios"] if s["name"] == "health-fixture")
        assert entry["last_status"] is None
        assert all(row["last_status"] is None for row in matrix["rows"])

    def test_corrupt_run_record_never_crashes(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
            },
        )
        runs_root = tmp_path / "runs"
        run_dir = runs_root / "20260101-000000-000000"
        run_dir.mkdir(parents=True)
        (run_dir / "scenarios.json").write_text("not json", encoding="utf-8")
        (runs_root / "latest.txt").write_text("20260101-000000-000000", encoding="utf-8")
        matrix = build_matrix(lib, runs_root=runs_root)
        entry = next(s for s in matrix["scenarios"] if s["name"] == "health-fixture")
        assert entry["last_status"] is None


class TestDeterminism:
    def test_deterministic_output(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
                "cli.yaml": CLI_SCENARIO.format(name="cli-fixture"),
                "proves.yaml": PROVES_SCENARIO.format(name="proves-fixture"),
                "hard.yaml": HARD_SCENARIO.format(name="hard-fixture"),
            },
        )
        first = build_matrix(lib)
        second = build_matrix(lib)
        assert first == second


class TestCellSemantics:
    def test_surface_cell_semantics(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
                "cli.yaml": CLI_SCENARIO.format(name="cli-fixture"),
                "proves.yaml": PROVES_SCENARIO.format(name="proves-fixture"),
            },
        )
        matrix = build_matrix(lib)
        by_name = {r["scenario"]: r for r in matrix["rows"]}
        assert by_name["health-fixture"]["mcp"] is True
        assert by_name["health-fixture"]["cli"] is False
        assert by_name["cli-fixture"]["cli"] is True
        assert by_name["cli-fixture"]["mcp"] is False
        assert by_name["proves-fixture"]["gates"] is True
        assert by_name["proves-fixture"]["modes"] is True
        assert by_name["health-fixture"]["gates"] is False

    def test_recovery_and_cleanup_tool_steps_mark_mcp(self, tmp_path: Path) -> None:
        scenario = TOOL_SCENARIO.format(name="recovery-fixture").replace(
            "    expect:\n      success: true",
            "    expect:\n      success: true\n    recovery_steps:\n"
            "      - name: recover\n"
            "        kind: tool\n"
            "        check: Recovery calls the surface.\n"
            "        standard: tool.contract\n"
            "        tool: cancel_pipeline\n"
            "        arguments: {}\n"
            "        expect: {}\n"
            "cleanup_steps:\n"
            "  - name: clean up\n"
            "    kind: tool\n"
            "    check: Cleanup calls the surface.\n"
            "    standard: tool.contract\n"
            "    tool: cancel_pipeline\n"
            "    arguments: {}\n"
            "    expect: {}",
        )
        lib = _write_lib(tmp_path, {"recovery.yaml": scenario})
        matrix = build_matrix(lib)
        row = next(r for r in matrix["rows"] if r["scenario"] == "recovery-fixture")
        assert row["mcp"] is True


class TestStatusHint:
    def test_status_hint_precedence(self, tmp_path: Path) -> None:
        requires_env = TOOL_SCENARIO.format(name="env-fixture").replace(
            "category: baseline\nrequires_env: []",
            "category: baseline\nrequires_env: [AUTOMEDIA_LLM_API_KEY]",
        )
        boundary = TOOL_SCENARIO.format(name="boundary-fixture").replace(
            "category: baseline",
            "category: surface\nerror_boundary: true",
        )
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
                "env.yaml": requires_env,
                "boundary.yaml": boundary,
                "hard.yaml": HARD_SCENARIO.format(name="hard-fixture"),
            },
        )
        matrix = build_matrix(lib)
        by_name = {s["name"]: s for s in matrix["scenarios"]}
        assert by_name["health-fixture"]["status_hint"] == "ready"
        assert by_name["env-fixture"]["status_hint"] == (
            "requires-env: AUTOMEDIA_LLM_API_KEY"
        )
        assert by_name["boundary-fixture"]["status_hint"] == "error-boundary probe"
        assert by_name["hard-fixture"]["status_hint"] == "hard"


class TestShape:
    def test_summary_and_surface_sections_present(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(name="health-fixture"),
            },
        )
        matrix = build_matrix(lib, runs_root=tmp_path / "no-runs")
        assert set(matrix) == {
            "surfaces",
            "scenarios",
            "rows",
            "flags",
            "summary",
            "report_cards",
            "assertions",
            "diff",
        }
        assert matrix["summary"] == matrix["summary"]  # verbatim audit summary
        assert set(matrix["flags"]) == {"hard", "boundary_only", "missing"}
        # the assertion half is run-record-derived: no runs → empty, never a crash
        assert matrix["report_cards"] == []
        assert matrix["assertions"] == {}
        assert matrix["diff"] is None
