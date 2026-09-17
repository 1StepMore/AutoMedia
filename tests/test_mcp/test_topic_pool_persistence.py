"""MCP topic tools persist by default (reinforcement task 1).

Contract: ``select_topic``, ``list_topic_pool`` and ``add_pool_topic`` default
to a **persistent** cwd-relative ``.automedia/pool.db`` — the same working
directory base the MCP allowlist resolves its ``./`` entry against — instead
of a throwaway ``:memory:`` database.  A topic added by one process is
therefore visible to a brand-new process, and the resolved default path is a
real file on disk.

Hermeticity: every test chdirs into ``tmp_path`` and monkeypatches the cached
MCP allowlist so the temp pool is allowlisted.  The real repo ``.automedia/``
and the user ``~/.automedia/`` are never touched; no network is used.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from automedia.mcp.allowlist import _require_allowed, _reset_allowlist_cache
from automedia.mcp.tools import add_pool_topic, list_topic_pool, select_topic
from automedia.pool.db import PoolDB, default_pool_path


@pytest.fixture(autouse=True)
def _hermetic_cwd_and_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run with cwd == tmp_path and an allowlist containing exactly tmp_path.

    The MCP allowlist is cached process-wide; it must be reset and repopulated
    around each test (mirrors the ``_audit_dir`` cache-poke pattern used by
    ``test_review_decision``).  This guarantees the default pool resolves under
    ``tmp_path`` and no test writes to the real repo ``.automedia/``.
    """
    monkeypatch.chdir(tmp_path)
    _reset_allowlist_cache()
    import automedia.mcp.server as _server_mod

    _server_mod._cached_allowlist = [str(tmp_path.resolve())]  # type: ignore[attr-defined]  # private cache poked to allowlist tmp_path (repo pattern)
    yield tmp_path
    _reset_allowlist_cache()


def _run_in_new_process(code: str, cwd: Path) -> str:
    """Run *code* in a fresh Python interpreter rooted at *cwd*; return stdout."""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, f"new process failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    return proc.stdout


# ---------------------------------------------------------------------------
# default_pool_path — single source of the MCP default
# ---------------------------------------------------------------------------


class TestDefaultPoolPath:
    """The shared helper resolves to a persistent cwd-relative pool file."""

    def test_resolves_under_cwd_as_automedia_pool_db(self, tmp_path: Path) -> None:
        resolved = default_pool_path().resolve()
        assert resolved.is_relative_to(tmp_path.resolve())
        assert resolved.parent.name == ".automedia"
        assert resolved.name == "pool.db"

    def test_default_path_is_a_real_file_not_memory(self, tmp_path: Path) -> None:
        # Given: a topic added through the production default path
        add_pool_topic(title="disk-topic", category="tech")

        # Then: the default is a real on-disk database, and an independent
        # PoolDB constructed from the same default sees the row.
        pool_file = tmp_path / ".automedia" / "pool.db"
        assert pool_file.is_file()
        with PoolDB(default_pool_path()) as db:
            titles = [t["title"] for t in db.list_topics()]
        assert titles == ["disk-topic"]

        # The production list tool opens a fresh connection to the same file.
        listed = list_topic_pool()
        assert [t["title"] for t in listed["topics"]] == ["disk-topic"]


# ---------------------------------------------------------------------------
# Cross-process persistence
# ---------------------------------------------------------------------------


class TestCrossProcessPersistence:
    """A topic added in one process is listed by a NEW process."""

    def test_topic_added_in_one_process_is_listed_by_a_new_process(self, tmp_path: Path) -> None:
        # Given: a topic added via the production MCP tool path in a NEW process
        raw_added = _run_in_new_process(
            "import json;"
            "from automedia.mcp.tools import add_pool_topic;"
            "print(json.dumps(add_pool_topic(title='persisted-topic', category='tech')))",
            cwd=tmp_path,
        )
        added = json.loads(raw_added)
        assert added["success"] is True, added
        assert added["id"] > 0
        assert (tmp_path / ".automedia" / "pool.db").is_file()

        # When: a SECOND, independent process lists the pool
        raw_listed = _run_in_new_process(
            "import json;"
            "from automedia.mcp.tools import list_topic_pool;"
            "print(json.dumps(list_topic_pool()))",
            cwd=tmp_path,
        )
        listed = json.loads(raw_listed)

        # Then: the topic added by the first process is present
        titles = [t["title"] for t in listed["topics"]]
        assert "persisted-topic" in titles

    def test_select_topic_uses_the_persistent_default(self, tmp_path: Path) -> None:
        # Given: a topic in the persistent default pool
        add_pool_topic(title="pick-me", category="tech")

        # When: select_topic reads the default pool (no explicit path)
        result = select_topic(category="tech")

        # Then: it selects the persisted topic rather than an empty :memory: DB
        assert result.get("selected") is not None
        assert result["selected"]["title"] == "pick-me"


# ---------------------------------------------------------------------------
# Explicit-path branch and allowlist semantics are unchanged
# ---------------------------------------------------------------------------


class TestExplicitPathAllowlistUnchanged:
    """An explicit out-of-allowlist pool_db_path is still denied."""

    def test_guard_still_raises_for_out_of_allowlist_path(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside-pool.db"
        with pytest.raises(PermissionError, match="not within any allowed directory"):
            _require_allowed(str(outside), tool_name="add_pool_topic")

    def test_tool_refuses_out_of_allowlist_path_without_creating_db(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside-pool.db"
        result = add_pool_topic(title="denied", pool_db_path=str(outside))

        assert result["success"] is False
        assert result["error"]["message"].find("not within any allowed directory") >= 0
        assert not outside.exists()
