"""Unit tests for the coverage audit (W3-T7/C4, guide §5.1).

All fixtures are synthetic: server/app module snippets and scenario
libraries written into ``tmp_path`` — never the real repo files.  Scenario
fixtures cite only real ``STANDARDS.md`` keys (the loader cross-checks
against the project registry), and every scenario carries the schema-required
``intent`` / per-step ``check`` + ``standard``.

Covers: declared extraction from both surfaces (including the
``Tool(name=...)`` non-match and the import-alias resolution), used
extraction (tool names, cli subcommand parsing, non-automedia commands
ignored), the boundary-only third class, phantom detection, determinism, and
the ``missing = ∅`` computation.
"""

from __future__ import annotations

from pathlib import Path

from automedia.validation.coverage import coverage_audit

SERVER_SNIPPET = """\
# Synthetic server snippet (fixture — never the real server.py).
from automedia.effects.mcp import analyze_content as effects_analyze_content
from automedia.mcp.tools import cancel_pipeline, health_check


def register(mcp):
    mcp.tool(description="Health check.")(health_check)
    mcp.tool(description="Cancel control.")(cancel_pipeline)
    mcp.tool(
        description=("Compute content analytics. "),
    )(effects_analyze_content)
    mcp.tool(description="Deprecated alias.", name="pool_add_topic")(pool_add_topic)
    # Tool(name=...) declarations must NOT match the registration regex.
    Tool(name="not_a_registration")


def helper(mcp):
    return mcp.tool(description="Duplicate registration.")(health_check)
"""

APP_SNIPPET = """\
# Synthetic app snippet (fixture — never the real app.py).
LazyTyperGroup.register_sub_app(
    "account",
    "automedia.cli.commands.account",
    help_text="Manage platform accounts.",
)
LazyTyperGroup.register_fn(
    "run", "automedia.cli.commands.run", "run_cmd", help_text="Run the pipeline."
)
LazyTyperGroup.register_fn(
    "doctor",
    "automedia.cli.commands.doctor",
    "doctor_cmd",
    help_text="Check system dependencies.",
)
register_sub_app('single', 'mod.path', help_text="Single-quoted name.")
register_other("ignored", "mod.path", help_text="Not a sub_app/fn registration.")
"""

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
    tool: {tool}
    arguments: {{}}
    expect:
      success: true
"""

BOUNDARY_SCENARIO = """\
name: {name}
description: Synthetic boundary probe (never GREEN-asserted).
intent: Prove the dispatcher rejects on the boundary path.
category: surface
error_boundary: true
steps:
  - name: probe the boundary
    kind: tool
    check: The probe expects an error.
    standard: tool.contract
    tool: {tool}
    arguments: {{}}
    expect: {{}}
"""

CLI_SCENARIO = """\
name: cli-mixed-steps
description: Synthetic cli-kind fixture.
intent: Prove cli subcommand extraction from mixed commands.
category: baseline
steps:
  - name: subcommand with flags
    kind: cli
    check: run --help exits 0.
    standard: founder-expectations.F02
    command: automedia run --help
    expect:
      exit_code: 0
  - name: global flag before subcommand
    kind: cli
    check: doctor prints the listing contract.
    standard: cli.doctor
    command: automedia --json doctor
    expect:
      stdout_has: [python]
  - name: non-automedia command ignored
    kind: cli
    check: setup commands are not surface coverage.
    standard: founder-expectations.F02
    command: python3 -c "print(1)"
    expect:
      exit_code: 0
  - name: cleanup command ignored
    kind: cli
    check: rm is not surface coverage.
    standard: founder-expectations.F02
    command: rm -rf /tmp/synthetic
    expect: {}
  - name: file-kind step ignored
    kind: file
    check: The manifest exists.
    standard: founder-expectations.F01
    command: pyproject.toml
    expect:
      artifact_exists: pyproject.toml
  - name: validate family is a phantom until W4
    kind: cli
    check: validate list shows the family.
    standard: founder-expectations.F02
    command: automedia validate list
    expect:
      exit_code: 0
  - name: bare automedia ignored
    kind: cli
    check: Bare binary names no subcommand.
    standard: founder-expectations.F02
    command: automedia --help
    expect: {}
