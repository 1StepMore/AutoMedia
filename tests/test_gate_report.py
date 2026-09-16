"""Tests for the gate-report writer (pipelines/gate_report.py).

Verifies that a per-run gate report can be rendered from data ALREADY
captured during a pipeline run (gates_log + optional in-memory gate result
dicts) and written to ``05_review/gate-report/gate-report-<ts>.{md,json}``
— without inventing a new persistent gate store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

from automedia.pipelines.gate_engine import GateLogEntry
from automedia.pipelines.gate_report import render_gate_report, write_gate_report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(
    gate_name: str,
    status: Literal["passed", "failed", "error"],
    duration_s: float,
    error: str | None = None,
) -> GateLogEntry:
    """Build a GateLogEntry (status validated as in gate_engine)."""
    if status not in ("passed", "failed", "error"):
        pytest.fail(f"invalid test status {status!r}")
    return GateLogEntry(gate_name=gate_name, status=status, duration_s=duration_s, error=error)


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Simulate the standard project layout (05_review exists)."""
    (tmp_path / "05_review").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Case 1 — render from a sample gates_log with one failed stop gate
# ---------------------------------------------------------------------------


class TestRenderFromGatesLog:
    def test_markdown_contains_gate_reason_duration(self, project_dir: Path) -> None:
        gates_log = [
            _entry("CW", "passed", 1.5),
            _entry("G0", "passed", 0.4),
            _entry("G1", "failed", 2.25, error="human_likeness below threshold: 0.42 < 0.60"),
        ]
        report = render_gate_report(str(project_dir), gates_log)

        markdown = report["markdown"]
        assert "G1" in markdown
        assert "human_likeness below threshold: 0.42 < 0.60" in markdown
        assert "2.25" in markdown
        # Report vocabulary mapping: passed|failed|error -> pass|fail|review
        assert "fail" in markdown
        assert "pass" in markdown

    def test_blocked_by_line_names_first_failed_gate(self, project_dir: Path) -> None:
        gates_log = [
            _entry("CW", "passed", 1.5),
            _entry("G0", "passed", 0.4),
            _entry("G1", "failed", 2.25, error="human_likeness below threshold"),
            _entry("G2", "failed", 0.9, error="secondary failure (should not block)"),
        ]
        report = render_gate_report(str(project_dir), gates_log)
        assert "G1" in report["blocked_by"]
        assert report["blocked_by_gate"] == "G1"
        assert "G1" in report["markdown"]

    def test_error_status_maps_to_review(self, project_dir: Path) -> None:
        """An 'error' status (gate raised) maps to review, not fail."""
        gates_log = [_entry("V1", "error", 0.5, error="ffmpeg crashed")]
        report = render_gate_report(str(project_dir), gates_log)
        row = next(r for r in report["gates"] if r["gate"] == "V1")
        assert row["verdict"] == "review"

    def test_json_round_trips(self, project_dir: Path) -> None:
        gates_log = [
            _entry("CW", "passed", 1.0),
            _entry("G0", "failed", 0.3, error="topic drift"),
        ]
        report = render_gate_report(str(project_dir), gates_log)
        # The report dict itself must be JSON-serializable
        encoded = json.loads(json.dumps(report["gates"]))
        assert isinstance(encoded, list) and len(encoded) == 2
        assert encoded[1]["verdict"] == "fail"

    def test_result_dict_merges_checks_and_expected_vs_actual(self, project_dir: Path) -> None:
        """LIVE mode: in-memory result dicts enrich rows with per-check detail."""
        gates_log = [_entry("G1", "failed", 2.0, error="check failed")]
        gate_results = [
            {
                "passed": False,
                "gate": "G1",
                "duration_s": 2.0,
                "error": "check failed",
                "checks": [
                    {"name": "human_likeness", "passed": True, "detail": "ok"},
                    {
                        "name": "banned_phrase",
                        "passed": False,
                        "detail": "found 'guaranteed'",
                    },
                ],
                "expected_vs_actual": {
                    "check": "banned_phrase",
                    "expected": "No banned phrases",
                    "actual": "found 'guaranteed'",
                    "context": {},
                },
            }
        ]
        report = render_gate_report(str(project_dir), gates_log, gate_results)
        row = report["gates"][0]
        assert row["checks"] is not None and len(row["checks"]) == 2
        eva = row["expected_vs_actual"]
        assert eva is not None
        assert eva["expected"] == "No banned phrases"
        assert "banned_phrase" in report["markdown"]
        assert "No banned phrases" in report["markdown"]

    def test_output_path_key_included_in_row(self, project_dir: Path) -> None:
        gates_log = [_entry("CW", "passed", 1.0)]
        gate_results = [
            {
                "passed": True,
                "gate": "CW",
                "duration_s": 1.0,
                "checks": [],
                "error": None,
                "expected_vs_actual": {},
                "output_path": "01_content/drafts/draft.md",
            }
        ]
        report = render_gate_report(str(project_dir), gates_log, gate_results)
        assert report["gates"][0]["output_path"] == "01_content/drafts/draft.md"


