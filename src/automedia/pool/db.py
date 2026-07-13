"""PoolDB — SQLite access for the topic pool database.

Provides schema creation, migration, and CRUD for topics.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, TypedDict


class TopicRecord(TypedDict, total=False):
    """A single topic row from the pool database."""

    id: int
    title: str
    url: str
    source: str
    category: str
    status: str
    score: float
    tenant_id: str
    created_at: str
    updated_at: str
    research_data: str

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    url         TEXT,
    source      TEXT,
    category    TEXT,
    status      TEXT    DEFAULT 'pending',
    score       REAL    DEFAULT 0.0,
    tenant_id   TEXT    DEFAULT 'default',
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_topics_status  ON topics(status);
CREATE INDEX IF NOT EXISTS idx_topics_category ON topics(category);
"""

_MIGRATIONS: list[str] = [
    "ALTER TABLE topics ADD COLUMN tenant_id TEXT DEFAULT 'default'",
    "CREATE INDEX IF NOT EXISTS idx_topics_tenant ON topics(tenant_id)",
    "ALTER TABLE topics ADD COLUMN research_data TEXT DEFAULT ''",
]


class PoolDB:
    """SQLite wrapper for topic pool storage.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite database file. If the file does not exist the
        schema is created automatically.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._open()

    # -- Public helpers -------------------------------------------------------

    @property
    def db_path(self) -> Path:
        """Return the resolved database file path."""
        return self._db_path

    # -- Connection management ------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        """Open (or create) the SQLite database and ensure the schema exists."""
        exists = self._db_path.exists()
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        self._conn = conn
        if not exists:
            self._create_schema()
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._open()
        assert self._conn is not None  # noqa: S101 — type narrowing after _open()
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- Schema ---------------------------------------------------------------

    def _create_schema(self) -> None:
        """Create the initial schema for a fresh database."""
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def run_migration(self) -> None:
        """Apply any pending migrations (ALTER TABLE, new indexes, …).

        Each migration is executed inside an EXCLUSIVE transaction.  Errors
        are logged but do not prevent later migrations from running.
        """
        for sql in _MIGRATIONS:
            try:
                self.conn.execute(sql)
                self.conn.commit()
            except sqlite3.OperationalError as exc:
                # Swallow harmless errors such as "duplicate column" when the
                # migration has already been applied.
                msg = str(exc)
                if "duplicate column" in msg.lower():
                    continue
                raise

    # -- CRUD -----------------------------------------------------------------

    def add_topic(self, data: dict[str, Any]) -> int:
        """Insert a new topic and return its ``id``.

        Parameters
        ----------
        data : dict
            Expected keys: ``title`` (required), ``url``, ``source``,
            ``category``, ``score``, ``status``, ``tenant_id``.
        """
        stmt = """
            INSERT INTO topics (title, url, source, category, score, status, tenant_id)
            VALUES (:title, :url, :source, :category, :score, :status, :tenant_id)
        """
        row = {
            "title": data.get("title", ""),
            "url": data.get("url", ""),
            "source": data.get("source", ""),
            "category": data.get("category", ""),
            "score": data.get("score", 0.0),
            "status": data.get("status", "pending"),
            "tenant_id": data.get("tenant_id", "default"),
        }
        cur = self.conn.execute(stmt, row)
        self.conn.commit()
        lastrowid = cur.lastrowid
        assert lastrowid is not None  # noqa: S101 — type narrowing
        return lastrowid

    def get_topic(self, topic_id: int) -> TopicRecord | None:
        """Fetch a single topic by its primary key.

        Returns ``None`` when the topic does not exist.
        """
        cur = self.conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)  # type: ignore[return-value]

    def list_topics(self, status: str | None = None) -> list[TopicRecord]:
        """Return all topics, optionally filtered by *status*."""
        if status:
            cur = self.conn.execute("SELECT * FROM topics WHERE status = ? ORDER BY id", (status,))
        else:
            cur = self.conn.execute("SELECT * FROM topics ORDER BY id")
        return [dict(r) for r in cur.fetchall()]  # type: ignore[misc]

    def mark_selected(self, topic_id: int) -> None:
        """Update a topic's status to ``'selected'``."""
        self.conn.execute(
            "UPDATE topics SET status = 'selected', updated_at = datetime('now') WHERE id = ?",
            (topic_id,),
        )
        self.conn.commit()

    def update_score(self, topic_id: int, score: float) -> None:
        """Update a topic's score."""
        self.conn.execute(
            "UPDATE topics SET score = ?, updated_at = datetime('now') WHERE id = ?",
            (score, topic_id),
        )
        self.conn.commit()

    def delete_topics(self, topic_ids: list[int]) -> int:
        """Delete topics by their IDs.  Returns the number of rows removed."""
        if not topic_ids:
            return 0
        placeholders = ",".join("?" for _ in topic_ids)
        cur = self.conn.execute(
            f"DELETE FROM topics WHERE id IN ({placeholders})",  # noqa: S608
            topic_ids,
        )
        self.conn.commit()
        assert cur.rowcount is not None  # noqa: S101 — type narrowing
        return cur.rowcount

    def update_brief(self, topic_id: int, md_content: str) -> None:
        self.conn.execute(
            "UPDATE topics SET research_data = ?, updated_at = datetime('now') WHERE id = ?",
            (md_content, topic_id),
        )
        self.conn.commit()

    def count_topics(self, status: str | None = None) -> int:
        """Return the number of topics, optionally filtered by *status*."""
        if status:
            cur = self.conn.execute("SELECT COUNT(*) FROM topics WHERE status = ?", (status,))
        else:
            cur = self.conn.execute("SELECT COUNT(*) FROM topics")
        row = cur.fetchone()
        assert row is not None  # noqa: S101 — type narrowing after fetchone()
        return row[0]

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> PoolDB:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
