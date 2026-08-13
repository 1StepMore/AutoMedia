"""Tests for PipelineHistoryHook — records pipeline gate history to SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from automedia.hooks.pipeline_history import (
    HISTORY_DB_FILENAME,
    PipelineHistoryHook,
    _db_path,
    _ensure_schema,
    _read_history,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _history_rows(project_dir: Path) -> list[dict[str, Any]]:
    """Return all rows from pipeline_history as list of dicts."""
    return _read_history(str(project_dir))


# ---------------------------------------------------------------------------
# _db_path utility
# ---------------------------------------------------------------------------


class TestDbPath:
    """Tests for the module-level _db_path helper."""

    def test_returns_path_under_automedia_dir(self) -> None:
        """_db_path joins project_dir with .automedia/ and HISTORY_DB_FILENAME."""
        result = _db_path("/some/project")
        expected = "/some/project/.automedia/history.db"
        assert result == expected

    def test_uses_history_db_filename_constant(self) -> None:
        """_db_path uses the module-level HISTORY_DB_FILENAME."""
        assert HISTORY_DB_FILENAME == "history.db"


# ---------------------------------------------------------------------------
# _ensure_schema
# ---------------------------------------------------------------------------


class TestEnsureSchema:
    """_ensure_schema creates the pipeline_history table if it does not exist."""

    def test_creates_table(self, tmp_path: Path) -> None:
        """A fresh DB gets the pipeline_history table."""
        db_file = tmp_path / ".automedia" / "history.db"
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        conn.close()

        # Re-open and verify schema
        conn2 = sqlite3.connect(str(db_file))
        conn2.row_factory = sqlite3.Row
        cur = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_history'"
        )
        assert cur.fetchone() is not None
        conn2.close()

    def test_column_schema(self, tmp_path: Path) -> None:
        """The pipeline_history table has the expected columns."""
        db_file = tmp_path / ".automedia" / "history.db"
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)

        cur = conn.execute("PRAGMA table_info(pipeline_history)")
        columns = {row["name"]: row for row in cur.fetchall()}
        conn.close()

        assert columns["id"]["type"].upper() == "INTEGER"
        assert columns["project_id"]["type"].upper() == "TEXT"
        assert columns["project_id"]["notnull"] == 1
        assert columns["action"]["type"].upper() == "TEXT"
        assert columns["action"]["notnull"] == 1
        assert columns["timestamp"]["type"].upper() == "REAL"
        assert columns["timestamp"]["notnull"] == 1
        assert columns["metadata_json"]["type"].upper() == "TEXT"

    def test_id_is_autoincrement_primary_key(self, tmp_path: Path) -> None:
        """The id column is an autoincrement primary key."""
        db_file = tmp_path / ".automedia" / "history.db"
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)

        cur = conn.execute("PRAGMA table_info(pipeline_history)")
        cols = {row["name"]: row for row in cur.fetchall()}
        conn.close()

        assert cols["id"]["pk"] == 1  # primary key

    def test_idempotent_multiple_calls(self, tmp_path: Path) -> None:
        """Calling _ensure_schema multiple times does not raise."""
        db_file = tmp_path / ".automedia" / "history.db"
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        _ensure_schema(conn)  # second call
        conn.close()


# ---------------------------------------------------------------------------
# PipelineHistoryHook — before_gate
# ---------------------------------------------------------------------------


class TestPipelineHistoryHookBeforeGate:
    """before_gate writes a 'started' entry to the history DB."""

    def test_writes_started_entry(self, tmp_path: Path) -> None:
        """Calling before_gate creates a started entry in the DB."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("lint", ctx)

        rows = _history_rows(tmp_path)
        assert len(rows) == 1
        assert rows[0]["action"] == "lint:started"
        assert rows[0]["project_id"] == "p1"

    def test_records_timestamp(self, tmp_path: Path) -> None:
        """The timestamp is a positive float (Unix timestamp)."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("lint", ctx)

        rows = _history_rows(tmp_path)
        ts = rows[0]["timestamp"]
        assert isinstance(ts, float)
        assert ts > 1_700_000_000  # reasonable Unix timestamp for 2023+

    def test_metadata_contains_gate_and_project(self, tmp_path: Path) -> None:
        """The metadata_json column contains serialized info about the event."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("lint", ctx)

        rows = _history_rows(tmp_path)
        meta = json.loads(rows[0]["metadata_json"])
        assert meta["gate"] == "lint"
        assert meta["project_id"] == "p1"