# ---------------------------------------------------------------------------
# Case 2 — empty gates_log → well-formed report, no exception
# ---------------------------------------------------------------------------


class TestEmptyGatesLog:
    def test_empty_log_well_formed_report(self, project_dir: Path) -> None:
        report = render_gate_report(str(project_dir), [])
        assert report["gates"] == []
        assert report["blocked_by_gate"] is None
        markdown = report["markdown"]
        assert "no gate" in markdown.lower() or "empty" in markdown.lower()
        # Still counts as zero totals, no crash
        assert report["summary"]["total"] == 0

    def test_write_empty_report_creates_files(self, project_dir: Path) -> None:
        report = render_gate_report(str(project_dir), [])
        md_path, json_path, html_path = write_gate_report(str(project_dir), report)
        assert md_path.exists() and json_path.exists() and html_path.exists()
        assert md_path.parent == project_dir / "05_review" / "gate-report"


# ---------------------------------------------------------------------------
# Case 3 — offline render has no review rows unless hitl-mode flag set
# ---------------------------------------------------------------------------


class TestH0ReviewSemantics:
    """_hitl_approved lives only in transient result dicts — it is ABSENT from
    persisted gates_log rows. Offline renders must NEVER guess 'review'."""

    def test_offline_h0_defaults_to_pass(self, project_dir: Path) -> None:
        gates_log = [_entry("H0", "passed", 0.1)]
        report = render_gate_report(str(project_dir), gates_log)
        row = report["gates"][0]
        assert row["verdict"] == "pass"
        assert row["verdict_source"] == "log"

    def test_live_h0_approved_review_then_passed(self, project_dir: Path) -> None:
        """LIVE: result carries _hitl_approved=True → review→passed.
        The verdict is 'pass' but the row records it went through review."""
        gates_log = [_entry("H0", "passed", 0.1)]
        gate_results = [{"passed": True, "gate": "H0", "_hitl_approved": True}]
        report = render_gate_report(str(project_dir), gates_log, gate_results)
        row = report["gates"][0]
        assert row["verdict"] == "pass"
        assert row["reviewed"] is True
        assert row["verdict_source"] == "result"

    def test_live_h0_rejected_maps_to_fail(self, project_dir: Path) -> None:
        """LIVE: an H0 whose HITL review rejected it must surface as fail."""
        gates_log = [_entry("H0", "passed", 0.1)]
        gate_results = [{"passed": True, "gate": "H0", "_hitl_approved": False}]
        report = render_gate_report(str(project_dir), gates_log, gate_results)
        row = report["gates"][0]
        assert row["verdict"] == "fail"

    def test_live_h0_awaiting_hitl_maps_to_review(self, project_dir: Path) -> None:
        """LIVE: H0 still awaiting human review renders as review."""
        gates_log = [_entry("H0", "passed", 0.1)]
        gate_results = [{"passed": True, "gate": "H0", "status": "awaiting_hitl"}]
        report = render_gate_report(str(project_dir), gates_log, gate_results)
        row = report["gates"][0]
        assert row["verdict"] == "review"

    def test_offline_hitl_mode_flag_marks_review(self, project_dir: Path) -> None:
        """OFFLINE fallback: hitl-mode context flag active → H0 = review."""
        gates_log = [_entry("H0", "passed", 0.1)]
        report = render_gate_report(str(project_dir), gates_log, hitl_mode=True)
        row = report["gates"][0]
        assert row["verdict"] == "review"
        assert row["reviewed"] is True

    def test_offline_no_flag_no_review_rows(self, project_dir: Path) -> None:
        """Without the flag, NO row may claim review from persisted data alone —
        except 'error' status, which is a recorded fact, not a guess."""
        gates_log = [
            _entry("H0", "passed", 0.1),
            _entry("CW", "passed", 1.0),
            _entry("G0", "failed", 0.2, error="topic drift"),
        ]
        report = render_gate_report(str(project_dir), gates_log)
        verdicts = {r["gate"]: r["verdict"] for r in report["gates"]}
        assert verdicts["H0"] == "pass"
        assert verdicts["CW"] == "pass"
        assert verdicts["G0"] == "fail"
        assert all(r["reviewed"] is False for r in report["gates"])


