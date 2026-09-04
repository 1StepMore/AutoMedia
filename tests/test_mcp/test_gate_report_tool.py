"""Tests for the ``get_gate_report`` MCP tool (productization-roadmap todo 6).

Contract: the tool is registered on ``create_server()`` and returns the
latest ``05_review/gate-report/gate-report-*.json`` payload for a project,
or a structured error.  Unknown project_id and report-less projects →
NOT_FOUND.  A base_dir outside the (fail-closed) mcp_allowlist.yaml →
ALLOWLIST_DENIED.  Zero production data — reports are seeded through the
real writer, ``write_gate_report``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from automedia.mcp.allowlist import _reset_allowlist_cache
from automedia.pipelines.gate_engine import GateLogEntry
from automedia.pipelines.gate_report import render_gate_report, write_gate_report


@pytest.fixture(autouse=True)
def _allowlist(tmp_path: Path) -> None:
    """Reset the allowlist cache and point it at tmp_path for the test."""
    _reset_allowlist_cache()
    import automedia.mcp.server as _server_mod

    _server_mod._cached_allowlist = [str(tmp_path.resolve())]
    yield
    _reset_allowlist_cache()


def _seed_project_with_report(
    tmp_path: Path,
    project_id: str = "report-proj-001",
    *,
    project_id_override: str | None = None,
) -> dict[str, Any]:
    """Create a project dir with an info file and one written gate report."""
    slug = "test-topic"
    project_dir = tmp_path / f"20260707_{slug}"
    project_dir.mkdir(parents=True, exist_ok=True)

    info = {
        "project_id": project_id_override or project_id,
        "topic": "Test Topic",
        "brand": "TestBrand",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

    gates_log = [
        GateLogEntry(gate_name="CW", status="passed", duration_s=1.0),
        GateLogEntry(gate_name="G1", status="failed", duration_s=0.5, error="tone drift"),
    ]
    report = render_gate_report(str(project_dir), gates_log)
    write_gate_report(str(project_dir), report)

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id_override or project_id,
    }


# =========================================================================
# Tests
# =========================================================================


class TestGetGateReport:
    """get_gate_report returns the latest gate-report JSON for a project."""

    def test_returns_report(self, tmp_path: Path) -> None:
        """Seeded project → success payload carrying the report content."""
        from automedia.mcp.tools.pipeline import get_gate_report

        proj = _seed_project_with_report(tmp_path)
        result = get_gate_report(
            project_id=proj["project_id"],  # type: ignore[arg-type]
            base_dir=proj["base_dir"],
        )

        assert result["success"] is True, result
        assert result["project_id"] == proj["project_id"]
        assert result["report_file"].startswith("gate-report-")
        assert result["report_file"].endswith(".json")
        report = result["report"]
        assert report["project_dir"] == proj["project_dir"]
        assert report["blocked_by_gate"] == "G1"
        assert report["summary"]["failed"] == 1
        by_gate = {row["gate"]: row for row in report["gates"]}
        assert by_gate["G1"]["verdict"] == "fail"
        assert by_gate["G1"]["error"] == "tone drift"
        assert "markdown" not in report  # writer excludes the md view from JSON

    def test_latest_picks_newest_report(self, tmp_path: Path) -> None:
        """Two written reports → the newest one (by filename) is returned."""
        from automedia.mcp.tools.pipeline import get_gate_report

        proj = _seed_project_with_report(tmp_path)

        gates_log = [GateLogEntry(gate_name="CW", status="passed", duration_s=0.1)]
        second = render_gate_report(str(proj["project_dir"]), gates_log)
        write_gate_report(str(proj["project_dir"]), second)

        result = get_gate_report(
            project_id=proj["project_id"],  # type: ignore[arg-type]
            base_dir=proj["base_dir"],
        )
        assert result["success"] is True
        report = result["report"]
        assert report["summary"]["failed"] == 0
        assert report["blocked_by_gate"] is None

    def test_unknown_project_error(self, tmp_path: Path) -> None:
        """Unknown project_id → structured NOT_FOUND error response."""
        from automedia.mcp.tools.pipeline import get_gate_report

        result = get_gate_report(
            project_id="no-such-proj",  # type: ignore[arg-type]
            base_dir=str(tmp_path),
        )
        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_no_report_not_found(self, tmp_path: Path) -> None:
        """Existing project without any report file → NOT_FOUND, no crash."""
        from automedia.mcp.tools.pipeline import get_gate_report

        proj = _seed_project_with_report(tmp_path)
        report_dir = Path(proj["project_dir"]) / "05_review" / "gate-report"
        for f in report_dir.glob("gate-report-*.json"):
            f.unlink()

        result = get_gate_report(
            project_id=proj["project_id"],  # type: ignore[arg-type]
            base_dir=proj["base_dir"],
        )
        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"
        assert "gate-report" in result["error"]["message"]

    def test_allowlist_denied_outside_allowlist(self) -> None:
        """base_dir NOT under the allowlist → structured ALLOWLIST_DENIED.

        The allowlist is fail-closed: only directories listed in
        mcp_allowlist.yaml (./, ./data, ./output, ./projects, /tmp/automedia)
        are readable — a project under any other directory is denied even
        when it exists.  Documents the Red-Line-3 path contract.
        """
        import tempfile

        from automedia.mcp.tools.pipeline import get_gate_report

        with tempfile.TemporaryDirectory() as outside:
            outside_root = Path(outside).resolve()
            proj = _seed_project_with_report(outside_root)

            result = get_gate_report(
                project_id=proj["project_id"],  # type: ignore[arg-type]
                base_dir=proj["base_dir"],
            )
            assert result["success"] is False
            assert result["error"]["code"] == "ALLOWLIST_DENIED"
            assert "not within any allowed directory" in result["error"]["message"]

    def test_registered_on_server(self) -> None:
        """create_server() registers get_gate_report."""
        from automedia.mcp.server import create_server

        server = create_server()
        names = set(server._tool_manager._tools.keys())
        assert "get_gate_report" in names