"""


def _write_lib(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write synthetic scenario files (name → content) into a temp dir."""
    lib = tmp_path / "scenarios"
    for filename, content in files.items():
        path = lib / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return lib


def _write_declared(tmp_path: Path) -> tuple[Path, Path]:
    server = tmp_path / "server_snippet.py"
    app = tmp_path / "app_snippet.py"
    server.write_text(SERVER_SNIPPET, encoding="utf-8")
    app.write_text(APP_SNIPPET, encoding="utf-8")
    return server, app


def _audit(tmp_path: Path, files: dict[str, str]) -> dict:
    lib = _write_lib(tmp_path, files)
    server, app = _write_declared(tmp_path)
    return coverage_audit(lib, server_path=server, app_path=app)


class TestShape:
    def test_output_carries_the_full_contract_shape(self, tmp_path: Path) -> None:
        result = _audit(
            tmp_path,
            {"health.yaml": TOOL_SCENARIO.format(name="health-fixture", tool="health_check")},
        )
        for key in (
            "declared_mcp",
            "declared_cli",
            "used_mcp",
            "used_cli",
            "covered_mcp",
            "covered_cli",
            "missing_mcp",
            "missing_cli",
            "phantom_mcp",
            "phantom_cli",
            "boundary_only_mcp",
            "boundary_only_cli",
            "error_boundary_scenarios",
            "director_waiver_note",
            "phantom_note",
            "summary",
        ):
            assert key in result, f"audit output missing key {key!r}"
        for key in (
            "mcp_declared",
            "mcp_used",
            "mcp_covered",
            "mcp_missing",
            "mcp_phantom",
            "mcp_boundary_only",
            "cli_declared",
            "cli_used",
            "cli_covered",
            "cli_missing",
            "cli_phantom",
            "cli_boundary_only",
        ):
            assert key in result["summary"], f"summary missing key {key!r}"


class TestDeclaredMCP:
    def test_regex_extracts_tool_calls_and_ignores_tool_declarations(
        self, tmp_path: Path
    ) -> None:
        result = _audit(
            tmp_path,
            {"health.yaml": TOOL_SCENARIO.format(name="health-fixture", tool="health_check")},
        )
        assert result["declared_mcp"] == [
            "analyze_content",
            "cancel_pipeline",
            "health_check",
            "pool_add_topic",
        ]

    def test_alias_import_resolves_to_callable_name(self, tmp_path: Path) -> None:
        # The scenario calls the CALLABLE name (fn.__name__), not the alias.
        result = _audit(
            tmp_path,
            {
                "analyze.yaml": TOOL_SCENARIO.format(
                    name="analyze-fixture", tool="analyze_content"
                )
            },
        )
        assert "analyze_content" in result["covered_mcp"]
        assert "effects_analyze_content" not in result["declared_mcp"]
        assert "effects_analyze_content" not in result["phantom_mcp"]


class TestDeclaredCLI:
    def test_registrations_parsed_including_single_quotes(self, tmp_path: Path) -> None:
        result = _audit(
            tmp_path,
            {"health.yaml": TOOL_SCENARIO.format(name="health-fixture", tool="health_check")},
        )
        assert result["declared_cli"] == ["account", "doctor", "run", "single"]
        assert "ignored" not in result["declared_cli"]