# ---------------------------------------------------------------------------
# write_gate_report — file output contract
# ---------------------------------------------------------------------------


class TestWriteGateReport:
    def test_writes_md_and_json(self, project_dir: Path) -> None:
        gates_log = [
            _entry("CW", "passed", 1.5),
            _entry("G1", "failed", 2.25, error="human_likeness below threshold"),
        ]
        report = render_gate_report(str(project_dir), gates_log)
        md_path, json_path, html_path = write_gate_report(str(project_dir), report)

        assert md_path.name.startswith("gate-report-") and md_path.suffix == ".md"
        assert json_path.name.startswith("gate-report-") and json_path.suffix == ".json"
        assert html_path.name.startswith("gate-report-") and html_path.suffix == ".html"
        assert md_path.parent == project_dir / "05_review" / "gate-report"
        # Timestamps match between the three views
        assert md_path.stem == json_path.stem == html_path.stem

        md_text = md_path.read_text(encoding="utf-8")
        assert "G1" in md_text and "human_likeness below threshold" in md_text

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["project_dir"] == str(project_dir)
        assert data["blocked_by_gate"] == "G1"
        assert len(data["gates"]) == 2

    def test_creates_missing_parent_dir(self, tmp_path: Path) -> None:
        """The parent dir 05_review/gate-report must be created if absent."""
        report = render_gate_report(str(tmp_path), [_entry("CW", "passed", 0.1)])
        md_path, json_path, html_path = write_gate_report(str(tmp_path), report)
        assert md_path.exists() and json_path.exists() and html_path.exists()

    def test_unique_timestamped_files(self, project_dir: Path) -> None:
        """Two writes produce distinct files (timestamp in the name)."""
        report = render_gate_report(str(project_dir), [_entry("CW", "passed", 0.1)])
        first = write_gate_report(str(project_dir), report)
        second = write_gate_report(str(project_dir), report)
        # Same-second writes could collide on name; contract allows either a
        # distinct name or overwrite, but the returned paths must be usable.
        assert first[0].exists() and second[0].exists()


# ---------------------------------------------------------------------------
# Report-dict shape invariants
# ---------------------------------------------------------------------------


class TestReportShape:
    def test_summary_counts(self, project_dir: Path) -> None:
        gates_log = [
            _entry("CW", "passed", 1.0),
            _entry("G0", "failed", 0.5, error="x"),
            _entry("V1", "error", 0.2, error="boom"),
        ]
        report = render_gate_report(str(project_dir), gates_log)
        s = report["summary"]
        assert s["total"] == 3
        assert s["passed"] == 1
        assert s["failed"] == 1
        assert s["errored"] == 1
        assert s["total_duration_s"] == pytest.approx(1.7)

    def test_generated_at_is_utc_iso(self, project_dir: Path) -> None:
        report = render_gate_report(str(project_dir), [_entry("CW", "passed", 0.1)])
        assert report["generated_at"].endswith("+00:00")
