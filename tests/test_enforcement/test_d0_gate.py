"""RED tests for D0 Gate — Decision Layer Provenance enforcement.

Scenarios
---------
1. ``.solution-state.yaml`` missing → D0Gate returns fail with ``status="rl9_violation"``
2. Required nodes missing → fail with missing node list
3. All required nodes completed → success with provenance
4. ``--force-provenance`` bypass → success with ``status="bypassed"``
5. Build mode requires build nodes
6. Scale mode requires scale nodes
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from automedia.decision import dependency
from automedia.decision.gates.d0_gate import D0Gate


@pytest.fixture
def empty_state_dir(tmp_path: Path) -> Path:
    """A tmp_path with no .solution-state.yaml."""
    return tmp_path


@pytest.fixture
def build_state_dir(tmp_path: Path) -> Path:
    """A tmp_path with a .solution-state.yaml containing all build nodes."""
    required = dependency.get_required_nodes_for_mode("build")
    state = {
        "mode": "build",
        "completed_nodes": sorted(required),
        "artifacts": {},
    }
    state_path = tmp_path / ".solution-state.yaml"
    with open(state_path, "w", encoding="utf-8") as fh:
        yaml.dump(state, fh)
    return tmp_path


@pytest.fixture
def partial_state_dir(tmp_path: Path) -> Path:
    """A tmp_path with only some nodes completed."""
    state = {
        "mode": "build",
        "completed_nodes": [1, 2, 3],
        "artifacts": {},
    }
    state_path = tmp_path / ".solution-state.yaml"
    with open(state_path, "w", encoding="utf-8") as fh:
        yaml.dump(state, fh)
    return tmp_path


class TestD0GateMissingState:
    """No .solution-state.yaml found."""

    def test_missing_state_file_fails(self, empty_state_dir: Path) -> None:
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(empty_state_dir),
            }
        )
        assert result["passed"] is False
        assert result["status"] == "rl9_violation"

    def test_missing_state_has_error_message(self, empty_state_dir: Path) -> None:
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(empty_state_dir),
            }
        )
        assert "RL9" in result.get("error", "")


class TestD0GatePartialState:
    """Some required nodes are missing."""

    def test_partial_state_fails(self, partial_state_dir: Path) -> None:
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(partial_state_dir),
            }
        )
        assert result["passed"] is False
        assert result["status"] == "rl9_violation"

    def test_partial_state_lists_missing_nodes(self, partial_state_dir: Path) -> None:
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(partial_state_dir),
            }
        )
        assert "missing_nodes" in result
        assert len(result["missing_nodes"]) > 0


class TestD0GateCompleteState:
    """All required nodes completed."""

    def test_complete_state_passes(self, build_state_dir: Path) -> None:
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(build_state_dir),
            }
        )
        assert result["passed"] is True
        assert result["status"] == "rl9_compliant"

    def test_complete_state_has_provenance(self, build_state_dir: Path) -> None:
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(build_state_dir),
            }
        )
        assert "provenance" in result
        assert result["provenance"]["mode"] == "build"


class TestD0GateForceProvenance:
    """--force-provenance bypasses the check."""

    def test_force_provenance_skips_check(self, empty_state_dir: Path) -> None:
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(empty_state_dir),
                "force_provenance": True,
            }
        )
        assert result["passed"] is True
        assert result["status"] == "bypassed"


class TestD0GateModeAwareness:
    """Build and Scale modes require different node sets."""

    def test_build_mode_requires_build_nodes(self, tmp_path: Path) -> None:
        state = {"mode": "build", "completed_nodes": [1, 2, 3]}
        sp = tmp_path / ".solution-state.yaml"
        with open(sp, "w", encoding="utf-8") as fh:
            yaml.dump(state, fh)
        gate = D0Gate()
        result = gate.execute({"mode": "build", "project_dir": str(tmp_path)})
        assert result["passed"] is False

    def test_scale_mode_requires_scale_nodes(self, tmp_path: Path) -> None:
        state = {"mode": "scale", "completed_nodes": [1, 2, 3]}
        sp = tmp_path / ".solution-state.yaml"
        with open(sp, "w", encoding="utf-8") as fh:
            yaml.dump(state, fh)
        gate = D0Gate()
        result = gate.execute({"mode": "scale", "project_dir": str(tmp_path)})
        assert result["passed"] is False