# ---------------------------------------------------------------------------
# PipelineHistoryHook — after_gate
# ---------------------------------------------------------------------------


class TestPipelineHistoryHookAfterGate:
    """after_gate writes a 'completed' entry to the history DB."""

    def test_writes_completed_entry(self, tmp_path: Path) -> None:
        """Calling after_gate creates a completed entry in the DB."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("lint", ctx)
        hook.after_gate("lint", ctx, {"passed": True})

        rows = _history_rows(tmp_path)
        assert len(rows) == 2
        assert rows[1]["action"] == "lint:completed"
        assert rows[1]["project_id"] == "p1"

    def test_records_timestamp(self, tmp_path: Path) -> None:
        """The timestamp is a positive float for completed entries."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": True})

        rows = _history_rows(tmp_path)
        ts = rows[1]["timestamp"]
        assert isinstance(ts, float)
        assert ts > 1_700_000_000

    def test_metadata_contains_result_passed(self, tmp_path: Path) -> None:
        """The metadata_json includes the result with passed status."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": True})

        rows = _history_rows(tmp_path)
        meta = json.loads(rows[1]["metadata_json"])
        assert meta["passed"] is True

    def test_metadata_contains_result_failed_with_error(
        self, tmp_path: Path
    ) -> None:
        """When a gate fails with an error, the metadata includes it."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.after_gate("g", ctx, {"passed": False, "error": "CTA missing"})

        rows = _history_rows(tmp_path)
        meta = json.loads(rows[1]["metadata_json"])
        assert meta["passed"] is False
        assert meta["error"] == "CTA missing"


# ---------------------------------------------------------------------------
# PipelineHistoryHook — on_gate_failed
# ---------------------------------------------------------------------------