class TestUsedExtraction:
    def test_tool_and_cli_targets_with_non_automedia_commands_ignored(
        self, tmp_path: Path
    ) -> None:
        result = _audit(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(
                    name="health-fixture", tool="health_check"
                ),
                "cli.yaml": CLI_SCENARIO,
            },
        )
        assert "health_check" in result["used_mcp"]
        assert result["used_cli"] == ["doctor", "run", "validate"]
        # python3 / rm / file-kind / bare automedia contribute nothing.
        assert "python3" not in result["used_cli"]
        assert "rm" not in result["used_cli"]
        assert "pyproject.toml" not in result["used_cli"]

    def test_cleanup_and_recovery_steps_are_declared_adapter_calls_too(
        self, tmp_path: Path
    ) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "tool.yaml": TOOL_SCENARIO.format(
                    name="tool-fixture", tool="health_check"
                )
            },
        )
        cleanup = lib / "cleanup.yaml"
        cleanup.write_text(
            TOOL_SCENARIO.format(name="cleanup-fixture", tool="cancel_pipeline"),
            encoding="utf-8",
        )
        text = cleanup.read_text(encoding="utf-8")
        cleanup.write_text(
            text.replace(
                "    expect:\n      success: true",
                "    expect:\n      success: true\n    recovery_steps:\n"
                "      - name: recover via alias tool\n"
                "        kind: tool\n"
                "        check: Recovery calls the surface.\n"
                "        standard: tool.contract\n"
                "        tool: pool_add_topic\n"
                "        arguments: {}\n"
                "        expect: {}\n"
                "    collect_artifacts: []\n"
                "cleanup_steps:\n"
                "  - name: clean up\n"
                "    kind: tool\n"
                "    check: Cleanup calls the surface.\n"
                "    standard: tool.contract\n"
                "    tool: pool_add_topic\n"
                "    arguments: {}\n"
                "    expect: {}",
            ),
            encoding="utf-8",
        )
        server, app = _write_declared(tmp_path)
        result = coverage_audit(lib, server_path=server, app_path=app)
        assert "pool_add_topic" in result["used_mcp"]


class TestMissingScenariosDir:
    def test_nonexistent_dir_yields_empty_used_sets(self, tmp_path: Path) -> None:
        server, app = _write_declared(tmp_path)
        result = coverage_audit(
            tmp_path / "does-not-exist", server_path=server, app_path=app
        )
        assert result["used_mcp"] == []
        assert result["used_cli"] == []
        assert result["missing_mcp"] == result["declared_mcp"]
        assert result["missing_cli"] == result["declared_cli"]
        assert result["error_boundary_scenarios"] == []


class TestBoundaryOnly:
    def test_boundary_scenario_targets_are_third_class(self, tmp_path: Path) -> None:
        result = _audit(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(
                    name="health-fixture", tool="health_check"
                ),
                "cancel.yaml": BOUNDARY_SCENARIO.format(
                    name="cancel-boundary-fixture", tool="cancel_pipeline"
                ),
                "pool.yaml": TOOL_SCENARIO.format(
                    name="pool-fixture", tool="pool_add_topic"
                ),
                "analyze.yaml": TOOL_SCENARIO.format(
                    name="analyze-fixture", tool="analyze_content"
                ),
            },
        )
        assert result["boundary_only_mcp"] == ["cancel_pipeline"]
        assert result["boundary_only_cli"] == []
        assert "cancel_pipeline" not in result["covered_mcp"]
        assert "cancel_pipeline" not in result["missing_mcp"]
        assert "cancel_pipeline" not in result["phantom_mcp"]
        assert result["missing_mcp"] == []
        assert result["error_boundary_scenarios"] == ["cancel.yaml"]
        assert "Boundary-only allowlist" in result["director_waiver_note"]
        assert "cancel_pipeline" in result["director_waiver_note"]
        assert "Phantom = used minus declared" in result["phantom_note"]

    def test_step_level_boundary_within_normal_scenario_stays_covered(
        self, tmp_path: Path
    ) -> None:
        # Only scenario-level error_boundary reclassifies (plan: the audit
        # reads the scenario level only).
        step_probe = TOOL_SCENARIO.format(name="probe-fixture", tool="cancel_pipeline")
        step_probe = step_probe.replace(
            "      success: true", "      success: true\n    error_boundary: true"
        )
        result = _audit(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(
                    name="health-fixture", tool="health_check"
                ),
                "probe.yaml": step_probe,
            },
        )
        assert result["boundary_only_mcp"] == []
        assert result["covered_mcp"] == ["cancel_pipeline", "health_check"]

    def test_boundary_target_undeclared_is_phantom_too(self, tmp_path: Path) -> None:
        # Phantom is pure (used − declared): a boundary scenario naming a
        # nonexistent tool is boundary-only AND phantom, never covered.
        result = _audit(
            tmp_path,
            {
                "ghost-boundary.yaml": BOUNDARY_SCENARIO.format(
                    name="ghost-boundary-fixture", tool="ghost_tool"
                )
            },
        )
        assert result["boundary_only_mcp"] == ["ghost_tool"]
        assert result["phantom_mcp"] == ["ghost_tool"]


