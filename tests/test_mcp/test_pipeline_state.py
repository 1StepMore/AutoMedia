"""Tests for the ``get_pipeline_state`` MCP tool (Wave 3 Todo 11).

Contract: the tool is registered on ``create_server()`` and returns a
success_response whose payload carries per-gate rows (gate/status/track/
md5/recorded_at) aggregated from the project's history.db + pipeline_md5.json.
Unknown project_id → structured NOT_FOUND error. Zero production data.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from automedia.hooks.md5_tracker import record_md5
from automedia.hooks.pipeline_history import _db_path, _ensure_schema
from automedia.mcp.allowlist import _reset_allowlist_cache
from automedia.pipelines.runner import _MODE_MAP

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(autouse=True)
def _allowlist(tmp_path: Path) -> None:
    """Reset the allowlist cache and point it at tmp_path for the test."""
    _reset_allowlist_cache()
    import automedia.mcp.server as _server_mod

    _server_mod._cached_allowlist = [str(tmp_path.resolve())]
    yield
    _reset_allowlist_cache()


def _seed_project(
    tmp_path: Path,
    project_id: str = "state-proj-001",
    *,
    with_history: bool = True,
) -> dict[str, Any]:
    """Create a project dir with info file and (optionally) gate history+md5.

    Seeds ``G0:completed`` (passed), ``G1:completed`` (passed: false → failed),
    ``V1:started`` (pending) and a real md5 record for G0.
    """
    slug = "test-topic"
    project_dir = tmp_path / f"20260707_{slug}"
    project_dir.mkdir(parents=True)

    info = {
        "project_id": project_id,
        "topic": "Test Topic",
        "brand": "TestBrand",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

    if with_history:
        db_file = Path(_db_path(str(project_dir)))
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file))
        try:
            _ensure_schema(conn)
            base_ts = time.time()
            rows: list[tuple[str, dict[str, Any]]] = [
                ("G0:completed", {"gate": "G0", "project_id": project_id, "passed": True}),
                ("G1:completed", {"gate": "G1", "project_id": project_id, "passed": False}),
                ("V1:started", {"gate": "V1", "project_id": project_id}),
            ]
            for i, (action, meta) in enumerate(rows):
                conn.execute(
                    "INSERT INTO pipeline_history (project_id, action, timestamp, "
                    "metadata_json) VALUES (?, ?, ?, ?)",
                    (project_id, action, base_ts + i, json.dumps(meta)),
                )
            conn.commit()
        finally:
            conn.close()

        asset = project_dir / "g0_asset.txt"
        asset.write_text("synthetic g0 asset", encoding="utf-8")
        record_md5(str(project_dir), "G0", str(asset))

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


# =========================================================================
# Tests
# =========================================================================


class TestGetPipelineState:
    """get_pipeline_state returns per-gate rows for a seeded project."""

    def test_returns_rows(self, tmp_path: Path) -> None:
        """Seeded project → success payload with per-gate state rows."""
        from automedia.mcp.tools.pipeline import get_pipeline_state

        proj = _seed_project(tmp_path)
        result = get_pipeline_state(
            project_id=proj["project_id"],  # type: ignore[arg-type]
            base_dir=proj["base_dir"],
        )

        assert result["success"] is True, result
        assert result["project_id"] == proj["project_id"]
        assert result["mode"] == "auto"
        gates = result["gates"]
        assert isinstance(gates, list) and gates

        assert len(gates) == len(_MODE_MAP["auto"])
        by_gate = {row["gate"]: row for row in gates}
        assert by_gate["G0"]["status"] == "passed"
        assert by_gate["G1"]["status"] == "failed"
        assert by_gate["V1"]["status"] == "pending"
        assert by_gate["H0"]["status"] == "pending"
        assert by_gate["G0"]["track"] == "copy"
        assert by_gate["V1"]["track"] == "video"
        assert by_gate["G0"]["md5"]

    def test_no_history_project_all_pending(self, tmp_path: Path) -> None:
        """Project without history.db → all-pending rows, never an error."""
        from automedia.mcp.tools.pipeline import get_pipeline_state

        proj = _seed_project(tmp_path, "state-proj-bare", with_history=False)
        result = get_pipeline_state(
            project_id=proj["project_id"],  # type: ignore[arg-type]
            base_dir=proj["base_dir"],
        )

        assert result["success"] is True, result
        gates = result["gates"]
        assert len(gates) == len(_MODE_MAP["auto"])
        assert all(row["status"] == "pending" for row in gates)

    def test_unknown_project_error(self, tmp_path: Path) -> None:
        """Unknown project_id → structured NOT_FOUND error response."""
        from automedia.mcp.tools.pipeline import get_pipeline_state

        result = get_pipeline_state(
            project_id="no-such-proj",  # type: ignore[arg-type]
            base_dir=str(tmp_path),
        )
        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_registered_on_server(self) -> None:
        """create_server() registers get_pipeline_state."""
        from automedia.mcp.server import create_server

        server = create_server()
        names = set(server._tool_manager._tools.keys())
        assert "get_pipeline_state" in names
