"""Asset Database — SQLite storage for brand assets.

Provides schema creation, CRUD operations, and tag-aware search for
production artifacts (brand docs, market research, personas, content, etc).

The schema enforces a built-in type taxonomy:

    strategy, persona, product, content, kol_brief, asset

Custom user-defined tags are stored as a JSON array in the ``tags`` column.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from structlog import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Built-in type taxonomy
# ---------------------------------------------------------------------------

ASSET_TYPES = frozenset(
    {
        "strategy",
        "persona",
        "product",
        "content",
        "kol_brief",
        "asset",
    }
)

# ---------------------------------------------------------------------------
# AssetDoc — schema-aligned dataclass
# ---------------------------------------------------------------------------

_SKIP_ON_INSERT = {"created_at", "updated_at"}


@dataclass
class AssetDoc:
    """A single asset entry mirroring the ``assets`` table schema.

    Attributes match the DB columns 1-to-1.  ``tags`` is stored as a
    JSON array in the database but exposed as a Python list on the
    dataclass.
    """

    doc_id: str = ""
    brand_id: str = ""
    type: str = "asset"
    source_phase: str = ""
    title: str = ""
    tags: list[str] = field(default_factory=list)
    lang: str = "zh"
    file_path: str = ""
    vector_id: str = ""
    source_project_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    checksum: str = ""

    def to_db_row(self) -> dict[str, Any]:
        """Convert to a flat dict suitable for SQLite INSERT."""
        d = asdict(self)
        d["tags"] = json.dumps(d["tags"], ensure_ascii=False)
        # Strip fields that are DB-defaulted
        for skip in _SKIP_ON_INSERT:
            d.pop(skip, None)
        return d

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> AssetDoc:
        """Build an instance from a ``sqlite3.Row`` or plain dict."""
        row = dict(row)
        if isinstance(row.get("tags"), str):
            row["tags"] = json.loads(row["tags"])
        return cls(**row)


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS assets (
    doc_id            TEXT PRIMARY KEY,
    brand_id          TEXT NOT NULL,
    type              TEXT NOT NULL,
    source_phase      TEXT,
    title             TEXT NOT NULL,
    tags              TEXT,
    lang              TEXT DEFAULT 'zh',
    file_path         TEXT,
    vector_id         TEXT,
    source_project_id TEXT,
    created_at        TEXT DEFAULT (datetime('now')),
    updated_at        TEXT DEFAULT (datetime('now')),
    checksum          TEXT
);

CREATE INDEX IF NOT EXISTS idx_assets_brand   ON assets(brand_id);
CREATE INDEX IF NOT EXISTS idx_assets_type    ON assets(type);
CREATE INDEX IF NOT EXISTS idx_assets_phase   ON assets(source_phase);
CREATE INDEX IF NOT EXISTS idx_assets_checksum ON assets(checksum);
"""

# ---------------------------------------------------------------------------
# AssetDatabase
# ---------------------------------------------------------------------------