class TestPhantom:
    def test_undeclared_tool_target_is_phantom(self, tmp_path: Path) -> None:
        result = _audit(
            tmp_path,
            {
                "ghost.yaml": TOOL_SCENARIO.format(
                    name="ghost-fixture", tool="ghost_tool"
                ),
                "health.yaml": TOOL_SCENARIO.format(
                    name="health-fixture", tool="health_check"
                ),
            },
        )
        assert result["phantom_mcp"] == ["ghost_tool"]
        assert result["covered_mcp"] == ["health_check"]
        assert "ghost_tool" in result["phantom_note"]

    def test_validate_command_is_expected_phantom(self, tmp_path: Path) -> None:
        result = _audit(
            tmp_path,
            {
                "cli.yaml": CLI_SCENARIO,
                "health.yaml": TOOL_SCENARIO.format(
                    name="health-fixture", tool="health_check"
                ),
            },
        )
        assert result["phantom_cli"] == ["validate"]
        assert result["phantom_mcp"] == []
        assert "W4" in result["phantom_note"]


class TestMissingEmpty:
    def test_all_declared_surfaces_covered_gives_empty_missing(self, tmp_path: Path) -> None:
        result = _audit(
            tmp_path,
            {
                "health.yaml": TOOL_SCENARIO.format(
                    name="health-fixture", tool="health_check"
                ),
                "cancel.yaml": BOUNDARY_SCENARIO.format(
                    name="cancel-boundary-fixture", tool="cancel_pipeline"
                ),
                "pool.yaml": TOOL_SCENARIO.format(
                    name="pool-fixture", tool="pool_add_topic"
                ),
                "analyze.yaml": TOOL_SCENARIO.format(
                    name="analyze-fixture", tool="analyze_content"
                ),
                "run.yaml": CLI_SCENARIO,
            },
        )
        # health_check + pool_add_topic covered, analyze_content covered,
        # cancel_pipeline boundary-only: missing = ∅ (∅ excluding
        # boundary-only).  CLI: run + doctor covered; validate phantom;
        # declared account/single untouched → still missing = ∅ for CLI only
        # because... no: declared-but-unused commands ARE missing.
        assert result["missing_mcp"] == []
        assert "run" in result["covered_cli"]
        assert "doctor" in result["covered_cli"]
        assert result["missing_cli"] == ["account", "single"]
        assert result["summary"]["mcp_missing"] == 0
        assert result["summary"]["mcp_boundary_only"] == 1


class TestDeterminism:
    def test_same_inputs_produce_identical_output(self, tmp_path: Path) -> None:
        files = {
            "health.yaml": TOOL_SCENARIO.format(
                name="health-fixture", tool="health_check"
            ),
            "cancel.yaml": BOUNDARY_SCENARIO.format(
                name="cancel-boundary-fixture", tool="cancel_pipeline"
            ),
            "cli.yaml": CLI_SCENARIO,
        }
        first = _audit(tmp_path, files)
        second = _audit(tmp_path, files)
        assert first == second

    def test_output_lists_are_sorted(self, tmp_path: Path) -> None:
        result = _audit(
            tmp_path,
            {
                "b.yaml": TOOL_SCENARIO.format(name="b-fixture", tool="pool_add_topic"),
                "a.yaml": TOOL_SCENARIO.format(name="a-fixture", tool="health_check"),
            },
        )
        assert result["covered_mcp"] == sorted(result["covered_mcp"])
        assert result["declared_mcp"] == sorted(result["declared_mcp"])
