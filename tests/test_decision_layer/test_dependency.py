"""Tests for automedia.decision.dependency — dependency graph loader.

All tests use a minimal synthetic YAML graph via monkeypatch to avoid
reading the real ``solution-wise/process/dependency-graph.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Synthetic fixture graph
# ---------------------------------------------------------------------------

_MINIMAL_GRAPH: dict[str, Any] = {
    "nodes": [
        {
            "node_id": 1,
            "name": "brand_questionnaire",
            "phase": "0",
            "mode": "both",
            "dependencies": [],
        },
        {
            "node_id": 2,
            "name": "mode_selection",
            "phase": "0",
            "mode": "both",
            "dependencies": [1],
        },
        {
            "node_id": 3,
            "name": "market_research",
            "phase": "1b",
            "mode": "build",
            "dependencies": [2],
        },
        {
            "node_id": 4,
            "name": "brand_positioning",
            "phase": "3",
            "mode": "build",
            "dependencies": [3],
        },
        {
            "node_id": 5,
            "name": "brand_health",
            "phase": "1s",
            "mode": "scale",
            "dependencies": [2],
        },
        {
            "node_id": 6,
            "name": "market_revalidation",
            "phase": "1s",
            "mode": "scale",
            "dependencies": [2],
            "optional": True,
        },
    ],
}


@pytest.fixture(autouse=True)
def _patch_graph_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write the synthetic graph to a temp file and patch ``_GRAPH_PATH``."""
    graph_file = tmp_path / "dependency-graph.yaml"
    graph_file.write_text(yaml.dump(_MINIMAL_GRAPH), encoding="utf-8")
    import automedia.decision.dependency as dep_mod

    monkeypatch.setattr(dep_mod, "_GRAPH_PATH", graph_file)
    return graph_file


# ===================================================================
# get_node()
# ===================================================================


class TestGetNode:
    """get_node() returns the correct node dict or None."""

    def test_returns_node_for_valid_id(self) -> None:
        from automedia.decision.dependency import get_node

        node = get_node(1)
        assert node is not None
        assert node["name"] == "brand_questionnaire"
        assert node["node_id"] == 1

    def test_returns_none_for_unknown_id(self) -> None:
        from automedia.decision.dependency import get_node

        assert get_node(999) is None

    def test_returns_node_with_correct_mode(self) -> None:
        from automedia.decision.dependency import get_node

        node = get_node(3)
        assert node is not None
        assert node["mode"] == "build"


# ===================================================================
# get_dependencies()
# ===================================================================


class TestGetDependencies:
    """get_dependencies() returns prerequisite node IDs."""

    def test_returns_empty_for_root_node(self) -> None:
        from automedia.decision.dependency import get_dependencies

        assert get_dependencies(1) == []

    def test_returns_correct_deps(self) -> None:
        from automedia.decision.dependency import get_dependencies

        deps = get_dependencies(2)
        assert deps == [1]

    def test_returns_empty_for_unknown_node(self) -> None:
        from automedia.decision.dependency import get_dependencies

        assert get_dependencies(999) == []


# ===================================================================
# validate_prerequisites()
# ===================================================================


class TestValidatePrerequisites:
    """validate_prerequisites() checks dependency satisfaction."""

    def test_returns_ok_when_deps_met(self) -> None:
        from automedia.decision.dependency import validate_prerequisites

        ok, missing = validate_prerequisites(2, {1})
        assert ok is True
        assert missing == []

    def test_returns_missing_when_deps_not_met(self) -> None:
        from automedia.decision.dependency import validate_prerequisites

        ok, missing = validate_prerequisites(2, set())
        assert ok is False
        assert missing == [1]

    def test_returns_ok_for_node_with_no_deps(self) -> None:
        from automedia.decision.dependency import validate_prerequisites

        ok, missing = validate_prerequisites(1, set())
        assert ok is True
        assert missing == []

    def test_returns_ok_for_unknown_node(self) -> None:
        from automedia.decision.dependency import validate_prerequisites

        ok, missing = validate_prerequisites(999, set())
        assert ok is True
        assert missing == []


# ===================================================================
# get_nodes_for_mode() / get_required_nodes_for_mode()
# ===================================================================


class TestModeQueries:
    """Mode-based node queries."""

    def test_get_nodes_for_build_mode(self) -> None:
        from automedia.decision.dependency import get_nodes_for_mode

        nodes = get_nodes_for_mode("build")
        ids = {n["node_id"] for n in nodes}
        # "both" nodes are included
        assert 1 in ids and 2 in ids
        # build-only nodes
        assert 3 in ids and 4 in ids

    def test_get_nodes_for_scale_mode(self) -> None:
        from automedia.decision.dependency import get_nodes_for_mode

        nodes = get_nodes_for_mode("scale")
        ids = {n["node_id"] for n in nodes}
        assert 1 in ids and 2 in ids
        assert 5 in ids

    def test_get_required_nodes_for_build(self) -> None:
        from automedia.decision.dependency import get_required_nodes_for_mode

        required = get_required_nodes_for_mode("build")
        assert isinstance(required, set)
        assert len(required) > 0
        # Node 6 is optional — should NOT be in build-required
        assert 6 not in required

    def test_get_required_nodes_for_scale(self) -> None:
        from automedia.decision.dependency import get_required_nodes_for_mode

        required = get_required_nodes_for_mode("scale")
        assert isinstance(required, set)
        # Node 6 is optional in scale mode
        assert 6 not in required
        # Node 5 is required in scale mode
        assert 5 in required


# ===================================================================
# list_all_nodes()
# ===================================================================


class TestListAllNodes:
    """list_all_nodes() returns full node list."""

    def test_returns_list(self) -> None:
        from automedia.decision.dependency import list_all_nodes

        nodes = list_all_nodes()
        assert isinstance(nodes, list)

    def test_returns_all_nodes(self) -> None:
        from automedia.decision.dependency import list_all_nodes

        nodes = list_all_nodes()
        assert len(nodes) == 6

    def test_returns_empty_when_file_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from automedia.decision.dependency import list_all_nodes
        import automedia.decision.dependency as dep_mod

        monkeypatch.setattr(dep_mod, "_GRAPH_PATH", Path("/nonexistent/path.yaml"))
        nodes = list_all_nodes()
        assert nodes == []
