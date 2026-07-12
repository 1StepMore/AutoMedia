"""Tests for automedia.decision.preflight — phase transition checker.

Uses a synthetic dependency graph via monkeypatch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Synthetic graph — same as test_dependency for consistency
# ---------------------------------------------------------------------------

_GRAPH: dict[str, Any] = {
    "nodes": [
        {"node_id": 1, "name": "brand_questionnaire", "phase": "0", "mode": "both", "dependencies": []},
        {"node_id": 2, "name": "mode_selection", "phase": "0", "mode": "both", "dependencies": [1]},
        {"node_id": 3, "name": "market_research", "phase": "1b", "mode": "build", "dependencies": [2]},
        {"node_id": 4, "name": "brand_positioning", "phase": "3", "mode": "build", "dependencies": [3]},
        {"node_id": 5, "name": "audience_segmentation", "phase": "5", "mode": "build", "dependencies": [3, 4]},
        {"node_id": 10, "name": "brand_health", "phase": "1s", "mode": "scale", "dependencies": [2]},
        {"node_id": 11, "name": "market_reval", "phase": "1s", "mode": "scale", "dependencies": [2]},
    ],
}


@pytest.fixture(autouse=True)
def _patch_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_file = tmp_path / "dependency-graph.yaml"
    graph_file.write_text(yaml.dump(_GRAPH), encoding="utf-8")
    import automedia.decision.dependency as dep_mod

    monkeypatch.setattr(dep_mod, "_GRAPH_PATH", graph_file)


# ===================================================================
# check()
# ===================================================================


class TestPreflightCheck:
    """check() returns warnings for missing prerequisites."""

    def test_returns_empty_when_all_phases_complete(self) -> None:
        from automedia.decision.preflight import check

        # All phase-0 and phase-1b nodes complete → moving to phase 2
        completed = {1, 2, 3}
        warnings = check("2", "build", completed)
        assert warnings == []

    def test_returns_warnings_when_nodes_missing(self) -> None:
        from automedia.decision.preflight import check

        # Node 3 (market_research, phase 1b) NOT completed → moving to phase 2
        completed = {1, 2}
        warnings = check("2", "build", completed)
        assert len(warnings) > 0
        assert any("market_research" in w for w in warnings)

    def test_handles_unknown_phase(self) -> None:
        from automedia.decision.preflight import check

        warnings = check("99", "build", set())
        assert len(warnings) == 1
        assert "Unknown phase" in warnings[0]

    def test_returns_empty_for_first_phase(self) -> None:
        from automedia.decision.preflight import check

        # Phase 0 has no prior phases
        warnings = check("0", "build", set())
        assert warnings == []

    def test_scale_mode_ignores_build_nodes(self) -> None:
        from automedia.decision.preflight import check

        # In scale mode, phase-1b (build) nodes are irrelevant
        completed = {1, 2, 10, 11}
        warnings = check("2", "scale", completed)
        # Should be empty — all scale prior nodes done
        assert warnings == []
