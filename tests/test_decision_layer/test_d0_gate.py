"""Tests for D0Gate — Decision Layer Provenance Gate (Red Line 9).

Covers
------
1. Gate metadata (gate_name, failure_mode)
2. Force-provenance bypass
3. Missing .solution-state.yaml → RL9 violation
4. Valid solution state with all required nodes → compliant
5. Partial completion → RL9 violation with missing_nodes list
6. Empty completed_nodes → RL9 violation
7. Unknown decision_mode defaults to "build" behaviour
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from automedia.decision.gates.d0_gate import D0Gate, _find_solution_state

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fake required-node IDs standing in for the real 27-node build graph.
_FAKE_BUILD_NODES: set[int] = {1, 2, 3, 4, 5}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def d0() -> D0Gate:
    """Return a fresh D0Gate instance."""
    return D0Gate()


@pytest.fixture()
def fake_required_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``dependency.get_required_nodes_for_mode`` to return ``_FAKE_BUILD_NODES``."""
    import automedia.decision.dependency as dep

    monkeypatch.setattr(
        dep,
        "get_required_nodes_for_mode",
        lambda _mode: set(_FAKE_BUILD_NODES),
    )


@pytest.fixture()
def write_solution_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Factory fixture: write a ``.solution-state.yaml`` into *tmp_path* and
    redirect ``_find_solution_state`` to find it there.

    Returns a helper ``(completed_nodes) -> Path`` that writes the YAML and
    returns its path.
    """

    def _write(completed_nodes: list[int]) -> Path:
        state_file = tmp_path / ".solution-state.yaml"
        state_file.write_text(
            yaml.safe_dump({"completed_nodes": completed_nodes}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "automedia.decision.gates.d0_gate._find_solution_state",
            lambda _project_dir=None: str(state_file),
        )
        return state_file

    return _write


# ===========================================================================
# Test Cases
# ===========================================================================


class TestD0GateMetadata:
    """D0Gate exposes correct gate naming metadata."""

    def test_gate_name_is_d0(self, d0: D0Gate) -> None:
        assert d0.gate_name == "D0"

    def test_failure_mode_is_stop(self, d0: D0Gate) -> None:
        assert d0.failure_mode == "stop"

    def test_gate_name_is_readonly(self, d0: D0Gate) -> None:
        with pytest.raises(AttributeError):
            d0.gate_name = "D99"  # type: ignore[misc]

    def test_failure_mode_is_readonly(self, d0: D0Gate) -> None:
        with pytest.raises(AttributeError):
            d0.failure_mode = "retry"  # type: ignore[misc]


class TestD0GateForceProvenanceBypass:
    """D0Gate bypasses all checks when ``force_provenance=True``."""

    def test_force_provenance_returns_passed(self, d0: D0Gate) -> None:
        result = d0.execute({"force_provenance": True})
        assert result["passed"] is True

    def test_force_provenance_status_is_bypassed(self, d0: D0Gate) -> None:
        result = d0.execute({"force_provenance": True})
        assert result["status"] == "bypassed"

    def test_force_provenance_gate_key(self, d0: D0Gate) -> None:
        result = d0.execute({"force_provenance": True})
        assert result["gate"] == "D0"

    def test_force_provenance_detail_mentions_flag(self, d0: D0Gate) -> None:
        result = d0.execute({"force_provenance": True})
        assert "--force-provenance" in result["detail"]

    def test_force_provenance_skips_file_lookup(
        self,
        d0: D0Gate,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When force_provenance=True, _find_solution_state must NOT be called."""
        calls: list[Any] = []
        monkeypatch.setattr(
            "automedia.decision.gates.d0_gate._find_solution_state",
            lambda *a, **kw: (calls.append(1) or None),
        )
        d0.execute({"force_provenance": True})
        assert calls == [], "_find_solution_state was called despite force_provenance"


class TestD0GateMissingStateFile:
    """D0Gate fails with RL9 violation when no .solution-state.yaml exists."""

    def test_missing_state_returns_not_passed(self, d0: D0Gate) -> None:
        result = d0.execute({"project_dir": "/nonexistent"})
        assert result["passed"] is False

    def test_missing_state_status_is_rl9_violation(self, d0: D0Gate) -> None:
        result = d0.execute({"project_dir": "/nonexistent"})
        assert result["status"] == "rl9_violation"

    def test_missing_state_error_mentions_force_provenance(self, d0: D0Gate) -> None:
        result = d0.execute({"project_dir": "/nonexistent"})
        assert "--force-provenance" in result["error"]

    def test_missing_state_error_mentions_solution_state(self, d0: D0Gate) -> None:
        result = d0.execute({"project_dir": "/nonexistent"})
        assert ".solution-state.yaml" in result["error"]

    def test_missing_state_gate_key(self, d0: D0Gate) -> None:
        result = d0.execute({"project_dir": "/nonexistent"})
        assert result["gate"] == "D0"


