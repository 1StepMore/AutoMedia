"""Unit tests for the affected-area mapper (plan W5-T3, scripts/validation_affected.py).

All fixtures are synthetic (Red Line 4): a small scenario library under
``tmp_path`` — files are minimal scenario-shaped YAML (``name`` + ``steps``
+ optional ``requires_env``), enough for the mapper's structural rules and
env-free scan.  The mapper is pure (no automedia import), so tests only
exercise ``map_affected`` + the ``main`` CLI surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation_affected import main, map_affected

# Scenario-shaped docs; ``requires_env`` controls env-free classification.
_LAYOUT: dict[str, dict[str, object]] = {
    "health-check.yaml": {},
    "get-config.yaml": {"requires_env": []},
    "llm-gated.yaml": {"requires_env": ["AUTOMEDIA_LLM_API_KEY"]},
    "cli/run-cli.yaml": {},
    "surface/health/engine-health.yaml": {},
    "surface/pool/select-topic.yaml": {},
    "publish/publish-dry-run.yaml": {},
    "publish/publish-draft.yaml": {"requires_env": ["AUTOMEDIA_INSTAGRAM_TOKEN"]},
    "journeys/lifecycle.yaml": {},
    "journeys/text-only.yaml": {"requires_env": ["AUTOMEDIA_LLM_API_KEY"]},
    "quality/quality-draft.yaml": {},
    "regression/reg-pin.yaml": {},
}

# All env-free + root-batch files — the expected fallback net.
_FALLBACK_EXPECTED = [
    "cli/run-cli.yaml",
    "get-config.yaml",
    "health-check.yaml",
    "journeys/lifecycle.yaml",
    "llm-gated.yaml",  # root batch includes env-gated ROOT files
    "publish/publish-dry-run.yaml",
    "quality/quality-draft.yaml",
    "regression/reg-pin.yaml",
    "surface/health/engine-health.yaml",
    "surface/pool/select-topic.yaml",
]


@pytest.fixture
def scenarios_dir(tmp_path: Path) -> Path:
    """A synthetic scenario library with one file per layout entry."""
    root = tmp_path / "scenarios"
    for rel, fields in _LAYOUT.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"name": rel.replace("/", "-").removesuffix(".yaml"), "steps": [], **fields}
        path.write_text(_dump(doc), encoding="utf-8")
    return root


def _dump(doc: dict[str, object]) -> str:
    """Deterministic YAML dump via manual lines (pyyaml adds ``...`` noise)."""
    lines = [f"name: {doc['name']}", "steps: []"]
    requires_env = doc.get("requires_env")
    if requires_env is not None:
        env = "".join(f"  - {name}\n" for name in requires_env) or "  []"
        lines.append(f"requires_env:\n{env}".rstrip())
    return "\n".join(lines) + "\n"


# ── Explicit rules ────────────────────────────────────────────────────────────


def test_mcp_change_maps_all_surface_scenarios(scenarios_dir: Path) -> None:
    result = map_affected(["src/automedia/mcp/server.py"], scenarios_dir=scenarios_dir)
    assert result == [
        "surface/health/engine-health.yaml",
        "surface/pool/select-topic.yaml",
    ]


def test_cli_change_maps_all_cli_scenarios(scenarios_dir: Path) -> None:
    result = map_affected(["src/automedia/cli/commands/validate.py"], scenarios_dir=scenarios_dir)
    assert result == ["cli/run-cli.yaml"]


def test_gates_change_maps_journeys_and_quality(scenarios_dir: Path) -> None:
    result = map_affected(["src/automedia/gates/fact_check.py"], scenarios_dir=scenarios_dir)
    assert result == [
        "journeys/lifecycle.yaml",
        "journeys/text-only.yaml",
        "quality/quality-draft.yaml",
    ]


def test_adapters_change_maps_publish_scenarios(scenarios_dir: Path) -> None:
    result = map_affected(
        ["src/automedia/adapters/platforms/wechat.py"], scenarios_dir=scenarios_dir
    )
    assert result == [
        "publish/publish-draft.yaml",
        "publish/publish-dry-run.yaml",
    ]


def test_scenario_change_maps_itself_plus_regression(scenarios_dir: Path) -> None:
    result = map_affected(["scenarios/quality/quality-draft.yaml"], scenarios_dir=scenarios_dir)
    assert result == [
        "quality/quality-draft.yaml",
        "regression/reg-pin.yaml",
    ]


def test_deleted_scenario_contributes_only_regression(scenarios_dir: Path) -> None:
    result = map_affected(["scenarios/ghost-deleted.yaml"], scenarios_dir=scenarios_dir)
    assert result == ["regression/reg-pin.yaml"]


# ── Ambiguity ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "src/automedia/core/config_loader.py",
        "src/automedia/validation/engine.py",
        "src/automedia/core/project.py",
    ],
)
def test_core_or_validation_change_is_full_suite(scenarios_dir: Path, path: str) -> None:
    assert map_affected([path], scenarios_dir=scenarios_dir) == ["--all"]


def test_one_ambiguous_path_makes_the_whole_result_all(scenarios_dir: Path) -> None:
    result = map_affected(
        ["src/automedia/adapters/base.py", "src/automedia/core/config_loader.py"],
        scenarios_dir=scenarios_dir,
    )
    assert result == ["--all"]


def test_empty_changed_list_is_full_suite(scenarios_dir: Path) -> None:
    assert map_affected([], scenarios_dir=scenarios_dir) == ["--all"]


# ── Fallback ──────────────────────────────────────────────────────────────────


def test_unmatched_path_falls_back_to_batch_plus_env_free(scenarios_dir: Path) -> None:
    result = map_affected(["pyproject.toml"], scenarios_dir=scenarios_dir)
    assert result == _FALLBACK_EXPECTED


def test_fallback_excludes_env_gated_non_root_scenarios(scenarios_dir: Path) -> None:
    result = map_affected(["src/automedia/pipelines/runner.py"], scenarios_dir=scenarios_dir)
    assert "publish/publish-draft.yaml" not in result  # env-gated, non-root
    assert "journeys/text-only.yaml" not in result  # env-gated, non-root
    assert "llm-gated.yaml" in result  # root batch includes it


def test_fallback_union_with_explicit_rules(scenarios_dir: Path) -> None:
    """An unmatched path does not discard the explicit-rule results."""
    result = map_affected(["src/automedia/mcp/server.py", "README.md"], scenarios_dir=scenarios_dir)
    assert "surface/health/engine-health.yaml" in result
    assert result == sorted(set(result) | set(_FALLBACK_EXPECTED))


def test_scenarios_are_sorted_deterministically(scenarios_dir: Path) -> None:
    result = map_affected(["src/automedia/mcp/server.py"], scenarios_dir=scenarios_dir)
    assert result == sorted(result)
    assert map_affected(["src/automedia/mcp/server.py"], scenarios_dir=scenarios_dir) == result


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_all_flag_prints_full_suite_marker(
    scenarios_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(scenarios_dir))
    assert main(["--all"]) == 0
    assert capsys.readouterr().out.splitlines() == ["--all"]


def test_cli_changed_paths_print_affected_files(
    scenarios_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(scenarios_dir))
    assert main(["src/automedia/adapters/base.py"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "publish/publish-draft.yaml",
        "publish/publish-dry-run.yaml",
    ]
