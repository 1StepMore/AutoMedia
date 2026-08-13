"""Pipeline history hook — records per-gate lifecycle events to SQLite.

Each ``before_gate``, ``after_gate``, and ``on_gate_failed`` call writes a
row to ``pipeline_history`` in ``{project_dir}/.automedia/history.db``.
This provides an auditable log of pipeline execution for rollback and
debugging (Gap 9).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.hooks.protocol import GateObserver

log = get_logger(__name__)

HISTORY_DB_FILENAME = "history.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    timestamp     REAL    NOT NULL,
    metadata_json TEXT
);
"""


# ---------------------------------------------------------------------------
# Module-level helpers (also used by CLI commands)
# ---------------------------------------------------------------------------


def _db_path(project_dir: str) -> str:
    """Return absolute path to ``history.db`` under ``{project_dir}/.automedia/``."""
    return os.path.join(project_dir, ".automedia", HISTORY_DB_FILENAME)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the ``pipeline_history`` table if it does not exist."""
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


def _open_db(project_dir: str) -> sqlite3.Connection:
    """Open (or create) the history database and ensure the schema exists.

    The ``.automedia/`` directory is created inside *project_dir* if it does
    not already exist.
    """
    db_file = Path(_db_path(project_dir))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _read_history(project_dir: str) -> list[dict[str, Any]]:
    """Return all rows from ``pipeline_history`` as a list of dicts.

    Returns an empty list if the database does not exist.
    """
    db_file = _db_path(project_dir)
    if not os.path.isfile(db_file):
        return []
    conn = _open_db(project_dir)
    try:
        cur = conn.execute(
            "SELECT id, project_id, action, timestamp, metadata_json "
            "FROM pipeline_history ORDER BY id"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Hook implementation
# ---------------------------------------------------------------------------


class PipelineHistoryHook(GateObserver):
    """Records per-gate lifecycle events to a SQLite history database.

    Each gate lifecycle method writes a row with:
    * ``project_id`` — from gate context (falls back to ``"unknown"``)
    * ``action`` — ``"{gate_name}:{status}"`` (e.g. ``"lint:started"``)
    * ``timestamp`` — Unix timestamp (``time.time()``)
    * ``metadata_json`` — JSON blob with event-specific details

    The database is stored at ``{project_dir}/.automedia/history.db``.
    """

    def _write_entry(
        self,
        gate_name: str,
        status: str,
        context: dict[str, Any],
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        """Write a single row to the history database.

        Parameters
        ----------
        gate_name:
            Name of the gate being tracked.
        status:
            Lifecycle status: ``"started"``, ``"completed"``, or ``"failed"``.
        context:
            Gate context dict (readonly).  Must contain ``"project_dir"``.
        extra_meta:
            Optional extra fields to merge into ``metadata_json``.
        """
        project_dir = context.get("project_dir")
        if not project_dir:
            log.warning(
                "PipelineHistoryHook: project_dir not set; skipping write",
                gate=gate_name,
            )
            return

        project_id = context.get("project_id", "unknown")

        meta: dict[str, Any] = {
            "gate": gate_name,
            "project_id": project_id,
        }
        if extra_meta:
            meta.update(extra_meta)

        try:
            conn = _open_db(str(project_dir))
            try:
                conn.execute(
                    "INSERT INTO pipeline_history (project_id, action, timestamp, metadata_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        project_id,
                        f"{gate_name}:{status}",
                        time.time(),
                        json.dumps(meta, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            log.exception(
                "PipelineHistoryHook: failed to write entry",
                gate=gate_name,
                status=status,
            )

    # -- GateObserver overrides ------------------------------------------------

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        """Record a ``started`` entry for *gate_name*."""
        self._write_entry(gate_name, "started", context)

    def after_gate(
        self, gate_name: str, context: dict[str, Any], result: dict[str, Any]
    ) -> None:
        """Record a ``completed`` entry with the gate result metadata."""
        extra = {
            "passed": result.get("passed", True),
        }
        error = result.get("error")
        if error is not None:
            extra["error"] = str(error)
        self._write_entry(gate_name, "completed", context, extra_meta=extra)

    def on_gate_failed(
        self, gate_name: str, context: dict[str, Any], error: Exception
    ) -> None:
        """Record a ``failed`` entry with exception details."""
        extra = {
            "error": str(error),
            "error_type": type(error).__name__,
        }
        self._write_entry(gate_name, "failed", context, extra_meta=extra)