class AssetDatabase:
    """Per-brand SQLite storage for production artifacts.

    Each brand gets its own database file at::

        ~/.automedia/asset-library/{brand}/index.sqlite

    Parameters
    ----------
    brand : str
        Brand identifier used as the sub-directory name and stored in
        every row's ``brand_id`` column.
    """

    def __init__(self, brand: str) -> None:
        """Initialize the asset library database for a given brand."""
        self._brand = brand
        self._db_path = self._resolve_db_path(brand)
        self._conn: sqlite3.Connection | None = None
        self._open()

    # -- Path resolution ------------------------------------------------------

    @staticmethod
    def _base_dir() -> Path:
        """Return the root directory for asset library databases."""
        return Path(os.path.expanduser("~/.automedia/asset-library/"))

    @classmethod
    def _resolve_db_path(cls, brand: str) -> Path:
        """Resolve the SQLite database path for a given brand."""
        return cls._base_dir() / brand / "index.sqlite"

    # -- Connection management ------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        db_dir = self._db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        exists = self._db_path.exists()

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn

        if not exists:
            self._create_schema()
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the active SQLite connection, opening it if needed."""
        if self._conn is None:
            self._open()
        assert self._conn is not None  # noqa: S101 — type narrowing after _open()
        return self._conn

    @property
    def brand(self) -> str:
        """Return the brand identifier for this database instance."""
        return self._brand

    @property
    def db_path(self) -> Path:
        """Return the resolved SQLite database file path."""
        return self._db_path

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- Schema ---------------------------------------------------------------

    def _create_schema(self) -> None:
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    # -- CRUD -----------------------------------------------------------------

    def add_asset(self, doc: AssetDoc) -> str:
        """Insert a new asset and return its ``doc_id``.

        If ``doc.doc_id`` is empty a UUID is generated automatically.
        The ``brand_id`` is forced to the database's brand.

        Parameters
        ----------
        doc : AssetDoc
            Asset to insert.  ``doc_id``, ``created_at``, and
            ``updated_at`` are populated if left empty.

        Returns
        -------
        str
            The ``doc_id`` of the inserted row.
        """
        if not doc.doc_id:
            import uuid

            doc.doc_id = str(uuid.uuid4())
        doc.brand_id = self._brand
        if not doc.created_at:
            from datetime import datetime

            doc.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not doc.updated_at:
            from datetime import datetime

            doc.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row = doc.to_db_row()
        columns = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)

        stmt = f"INSERT INTO assets ({columns}) VALUES ({placeholders})"  # noqa: S608 — parameterized
        try:
            self.conn.execute(stmt, row)
            self.conn.commit()
        except sqlite3.IntegrityError:
            # doc_id already exists → update instead
            self._update_by_id(doc)
        return doc.doc_id

    def _update_by_id(self, doc: AssetDoc) -> None:
        """Update an existing row by ``doc_id``."""
        from datetime import datetime

        row = doc.to_db_row()
        row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sets = ", ".join(f"{k} = :{k}" for k in row if k != "doc_id")
        stmt = f"UPDATE assets SET {sets} WHERE doc_id = :doc_id"  # noqa: S608 — parameterized
        self.conn.execute(stmt, {**row, "doc_id": doc.doc_id})
        self.conn.commit()

    def get_asset(self, doc_id: str) -> dict[str, Any] | None:
        """Fetch a single asset by ``doc_id``.

        Returns ``None`` when the asset does not exist.
        """
        cur = self.conn.execute("SELECT * FROM assets WHERE doc_id = ?", (doc_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if isinstance(d.get("tags"), str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d["tags"] = json.loads(d["tags"])
        return d

    def search_by_type(self, asset_type: str) -> list[dict[str, Any]]:
        """Return all assets matching a given ``type``.

        The *asset_type* must be one of the built-in taxonomy:
        ``strategy``, ``persona``, ``product``, ``content``,
        ``kol_brief``, ``asset``.
        """
        cur = self.conn.execute(
            "SELECT * FROM assets WHERE type = ? ORDER BY created_at DESC",
            (asset_type,),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def search_by_tags(self, tags: list[str]) -> list[dict[str, Any]]:
        """Return assets that contain *any* of the given tags.

        Tags are matched by JSON array containment.  The search uses
        SQLite's ``json_each`` for a proper overlap query.
        """
        if not tags:
            return []

        # Build a query that finds assets whose tags JSON array
        # contains at least one of the provided tags.
        placeholders = ", ".join("?" for _ in tags)
        query = f"""
            SELECT DISTINCT a.*
            FROM assets a, json_each(a.tags) AS j
            WHERE j.value IN ({placeholders})
            ORDER BY a.created_at DESC
        """  # noqa: S608 — parameterized
        cur = self.conn.execute(query, tags)
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def keyword_search(self, query: str) -> list[dict[str, Any]]:
        """Search assets by keyword (LIKE on ``title``).

        The search is case-insensitive and matches substrings.
        """
        pattern = f"%{query}%"
        cur = self.conn.execute(
            "SELECT * FROM assets WHERE title LIKE ? ORDER BY created_at DESC",
            (pattern,),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def list_all(self) -> list[dict[str, Any]]:
        """Return every asset ordered by creation date (newest first)."""
        cur = self.conn.execute("SELECT * FROM assets ORDER BY created_at DESC")
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def count(self) -> int:
        """Return the total number of assets in the database."""
        cur = self.conn.execute("SELECT COUNT(*) FROM assets")
        row = cur.fetchone()
        assert row is not None  # noqa: S101 — type narrowing after fetchone()
        return row[0]

    def delete_asset(self, doc_id: str) -> None:
        """Remove an asset by ``doc_id``."""
        self.conn.execute("DELETE FROM assets WHERE doc_id = ?", (doc_id,))
        self.conn.commit()

    # -- Utility --------------------------------------------------------------

    def asset_exists_by_checksum(self, checksum: str) -> bool:
        """Check whether an asset with the given content checksum exists."""
        cur = self.conn.execute(
            "SELECT 1 FROM assets WHERE checksum = ? LIMIT 1",
            (checksum,),
        )
        return cur.fetchone() is not None

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> AssetDatabase:
        """Enter context manager and return self."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Exit context manager — close the database connection."""
        self.close()
