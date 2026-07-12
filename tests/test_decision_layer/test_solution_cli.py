"""Tests for automedia.decision.cli.solution — Decision-layer CLI commands.

Uses monkeypatched dependency graph and state file for isolation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Synthetic dependency graph
# ---------------------------------------------------------------------------

_GRAPH: dict[str, Any] = {
    "nodes": [
        {"node_id": 1, "name": "brand_questionnaire", "phase": "0", "mode": "both", "dependencies": []},
        {"node_id": 2, "name": "mode_selection", "phase": "0", "mode": "both", "dependencies": [1]},
        {"node_id": 3, "name": "market_research", "phase": "1b", "mode": "build", "dependencies": [2]},
        {"node_id": 4, "name": "brand_positioning", "phase": "3", "mode": "build", "dependencies": [3]},
    ],
}


@pytest.fixture(autouse=True)
def _patch_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_file = tmp_path / "dependency-graph.yaml"
    graph_file.write_text(yaml.dump(_GRAPH), encoding="utf-8")
    import automedia.decision.dependency as dep_mod

    monkeypatch.setattr(dep_mod, "_GRAPH_PATH", graph_file)


@pytest.fixture()
def _patch_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state_file = tmp_path / ".solution-state.yaml"
    import automedia.decision.cli.solution as sol_mod

    monkeypatch.setattr(sol_mod, "_STATE_FILE", state_file)
    return state_file


# ===================================================================
# Helper functions
# ===================================================================


class TestDefaultState:
    """_default_state() returns expected shape."""

    def test_returns_dict_with_required_keys(self) -> None:
        from automedia.decision.cli.solution import _default_state

        state = _default_state()
        assert "brand" in state
        assert "completed_nodes" in state
        assert "completions" in state

    def test_brand_is_none_by_default(self) -> None:
        from automedia.decision.cli.solution import _default_state

        assert _default_state()["brand"] is None

    def test_completed_nodes_is_empty_list(self) -> None:
        from automedia.decision.cli.solution import _default_state

        assert _default_state()["completed_nodes"] == []


class TestResolveNodeId:
    """_resolve_node_id() maps node names to IDs."""

    def test_returns_id_for_known_name(self) -> None:
        from automedia.decision.cli.solution import _resolve_node_id

        assert _resolve_node_id("brand_questionnaire") == 1

    def test_returns_none_for_unknown_name(self) -> None:
        from automedia.decision.cli.solution import _resolve_node_id

        assert _resolve_node_id("nonexistent_node") is None


class TestResolveNameFromId:
    """_resolve_name_from_id() maps IDs to node names."""

    def test_returns_name_for_known_id(self) -> None:
        from automedia.decision.cli.solution import _resolve_name_from_id

        assert _resolve_name_from_id(1) == "brand_questionnaire"

    def test_returns_none_for_unknown_id(self) -> None:
        from automedia.decision.cli.solution import _resolve_name_from_id

        assert _resolve_name_from_id(999) is None


class TestValidateMode:
    """_validate_mode() raises Exit for invalid modes."""

    def test_accepts_build(self) -> None:
        from automedia.decision.cli.solution import _validate_mode

        _validate_mode("build")  # should not raise

    def test_accepts_scale(self) -> None:
        from automedia.decision.cli.solution import _validate_mode

        _validate_mode("scale")  # should not raise

    def test_rejects_invalid_mode(self) -> None:
        import typer
        from automedia.decision.cli.solution import _validate_mode

        with pytest.raises(typer.Exit):
            _validate_mode("invalid")


# ===================================================================
# CLI commands via CliRunner
# ===================================================================


class TestCompleteNodeCommand:
    """complete-node command via typer.testing.CliRunner."""

    def test_marks_node_as_completed(
        self, _patch_state_file: Path, tmp_path: Path
    ) -> None:
        from typer.testing import CliRunner

        from automedia.decision.cli.solution import app

        runner = CliRunner()
        result = runner.invoke(app, ["complete-node", "--node", "brand_questionnaire", "--brand", "test"])
        assert result.exit_code == 0

        state = yaml.safe_load(_patch_state_file.read_text(encoding="utf-8"))
        assert "brand_questionnaire" in state["completed_nodes"]

    def test_rejects_unknown_node(self, _patch_state_file: Path) -> None:
        from typer.testing import CliRunner

        from automedia.decision.cli.solution import app

        runner = CliRunner()
        result = runner.invoke(app, ["complete-node", "--node", "fake_node", "--brand", "test"])
        assert result.exit_code != 0


class TestApproveNodeCommand:
    """approve-node command via typer.testing.CliRunner."""

    def test_records_approval(
        self, _patch_state_file: Path, tmp_path: Path
    ) -> None:
        from typer.testing import CliRunner

        from automedia.decision.cli.solution import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["approve-node", "--node", "brand_questionnaire", "--by", "alice"],
        )
        assert result.exit_code == 0

        state = yaml.safe_load(_patch_state_file.read_text(encoding="utf-8"))
        assert len(state["completions"]) == 1
        assert state["completions"][0]["by"] == "alice"


class TestNextNodeCommand:
    """next-node command via typer.testing.CliRunner."""

    def test_shows_first_pending_node(self, _patch_state_file: Path) -> None:
        from typer.testing import CliRunner

        from automedia.decision.cli.solution import app

        runner = CliRunner()
        result = runner.invoke(app, ["next-node", "--mode", "build"])
        assert result.exit_code == 0
        assert "brand_questionnaire" in result.output

    def test_rejects_invalid_mode(self, _patch_state_file: Path) -> None:
        from typer.testing import CliRunner

        from automedia.decision.cli.solution import app

        runner = CliRunner()
        result = runner.invoke(app, ["next-node", "--mode", "bad"])
        assert result.exit_code != 0


class TestPreflightCheckCommand:
    """preflight-check command via typer.testing.CliRunner."""

    def test_reports_missing_nodes(self, _patch_state_file: Path) -> None:
        from typer.testing import CliRunner

        from automedia.decision.cli.solution import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["preflight-check", "--next-phase", "1b", "--mode", "build"]
        )
        # Phase 0 nodes not completed → should warn
        assert result.exit_code != 0

    def test_passes_when_all_complete(self, _patch_state_file: Path) -> None:
        from typer.testing import CliRunner

        from automedia.decision.cli.solution import app

        state = {
            "brand": "test",
            "completed_nodes": [
                "brand_questionnaire",
                "mode_selection",
                "market_research",
            ],
            "completions": [],
        }
        _patch_state_file.write_text(yaml.dump(state), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            app, ["preflight-check", "--next-phase", "2", "--mode", "build"]
        )
        assert result.exit_code == 0
