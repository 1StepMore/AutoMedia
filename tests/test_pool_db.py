"""Tests for automedia.pool.db — PoolDB SQLite wrapper."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import uuid
from collections.abc import Iterator

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
def pool(db_path: str) -> Iterator[PoolDB]:
    """Return a PoolDB instance backed by a temp file, closed on teardown.

    中文说明：必须 ``yield`` 后显式 ``close()``。Windows 上打开的 SQLite 连接
    会锁定 ``.db`` 文件，使 ``db_path`` fixture 的 teardown ``os.unlink`` 抛
    ``PermissionError [WinError 32]``——该文件此前有 22 项测试因此失败（测试体
    全部通过，失败全在 teardown）。``PoolDB`` 已提供 ``close()``，这里只是补上
    "用完即关"的职责，生产代码无需改动。
    """
    db = PoolDB(db_path)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def tmp_pool_db(pool: PoolDB) -> PoolDB:
    """Alias for pool fixture — used in update/delete/count tests."""
    return pool


# ===================================================================
# Tests
# ===================================================================


class TestPoolDBCreate:
    """Schema auto-creation on first connect."""

    def test_db_file_created(self, db_path: str):
        assert not os.path.exists(db_path)
        db = PoolDB(db_path)
        try:
            assert os.path.exists(db_path)
        finally:
            # 不关连接会让 db_path fixture 的 teardown unlink 在 Windows 上
            # 抛 WinError 32（见 pool fixture 的说明）。
            db.close()

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
            "CREATE TABLE topics ("
            "id INTEGER PRIMARY KEY,"
            " title TEXT,"
            " status TEXT DEFAULT 'pending'"
            ")"
        )
        conn.commit()
        conn.close()

        pool = PoolDB(db_path)
        try:
            pool.run_migration()

            # Verify column now exists
            cur = pool.conn.execute("PRAGMA table_info(topics)")
            cols = {row["name"] for row in cur.fetchall()}
            assert "tenant_id" in cols
        finally:
            # 同上：不关连接会让 teardown 的 unlink 在 Windows 上失败。
            pool.close()

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


class TestPoolDBFileRelease:
    """Windows 文件句柄释放 —— 回归锁定 22 项 teardown 失败。

    中文说明：Windows 上打开的 SQLite 连接会锁定 ``.db`` 文件；``close()`` 之后
    文件必须可删。此前该文件的 22 项失败**全部发生在 teardown 的 ``os.unlink``**
    （``PermissionError [WinError 32]``），测试体并无问题。本类是"用完即关"这一
    约定的回归门。
    """

    def test_close_releases_file_lock(self, db_path: str) -> None:
        """关闭连接后 db 文件可删且不残留 WAL sidecar。"""
        db = PoolDB(db_path)
        db.add_topic({"title": "lock probe"})
        db.close()

        # 句柄泄漏时，Windows 在此抛 PermissionError [WinError 32]
        os.unlink(db_path)

        assert not os.path.exists(db_path)
        for sidecar in (f"{db_path}-wal", f"{db_path}-shm"):
            assert not os.path.exists(sidecar), f"WAL sidecar left behind: {sidecar}"


class TestPoolDBUpdateScore:
    """update_score() — set score on a topic."""

    def test_update_score_changes_value(self, tmp_pool_db: PoolDB) -> None:
        tid = tmp_pool_db.add_topic({"title": "Score Me", "score": 0.0})
        tmp_pool_db.update_score(tid, 9.5)
        row = tmp_pool_db.get_topic(tid)
        assert row is not None
        assert row["score"] == 9.5

    def test_update_score_returns_none_for_invalid_id(self, tmp_pool_db: PoolDB) -> None:
        tmp_pool_db.update_score(99999, 5.0)


class TestPoolDBDeleteTopics:
    """delete_topics() — remove topics by ID list."""

    def test_delete_single_topic(self, tmp_pool_db: PoolDB) -> None:
        tid = tmp_pool_db.add_topic({"title": "Delete Me"})
        assert tmp_pool_db.get_topic(tid) is not None
        deleted = tmp_pool_db.delete_topics([tid])
        assert deleted == 1
        assert tmp_pool_db.get_topic(tid) is None

    def test_delete_multiple_topics(self, tmp_pool_db: PoolDB) -> None:
        ids = [tmp_pool_db.add_topic({"title": f"Item {i}"}) for i in range(5)]
        to_delete = ids[:3]
        deleted = tmp_pool_db.delete_topics(to_delete)
        assert deleted == 3
        remaining = tmp_pool_db.list_topics()
        assert len(remaining) == 2

    def test_delete_empty_list_returns_zero(self, tmp_pool_db: PoolDB) -> None:
        assert tmp_pool_db.delete_topics([]) == 0

    def test_delete_nonexistent_id_returns_zero(self, tmp_pool_db: PoolDB) -> None:
        assert tmp_pool_db.delete_topics([9999]) == 0


class TestPoolDBCountTopics:
    """count_topics() — total or filtered count."""

    def test_count_all_topics(self, tmp_pool_db: PoolDB) -> None:
        tmp_pool_db.add_topic({"title": "A"})
        tmp_pool_db.add_topic({"title": "B"})
        tmp_pool_db.add_topic({"title": "C"})
        assert tmp_pool_db.count_topics() == 3

    def test_count_by_status(self, tmp_pool_db: PoolDB) -> None:
        tmp_pool_db.add_topic({"title": "P1", "status": "pending"})
        tmp_pool_db.add_topic({"title": "P2", "status": "pending"})
        tmp_pool_db.add_topic({"title": "S1", "status": "selected"})
        assert tmp_pool_db.count_topics(status="pending") == 2
        assert tmp_pool_db.count_topics(status="selected") == 1

    def test_count_empty_db_returns_zero(self, tmp_pool_db: PoolDB) -> None:
        assert tmp_pool_db.count_topics() == 0
        assert tmp_pool_db.count_topics(status="pending") == 0

    def test_count_with_topic_after_delete(self, tmp_pool_db: PoolDB) -> None:
        tid = tmp_pool_db.add_topic({"title": "Temporary"})
        assert tmp_pool_db.count_topics() == 1
        tmp_pool_db.delete_topics([tid])
        assert tmp_pool_db.count_topics() == 0
