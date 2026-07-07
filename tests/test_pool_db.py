"""Tests for automedia.pool.db — PoolDB SQLite wrapper."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import uuid

import pytest

from automedia.pool.db import PoolDB


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def db_path() -> str:
    """Return a temporary file path that does not yet exist."""
    path = os.path.join(tempfile.gettempdir(), f"test_pool_{uuid.uuid4().hex}.db")
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def pool(db_path: str) -> PoolDB:
    """Return a PoolDB instance backed by a temp file."""
    return PoolDB(db_path)


# ===================================================================
# Tests
# ===================================================================


class TestPoolDBCreate:
    """Schema auto-creation on first connect."""

    def test_db_file_created(self, db_path: str):
        assert not os.path.exists(db_path)
        PoolDB(db_path)
        assert os.path.exists(db_path)

    def test_schema_has_topics_table(self, pool: PoolDB):
        cur = pool.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='topics'"
        )
        assert cur.fetchone() is not None

    def test_schema_columns(self, pool: PoolDB):
        cur = pool.conn.execute("PRAGMA table_info(topics)")
        cols = {row["name"] for row in cur.fetchall()}
        assert "id" in cols
        assert "title" in cols
        assert "url" in cols
        assert "status" in cols
        assert "score" in cols
        assert "tenant_id" in cols


class TestPoolDBCRUD:
    """Basic CRUD operations."""

    def test_add_topic_returns_id(self, pool: PoolDB):
        topic_id = pool.add_topic({"title": "Test Topic"})
        assert isinstance(topic_id, int)
        assert topic_id >= 1

    def test_get_topic(self, pool: PoolDB):
        tid = pool.add_topic({"title": "Hello", "url": "https://example.com"})
        row = pool.get_topic(tid)
        assert row is not None
        assert row["title"] == "Hello"
        assert row["url"] == "https://example.com"
        assert row["status"] == "pending"

    def test_get_topic_not_found(self, pool: PoolDB):
        assert pool.get_topic(9999) is None

    def test_list_topics_all(self, pool: PoolDB):
        pool.add_topic({"title": "A"})
        pool.add_topic({"title": "B"})
        pool.add_topic({"title": "C"})
        rows = pool.list_topics()
        assert len(rows) == 3

    def test_list_topics_filtered(self, pool: PoolDB):
        pool.add_topic({"title": "Pending", "status": "pending"})
        pool.add_topic({"title": "Selected", "status": "selected"})
        pending = pool.list_topics(status="pending")
        assert len(pending) == 1
        assert pending[0]["title"] == "Pending"

    def test_mark_selected(self, pool: PoolDB):
        tid = pool.add_topic({"title": "Pick me"})
        pool.mark_selected(tid)
        row = pool.get_topic(tid)
        assert row is not None
        assert row["status"] == "selected"

    def test_add_topic_with_full_data(self, pool: PoolDB):
        data = {
            "title": "Full",
            "url": "https://example.com",
            "source": "twitter",
            "category": "growth",
            "score": 9.5,
            "status": "selected",
            "tenant_id": "acme",
        }
        tid = pool.add_topic(data)
        row = pool.get_topic(tid)
        assert row is not None
        assert row["title"] == "Full"
        assert row["source"] == "twitter"
        assert row["category"] == "growth"
        assert row["score"] == 9.5
        assert row["tenant_id"] == "acme"


class TestPoolDBMigration:
    """run_migration applies ALTER TABLE / new indexes."""

    def test_migration_adds_tenant_id_if_missing(self, db_path: str):
        # Manually create a DB without tenant_id to test migration
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE topics (id INTEGER PRIMARY KEY, title TEXT, status TEXT DEFAULT 'pending')"
        )
        conn.commit()
        conn.close()

        pool = PoolDB(db_path)
        pool.run_migration()

        # Verify column now exists
        cur = pool.conn.execute("PRAGMA table_info(topics)")
        cols = {row["name"] for row in cur.fetchall()}
        assert "tenant_id" in cols

    def test_migration_is_idempotent(self, pool: PoolDB):
        # Run migration twice — no error
        pool.run_migration()
        pool.run_migration()  # should not raise


class TestPoolDBContextManager:
    """Context manager support."""

    def test_context_manager(self, db_path: str):
        with PoolDB(db_path) as pool:
            tid = pool.add_topic({"title": "ctx test"})
            row = pool.get_topic(tid)
            assert row is not None
        # After exit the internal connection is closed
        assert pool._conn is None
