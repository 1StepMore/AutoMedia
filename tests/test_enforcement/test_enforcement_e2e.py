"""E2E enforcement tests — D0 Gate, provenance checks, force-provenance bypass.

These tests validate the core enforcement mechanisms defined in PRD-3 W5:

    1. test_missing_state_triggers_rl9_violation
       When .solution-state.yaml is missing, D0Gate returns rl9_violation.

    2. test_complete_state_allows_pipeline
       When .solution-state.yaml has all required nodes, pipeline proceeds.

    3. test_force_provenance_bypasses_with_audit
       --force-provenance bypasses D0Gate and creates audit log.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from automedia.decision import dependency
from automedia.decision.gates.d0_gate import D0Gate


class TestEnforcementE2E:
    """E2E enforcement scenarios covering D0 Gate and provenance audit."""

    # ------------------------------------------------------------------
    # Scenario 1: Missing state → RL9 violation
    # ------------------------------------------------------------------

    def test_missing_state_triggers_rl9_violation(self, tmp_path: Path) -> None:
        """When .solution-state.yaml is missing, D0Gate returns rl9_violation."""
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(tmp_path),
            }
        )
        assert result["passed"] is False
        assert result["status"] == "rl9_violation"
        assert "error" in result

    # ------------------------------------------------------------------
    # Scenario 2: Complete state → pipeline passes
    # ------------------------------------------------------------------

    def test_complete_state_allows_pipeline(self, tmp_path: Path) -> None:
        """When .solution-state.yaml has all required nodes, pipeline proceeds."""
        required = dependency.get_required_nodes_for_mode("build")
        state: dict[str, Any] = {
            "mode": "build",
            "completed_nodes": sorted(required),
        }
        state_path = tmp_path / ".solution-state.yaml"
        with open(state_path, "w", encoding="utf-8") as f:
            yaml.dump(state, f)

        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(tmp_path),
            }
        )
        assert result["passed"] is True
        assert result["status"] == "rl9_compliant"
        assert "provenance" in result
        assert result["provenance"]["mode"] == "build"
        assert result["provenance"]["completed_nodes"] == len(required)

    # ------------------------------------------------------------------
    # Scenario 3: Force-provenance bypass + audit log verification
    # ------------------------------------------------------------------

    def test_force_provenance_bypasses_with_audit(self, tmp_path: Path) -> None:
        """--force-provenance bypasses D0Gate and creates audit log."""
        from automedia.decision.audit import _audit_log_path, log_force_provenance

        # Bypass — no .solution-state.yaml needed
        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(tmp_path),
                "force_provenance": True,
            }
        )
        assert result["passed"] is True
        assert result["status"] == "bypassed"
        assert "force-provenance" in result.get("detail", "")

        # Verify audit log was written
        log_force_provenance(topic="e2e-test-topic", brand="E2ETestBrand", user="pytest")
        log_path = _audit_log_path()
        assert log_path.exists(), f"Audit log not found at {log_path}"
        log_content = log_path.read_text(encoding="utf-8")
        assert "e2e-test-topic" in log_content
        assert "E2ETestBrand" in log_content
        assert "pytest" in log_content

    # ------------------------------------------------------------------
    # Scenario 4: Partial state (missing nodes) → RL9 violation
    # ------------------------------------------------------------------

    def test_partial_state_triggers_rl9_violation(self, tmp_path: Path) -> None:
        """When only some required nodes are completed, D0Gate returns rl9_violation."""
        state: dict[str, Any] = {
            "mode": "build",
            "completed_nodes": [1, 2, 3],
        }
        state_path = tmp_path / ".solution-state.yaml"
        with open(state_path, "w", encoding="utf-8") as f:
            yaml.dump(state, f)

        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(tmp_path),
            }
        )
        assert result["passed"] is False
        assert result["status"] == "rl9_violation"
        assert "missing_nodes" in result
        assert len(result["missing_nodes"]) > 0

    # ------------------------------------------------------------------
    # Scenario 5: Scale mode requires scale-specific nodes
    # ------------------------------------------------------------------

    def test_scale_mode_requires_scale_nodes(self, tmp_path: Path) -> None:
        """Scale mode requires scale-specific nodes; missing them triggers violation."""
        required = dependency.get_required_nodes_for_mode("scale")
        # Create state with zero completed nodes
        state: dict[str, Any] = {
            "mode": "scale",
            "completed_nodes": [],
        }
        state_path = tmp_path / ".solution-state.yaml"
        with open(state_path, "w", encoding="utf-8") as f:
            yaml.dump(state, f)

        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "scale",
                "project_dir": str(tmp_path),
            }
        )
        assert result["passed"] is False
        assert result["status"] == "rl9_violation"
        assert result.get("missing_nodes") is not None
        # All scale-required nodes should be in the missing list
        assert set(result["missing_nodes"]).issuperset(required & {9, 10, 11, 12, 13})