class TestPipelineHistoryHookOnGateFailed:
    """on_gate_failed writes a 'failed' entry with exception info."""

    def test_writes_failed_entry(self, tmp_path: Path) -> None:
        """Calling on_gate_failed creates a failed entry in the DB."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("tts", ctx)
        hook.on_gate_failed("tts", ctx, RuntimeError("service down"))

        rows = _history_rows(tmp_path)
        assert len(rows) == 2
        assert rows[1]["action"] == "tts:failed"
        assert rows[1]["project_id"] == "p1"

    def test_metadata_contains_exception_string(self, tmp_path: Path) -> None:
        """The exception message is captured in metadata_json."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("tts", ctx)
        hook.on_gate_failed("tts", ctx, ConnectionError("timeout after 30s"))

        rows = _history_rows(tmp_path)
        meta = json.loads(rows[1]["metadata_json"])
        assert "timeout after 30s" in meta["error"]

    def test_records_timestamp(self, tmp_path: Path) -> None:
        """The timestamp is recorded for failed entries."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("g", ctx)
        hook.on_gate_failed("g", ctx, ValueError("bad input"))

        rows = _history_rows(tmp_path)
        ts = rows[1]["timestamp"]
        assert isinstance(ts, float)
        assert ts > 1_700_000_000


# ---------------------------------------------------------------------------
# PipelineHistoryHook — multiple gates accumulate
# ---------------------------------------------------------------------------


class TestPipelineHistoryHookAccumulation:
    """Multiple gate invocations accumulate entries in the history DB."""

    def test_multiple_gates_appended(self, tmp_path: Path) -> None:
        """Each lifecycle event adds a sequential entry in the DB."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}

        hook.before_gate("g1", ctx)
        hook.after_gate("g1", ctx, {"passed": True})

        hook.before_gate("g2", ctx)
        hook.after_gate("g2", ctx, {"passed": False, "error": "bad"})

        hook.before_gate("g3", ctx)
        hook.on_gate_failed("g3", ctx, RuntimeError("boom"))

        rows = _history_rows(tmp_path)
        assert len(rows) == 6
        actions = [r["action"] for r in rows]
        assert actions == [
            "g1:started",
            "g1:completed",
            "g2:started",
            "g2:completed",
            "g3:started",
            "g3:failed",
        ]

    def test_ids_are_sequential(self, tmp_path: Path) -> None:
        """Primary key IDs increase monotonically."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}

        hook.before_gate("a", ctx)
        hook.after_gate("a", ctx, {"passed": True})
        hook.before_gate("b", ctx)
        hook.after_gate("b", ctx, {"passed": True})

        rows = _history_rows(tmp_path)
        ids = [r["id"] for r in rows]
        assert ids == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# PipelineHistoryHook — error resilience
# ---------------------------------------------------------------------------


class TestPipelineHistoryHookErrorResilience:
    """Errors during DB operations are logged and do not raise."""

    def test_missing_project_dir_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When project_dir is missing from context, the hook logs and returns."""
        import logging

        hook = PipelineHistoryHook()
        caplog.set_level(logging.WARNING, logger="automedia.hooks.pipeline_history")

        # Should not raise
        hook.before_gate("g", {})
        hook.after_gate("g", {}, {"passed": True})

        assert "project_dir not set" in caplog.text

    def test_missing_project_dir_skips_write(self, tmp_path: Path) -> None:
        """No DB file is created when project_dir is missing."""
        hook = PipelineHistoryHook()
        hook.before_gate("g", {})
        hook.after_gate("g", {}, {"passed": True})

        db_file = tmp_path / ".automedia" / "history.db"
        assert not db_file.exists()

    def test_context_missing_keys_does_not_raise(self) -> None:
        """before_gate / after_gate tolerate context without project_dir/project_id."""
        hook = PipelineHistoryHook()
        # These should not raise
        hook.before_gate("g", {"project_dir": "/tmp"})
        hook.after_gate("g", {"project_dir": "/tmp"}, {"passed": True})

    def test_missing_project_id_uses_fallback(self, tmp_path: Path) -> None:
        """When project_id is missing, 'unknown' is used as fallback."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path)}
        hook.before_gate("g", ctx)

        rows = _history_rows(tmp_path)
        assert rows[0]["project_id"] == "unknown"


# ---------------------------------------------------------------------------
# PipelineHistoryHook — data directory creation
# ---------------------------------------------------------------------------


class TestPipelineHistoryHookDirectoryCreation:
    """The .automedia directory is created if it does not exist."""

    def test_creates_automedia_dir_if_missing(self, tmp_path: Path) -> None:
        """If .automedia/ does not exist, it is created automatically."""
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("lint", ctx)

        automedia_dir = tmp_path / ".automedia"
        assert automedia_dir.is_dir()
        assert (automedia_dir / "history.db").exists()

    def test_uses_existing_automedia_dir(self, tmp_path: Path) -> None:
        """If .automedia/ already exists, it is reused."""
        (tmp_path / ".automedia").mkdir()
        hook = PipelineHistoryHook()
        ctx = {"project_dir": str(tmp_path), "project_id": "p1"}
        hook.before_gate("lint", ctx)

        automedia_dir = tmp_path / ".automedia"
        assert (automedia_dir / "history.db").exists()


# ---------------------------------------------------------------------------
# PipelineHistoryHook — protocol conformance
# ---------------------------------------------------------------------------


class TestPipelineHistoryHookProtocol:
    """PipelineHistoryHook satisfies the GateHook protocol."""

    def test_isinstance_gate_hook(self) -> None:
        """PipelineHistoryHook is an instance of GateHook via structural subtyping."""
        from automedia.hooks.protocol import GateHook

        assert isinstance(PipelineHistoryHook(), GateHook)

    def test_isinstance_gate_observer(self) -> None:
        """PipelineHistoryHook inherits from GateObserver."""
        from automedia.hooks.protocol import GateObserver

        assert isinstance(PipelineHistoryHook(), GateObserver)
