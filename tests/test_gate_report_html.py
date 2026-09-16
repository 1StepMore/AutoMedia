"""Tests for the self-contained HTML gate report (todo 10).

The writer now also emits ONE self-contained HTML document
(``gate-report-<ts>.html``) alongside the Markdown and JSON views.  These
tests pin the contract:

- the HTML carries the failing gate's name, its recorded reason, and the Fix
  text (same content as the Markdown/MCP views);
- it references NO external resource — no ``http(s)`` URL, no ``<script>``;
- every dynamic value is HTML-escaped (``<``/``&`` render as text, not markup).
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Literal, cast

from automedia.gates.failure_modes import FAILURE_MODES
from automedia.pipelines.gate_engine import GateLogEntry
from automedia.pipelines.gate_report import render_gate_report, write_gate_report


def _failure_mode_fixes(gate: str) -> list[str]:
    """Gate-level fixes from the knowledge base — an independent known-good source."""
    return cast("list[str]", FAILURE_MODES[gate]["fixes"])


def _entry(
    gate_name: str,
    status: Literal["passed", "failed", "error"],
    error: str | None = None,
) -> GateLogEntry:
    return GateLogEntry(gate_name=gate_name, status=status, duration_s=1.0, error=error)


def _write_html(tmp_path: Path, gates_log: list[GateLogEntry]) -> tuple[str, Path]:
    """Render + write a report, returning ``(html_text, html_path)``."""
    report = render_gate_report(str(tmp_path), gates_log)
    artifacts = write_gate_report(str(tmp_path), report)
    html_path = artifacts.html_path
    return html_path.read_text(encoding="utf-8"), html_path


class TestHtmlContent:
    """The HTML carries the same content plus the Fix column."""

    def test_contains_failing_gate_reason_and_fix(self, tmp_path: Path) -> None:
        reason = "human_likeness below threshold: 0.42 < 0.60"
        html_text, _ = _write_html(tmp_path, [_entry("G1", "failed", reason)])

        assert "G1" in html_text
        assert html.escape(reason) in html_text
        assert _failure_mode_fixes("G1")[0] in html_text

    def test_contains_passing_and_review_rows(self, tmp_path: Path) -> None:
        html_text, _ = _write_html(
            tmp_path,
            [
                _entry("CW", "passed"),
                _entry("V1", "error", "ffmpeg crashed"),
            ],
        )
        assert "CW" in html_text
        assert "review" in html_text
        assert "ffmpeg crashed" in html_text

    def test_check_suggestion_reaches_html(self, tmp_path: Path) -> None:
        """LIVE render: the per-check suggestion is the Fix content."""
        from automedia.gates._result import build_gate_result

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
        assert suggestion  # precondition: production builder produced remediation

        report = render_gate_report(
            str(tmp_path),
            [_entry("G1", "failed", "banned phrase found")],
            [result],
        )
        html_text = write_gate_report(str(tmp_path), report).html_path.read_text(encoding="utf-8")
        assert suggestion in html_text

    def test_empty_log_renders_well_formed_document(self, tmp_path: Path) -> None:
        html_text, _ = _write_html(tmp_path, [])
        assert html_text.lstrip().lower().startswith("<!doctype html>")
        assert "</html>" in html_text
        assert "no gate" in html_text.lower()


class TestHtmlSelfContained:
    """No external resource may be referenced (no http script/link)."""

    def test_no_external_http_references(self, tmp_path: Path) -> None:
        html_text, _ = _write_html(tmp_path, [_entry("G1", "failed", "tone drift")])
        assert "http://" not in html_text
        assert "https://" not in html_text

    def test_no_script_or_external_link_elements(self, tmp_path: Path) -> None:
        html_text, _ = _write_html(tmp_path, [_entry("G1", "failed", "tone drift")])
        lowered = html_text.lower()
        assert "<script" not in lowered
        assert "<link" not in lowered


class TestHtmlEscaping:
    """Dynamic values are escaped — markup in a reason renders as text."""

    def test_reason_markup_is_escaped(self, tmp_path: Path) -> None:
        malicious = "<script>alert(1)</script> & <b>bold</b>"
        html_text, _ = _write_html(tmp_path, [_entry("G1", "failed", malicious)])

        # The raw tags never appear; escaped entities do.
        assert "<script>alert(1)</script>" not in html_text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
        assert "&amp;" in html_text
        assert "&lt;b&gt;bold&lt;/b&gt;" in html_text


class TestWriteContract:
    """The writer returns a 3-field result with an .html artifact."""

    def test_returns_html_path_next_to_md_and_json(self, tmp_path: Path) -> None:
        report = render_gate_report(str(tmp_path), [_entry("CW", "passed")])
        artifacts = write_gate_report(str(tmp_path), report)

        assert artifacts.md_path.exists()
        assert artifacts.json_path.exists()
        assert artifacts.html_path.exists()
        assert artifacts.html_path.suffix == ".html"
        assert artifacts.html_path.parent == tmp_path / "05_review" / "gate-report"
        # One timestamped stem shared by all three views.
        assert artifacts.md_path.stem == artifacts.json_path.stem
        assert artifacts.html_path.stem == artifacts.json_path.stem
