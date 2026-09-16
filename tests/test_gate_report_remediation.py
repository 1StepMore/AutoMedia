"""Regression tests for per-check remediation fields in the gate report.

Todo 8 (automedia-reinforcement): ``gate_report._build_row`` used to rebuild
each check dict down to ``{name, passed, detail}``, silently discarding the
remediation fields that ``gates._result._enrich_failing_checks`` had already
derived (``suggestion`` / ``threshold`` / ``actual_value`` / ``check_name``).

These tests build results through the PRODUCTION types (``build_gate_result``)
so the enrichment path is exercised end to end, then assert the fields survive
into the rendered report's check dicts.

NOTE: a later todo adds a Markdown "Fix" column to this module — keep its
additions in a separate class so the data-preservation tests below stay
isolated from the rendering tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from automedia.gates._result import build_gate_result
from automedia.pipelines.gate_engine import GateLogEntry
from automedia.pipelines.gate_report import render_gate_report


def _entry(
    gate_name: str,
    status: Literal["passed", "failed", "error"],
    error: str | None,
) -> GateLogEntry:
    """Build a GateLogEntry for the given status (validated as in gate_engine)."""
    return GateLogEntry(gate_name=gate_name, status=status, duration_s=1.0, error=error)


class TestFailingCheckRemediationPreserved:
    """Todo 8: remediation fields on failing checks reach the report's checks."""

    def test_json_row_failing_check_keeps_suggestion_and_threshold(self, tmp_path: Path) -> None:
        # Given: a real gate result whose failing check was enriched by the
        # production builder (not a hand-rolled dict bypassing enrichment).
        result = build_gate_result(
            [
                {"name": "human_likeness", "passed": True, "detail": "score 0.81"},
                {
                    "name": "banned_phrase",
                    "passed": False,
                    "detail": "found 'guaranteed'",
                },
            ],
            gate="G1",
            error="banned phrase found",
            expected_map={"banned_phrase": "No banned phrases"},
        )
        enriched = result["checks"][1]
        assert enriched["suggestion"]  # producer genuinely enriched the check

        # When: the in-memory result flows through the report writer.
        report = render_gate_report(
            str(tmp_path), [_entry("G1", "failed", "banned phrase found")], [result]
        )
        checks = report["gates"][0]["checks"]
        assert checks is not None
        failing = next(c for c in checks if c["name"] == "banned_phrase")

        # Then: the remediation fields survive into the JSON check dict.
        assert failing["suggestion"] == enriched["suggestion"]
        assert failing["suggestion"]
        assert failing["threshold"] == "No banned phrases"
        assert failing["actual_value"] == "found 'guaranteed'"

        # And the row stays JSON-serializable with those fields intact.
        encoded = json.loads(json.dumps(report["gates"]))
        encoded_failing = next(c for c in encoded[0]["checks"] if c["name"] == "banned_phrase")
        assert encoded_failing["suggestion"]
        assert encoded_failing["threshold"] == "No banned phrases"


class TestPassingCheckHasNoRemediation:
    """Todo 8 failure mode: passing checks gain no spurious fix content."""

    def test_passing_check_has_no_remediation_fields(self, tmp_path: Path) -> None:
        # Given: a real gate result whose checks all pass.
        result = build_gate_result(
            [{"name": "human_likeness", "passed": True, "detail": "score 0.81"}],
            gate="G1",
            error=None,
            expected_map={"human_likeness": "Human likeness above 0.60"},
        )

        # When: rendered through the report writer.
        report = render_gate_report(str(tmp_path), [_entry("G1", "passed", None)], [result])
        checks = report["gates"][0]["checks"]
        assert checks is not None
        passing = checks[0]

        # Then: no remediation keys are synthesized for a passing check.
        assert passing["passed"] is True
        assert "suggestion" not in passing
        assert "threshold" not in passing
        assert "actual_value" not in passing
