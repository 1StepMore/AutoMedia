"""D0 Gate — Decision Layer Provenance Gate.

Red Line 9 enforcement: verifies that the Decision Layer has completed
all required nodes before allowing the Production Layer pipeline to run.

Inherits from ``BaseGate`` and is inserted at the front of the gate list
in ``run_full_pipeline()``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from automedia.decision import dependency
from automedia.gates.base import BaseGate


def _find_solution_state(project_dir: str | None = None) -> str | None:
    """Locate ``.solution-state.yaml``, searching CWD first, then *project_dir*."""
    for candidate in [
        Path.cwd() / ".solution-state.yaml",
        Path(project_dir) / ".solution-state.yaml" if project_dir else None,
        Path.home() / ".automedia" / ".solution-state.yaml",
    ]:
        if candidate and candidate.is_file():
            return str(candidate)
    return None


def _load_solution_state(state_path: str) -> dict[str, Any]:
    """Load and parse ``.solution-state.yaml``."""
    with open(state_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


class D0Gate(BaseGate):
    """Decision Layer Provenance Gate — validates Decision Layer completion.

    ``gate_context`` expected keys:
        - ``mode``: ``"build"`` or ``"scale"`` (from Diagnostic Agent)
        - ``project_dir``: project directory path (optional)
        - ``force_provenance``: bool — skip check if True

    On failure the gate returns ``{"passed": False, "status": "rl9_violation"}``.
    """

    _gate_name = "D0"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        """Check Decision Layer state and return pass/fail with provenance."""
        mode = gate_context.get("mode", "build")
        project_dir = gate_context.get("project_dir")
        force_provenance = gate_context.get("force_provenance", False)

        # Allow bypass
        if force_provenance:
            return {
                "passed": True,
                "gate": self.gate_name,
                "status": "bypassed",
                "detail": "D0 Gate bypassed via --force-provenance",
            }

        # Find and load solution state
        state_path = _find_solution_state(project_dir)

        if state_path is None:
            return {
                "passed": False,
                "gate": self.gate_name,
                "status": "rl9_violation",
                "error": (
                    "RL9 violation: .solution-state.yaml not found. "
                    "Run Decision Layer agents first, or use --force-provenance "
                    "--confirm-bypass-rl9 to skip."
                ),
            }

        state = _load_solution_state(state_path)
        completed: set[int] = set(state.get("completed_nodes", []))
        required = dependency.get_required_nodes_for_mode(mode)
        missing = [nid for nid in required if nid not in completed]

        if missing:
            node_names = []
            for nid in missing:
                node = dependency.get_node(nid)
                node_names.append(node["name"] if node else f"node_{nid}")
            return {
                "passed": False,
                "gate": self.gate_name,
                "status": "rl9_violation",
                "error": (
                    f"RL9 violation: {len(missing)} required node(s) not completed "
                    f"for mode '{mode}': {', '.join(node_names)}. "
                    "Complete all decision nodes or use --force-provenance."
                ),
                "missing_nodes": missing,
            }

        # All required nodes complete — inject provenance into context
        return {
            "passed": True,
            "gate": self.gate_name,
            "status": "rl9_compliant",
            "detail": f"All {len(required)} required nodes completed for mode '{mode}'",
            "provenance": {
                "mode": mode,
                "completed_nodes": len(completed),
                "required_nodes": len(required),
                "state_source": state_path,
            },
        }