class TestD0GateValidState:
    """D0Gate passes when all required nodes are completed."""

    def test_all_nodes_complete_returns_passed(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state(list(_FAKE_BUILD_NODES))
        result = d0.execute({"decision_mode": "build"})
        assert result["passed"] is True

    def test_all_nodes_complete_status_is_compliant(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state(list(_FAKE_BUILD_NODES))
        result = d0.execute({"decision_mode": "build"})
        assert result["status"] == "rl9_compliant"

    def test_all_nodes_complete_has_provenance_dict(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        state_path = write_solution_state(list(_FAKE_BUILD_NODES))
        result = d0.execute({"decision_mode": "build"})
        prov = result["provenance"]
        assert isinstance(prov, dict)
        assert prov["mode"] == "build"
        assert prov["required_nodes"] == len(_FAKE_BUILD_NODES)
        assert prov["completed_nodes"] == len(_FAKE_BUILD_NODES)
        assert prov["state_source"] == str(state_path)

    def test_all_nodes_complete_gate_key(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state(list(_FAKE_BUILD_NODES))
        result = d0.execute({"decision_mode": "build"})
        assert result["gate"] == "D0"

    def test_extra_completed_nodes_still_passes(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        """Having more completed nodes than required should still pass."""
        write_solution_state(list(_FAKE_BUILD_NODES) + [99, 100])
        result = d0.execute({"decision_mode": "build"})
        assert result["passed"] is True
        assert result["provenance"]["completed_nodes"] == len(_FAKE_BUILD_NODES) + 2


class TestD0GateMissingRequiredNodes:
    """D0Gate fails when some required nodes are not completed."""

    def test_partial_completion_returns_not_passed(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        # Only complete nodes 1 and 2; 3, 4, 5 are missing
        write_solution_state([1, 2])
        result = d0.execute({"decision_mode": "build"})
        assert result["passed"] is False

    def test_partial_completion_status_is_rl9_violation(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state([1, 2])
        result = d0.execute({"decision_mode": "build"})
        assert result["status"] == "rl9_violation"

    def test_partial_completion_lists_missing_nodes(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state([1, 2])
        result = d0.execute({"decision_mode": "build"})
        missing = result["missing_nodes"]
        assert sorted(missing) == [3, 4, 5]

    def test_partial_completion_error_mentions_count(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state([1, 2])
        result = d0.execute({"decision_mode": "build"})
        assert "3 required node" in result["error"]

    def test_partial_completion_error_mentions_force_provenance(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state([1, 2])
        result = d0.execute({"decision_mode": "build"})
        assert "--force-provenance" in result["error"]

    def test_empty_completed_nodes(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        """An empty completed_nodes list means nothing is done."""
        write_solution_state([])
        result = d0.execute({"decision_mode": "build"})
        assert result["passed"] is False
        assert result["status"] == "rl9_violation"
        assert sorted(result["missing_nodes"]) == sorted(list(_FAKE_BUILD_NODES))


class TestD0GateDefaultMode:
    """D0Gate defaults to 'build' when decision_mode is absent."""

    def test_default_mode_uses_build(
        self,
        d0: D0Gate,
        fake_required_nodes: None,
        write_solution_state,
    ) -> None:
        write_solution_state(list(_FAKE_BUILD_NODES))
        # No decision_mode key → should default to "build"
        result = d0.execute({})
        assert result["passed"] is True
        assert result["provenance"]["mode"] == "build"


class TestD0GateFindSolutionState:
    """Unit tests for the ``_find_solution_state`` helper."""

    def test_returns_none_when_no_file_exists(self, tmp_path: Path) -> None:
        result = _find_solution_state(str(tmp_path))
        assert result is None

    def test_finds_file_in_project_dir(self, tmp_path: Path) -> None:
        state = tmp_path / ".solution-state.yaml"
        state.write_text("completed_nodes: []", encoding="utf-8")
        result = _find_solution_state(str(tmp_path))
        assert result == str(state)

    def test_returns_none_for_none_project_dir(self) -> None:
        """When project_dir is None, only CWD and home are checked."""
        # We can't easily control those, but calling with None must not raise
        result = _find_solution_state(None)
        # It's either a path string or None — just verify no exception
        assert result is None or isinstance(result, str)
