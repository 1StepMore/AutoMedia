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
from typing import Literal, cast

from automedia.gates._result import build_gate_result
from automedia.gates.failure_modes import FAILURE_MODES
from automedia.pipelines.gate_engine import GateLogEntry
from automedia.pipelines.gate_report import render_gate_report


def _failure_mode_fixes(gate: str) -> list[str]:
    """Gate-level fixes from the knowledge base — an independent known-good source."""
    return cast("list[str]", FAILURE_MODES[gate]["fixes"])


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


class TestMarkdownFixColumn:
    """Todo 9: the rendered Markdown gains a "Fix" (怎么改) column sourced from
    the check ``suggestion``.  A failed gate with no per-check suggestion falls
    back to the first gate-level fix in :data:`FAILURE_MODES`; gates absent from
    the knowledge base render no invented text.
    """

    @staticmethod
    def _cells(line: str) -> list[str]:
        """Split one Markdown table row into its stripped cell values."""
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    def test_markdown_fix_cell_shows_check_suggestion(self, tmp_path: Path) -> None:
        # Given: a failed gate whose failing check the production builder enriched
        # with a suggestion (the same data path the report consumes live).
        result = build_gate_result(
            [
                {"name": "human_likeness", "passed": True, "detail": "score 0.81"},
                {"name": "banned_phrase", "passed": False, "detail": "found 'guaranteed'"},
            ],
            gate="G1",
            error="banned phrase found",
            expected_map={"banned_phrase": "No banned phrases"},
        )
        suggestion = result["checks"][1]["suggestion"]
        assert suggestion  # pre-condition: the builder produced remediation text

        # When: the report renders the in-memory result to Markdown.
        report = render_gate_report(
            str(tmp_path), [_entry("G1", "failed", "banned phrase found")], [result]
        )
        md = report["markdown"]

        # Then: the per-gate Fix cell carries the failing check's suggestion...
        gate_line = next(line for line in md.splitlines() if line.startswith("| G1 |"))
        assert self._cells(gate_line)[-1] == suggestion

        # ...and the per-check detail Fix cell carries the same suggestion.
        check_line = next(line for line in md.splitlines() if line.startswith("| banned_phrase |"))
        assert self._cells(check_line)[-1] == suggestion

    def test_markdown_fix_falls_back_to_failure_modes_when_no_suggestion(
        self, tmp_path: Path
    ) -> None:
        # Given: an offline render (persisted rows only) — no per-check detail,
        # so no per-check suggestion exists for the failed gate.
        expected_fix = _failure_mode_fixes("G1")[0]
        assert expected_fix

        # When: a failed G1 is rendered without any in-memory gate result.
        report = render_gate_report(str(tmp_path), [_entry("G1", "failed", "banned phrase found")])

        # Then: the gate-level FAILURE_MODES fix is the Fix cell.
        gate_line = next(
            line for line in report["markdown"].splitlines() if line.startswith("| G1 |")
        )
        assert self._cells(gate_line)[-1] == expected_fix

    def test_markdown_fix_falls_back_when_checks_lack_suggestion(self, tmp_path: Path) -> None:
        # Given: a live result whose failing check carries NO suggestion.
        result = {
            "gate": "G1",
            "checks": [{"name": "human_likeness", "passed": False, "detail": "score 0.42"}],
        }
        expected_fix = _failure_mode_fixes("G1")[0]
        assert expected_fix

        # When: rendered.
        report = render_gate_report(
            str(tmp_path), [_entry("G1", "failed", "human_likeness below threshold")], [result]
        )

        # Then: the fallback fix fills the gate's Fix cell.
        gate_line = next(
            line for line in report["markdown"].splitlines() if line.startswith("| G1 |")
        )
        assert self._cells(gate_line)[-1] == expected_fix

    def test_markdown_fix_absent_for_all_pass_run(self, tmp_path: Path) -> None:
        # Given: a passing gate with only passing checks.
        result = build_gate_result(
            [{"name": "human_likeness", "passed": True, "detail": "score 0.81"}],
            gate="G1",
            error=None,
            expected_map={"human_likeness": "Human likeness above 0.60"},
        )

        # When: rendered.
        report = render_gate_report(str(tmp_path), [_entry("G1", "passed", None)], [result])
        md = report["markdown"]

        # Then: the Fix columns exist but every cell is empty...
        gate_header = next(line for line in md.splitlines() if line.startswith("| Gate |"))
        assert self._cells(gate_header)[-1] == "Fix"
        gate_line = next(line for line in md.splitlines() if line.startswith("| G1 |"))
        assert self._cells(gate_line)[-1] == ""

        check_header = next(line for line in md.splitlines() if line.startswith("| Check |"))
        assert self._cells(check_header)[-1] == "Fix"
        check_line = next(line for line in md.splitlines() if line.startswith("| human_likeness |"))
        assert self._cells(check_line)[-1] == ""

        # ...and no gate-level remediation text leaked into the report.
        for fix in _failure_mode_fixes("G1"):
            assert fix not in md

    def test_markdown_fix_graceful_when_gate_not_in_failure_modes(self, tmp_path: Path) -> None:
        # Given: a failed gate the knowledge base does not know about.
        # When/Then: rendering does not crash and invents no remediation text.
        report = render_gate_report(
            str(tmp_path), [_entry("ZZ9", "failed", "some unknown failure")]
        )
        md = report["markdown"]
        gate_line = next(line for line in md.splitlines() if line.startswith("| ZZ9 |"))
        assert self._cells(gate_line)[-1] == ""
        assert "some unknown failure" in md  # the recorded reason is still surfaced
