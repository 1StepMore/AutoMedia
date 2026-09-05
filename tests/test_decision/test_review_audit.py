"""Dedicated module-level tests for the review-decision audit log (todo 10).

The module under test, :mod:`automedia.decision.review_audit`, was created in
todo 9 (commit 0be8f87) and is exercised indirectly through the
``review_decision`` MCP tool tests in ``tests/test_mcp/test_review_decision.py``
(TestReviewDecisionAuditLog: approve/reject/audit-failure).  Those tests pin
the *wiring*; this module pins the *semantics* of ``record_review_decision``
itself:

1. append-only, call-ordered JSON-lines to
   ``<user-config-dir>/audit/review_decisions.log`` (resolved via
   :func:`automedia.core.paths.get_user_config_dir`, honoring
   ``AUTOMEDIA_CONFIG_DIR``),
2. one stable entry schema (timestamp, project_id, gate_name, decision,
   reason, diff_record_path, actor),
3. log-write failure is swallowed (OSError at the mkdir/open boundary) —
   never propagates to the caller,
4. an existing log is preserved (append, never truncate),
5. the ``review_decision`` tool calls this module with ``actor="mcp"`` on
   every decision path (audit wiring cross-check).

Malformed/missing-project handling is a review_decision-tool concern and is
covered in tests/test_mcp/test_review_decision.py (structured-error tests);
intentionally not duplicated here.  All data is synthetic — no production
data, no LLM calls.
"""

from __future__ import annotations

import builtins
import json
import os
import stat
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from automedia.core.paths import get_user_config_dir
from automedia.decision.review_audit import record_review_decision

_EXPECTED_KEYS = {
    "timestamp",
    "project_id",
    "gate_name",
    "decision",
    "reason",
    "diff_record_path",
    "actor",
}


@pytest.fixture()
def audit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Hermetic user-config dir via ``AUTOMEDIA_CONFIG_DIR`` (mirrors the
    ``_audit_dir`` fixture in tests/test_mcp/test_review_decision.py:47-60,
    minus the allowlist pokes which only the MCP-tool tests need)."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(config_dir))
    yield config_dir


@pytest.fixture(autouse=True)
def _clean_hitl_waiters() -> Iterator[None]:
    """Keep the in-process HITL waiter registry clean around every test so
    the wiring test cannot leak (or see leaked) paused pipelines."""
    import automedia.pipelines.gate_types as gate_types

    with gate_types._hitl_lock:
        gate_types._hitl_waiters.clear()
    yield
    with gate_types._hitl_lock:
        gate_types._hitl_waiters.clear()


def _read_lines(config_dir: Path) -> list[dict[str, Any]]:
    """Parse the audit log into entries; every line must be valid JSON (the
    append-only contract is one JSON object per line)."""
    log_file = config_dir / "audit" / "review_decisions.log"
    assert log_file.is_file(), f"audit log missing at {log_file}"
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# Append-only order + entry schema
# ---------------------------------------------------------------------------


class TestAppendOrderAndSchema:
    def test_approve_then_reject_append_two_lines_in_call_order(self, audit_env: Path) -> None:
        record_review_decision("prj-audit01", "H0", "approve")
        record_review_decision("prj-audit01", "H0", "reject", reason="not on brand")

        entries = _read_lines(audit_env)
        assert len(entries) == 2
        assert [e["decision"] for e in entries] == ["approve", "reject"]
        assert entries[0]["reason"] == ""
        assert entries[1]["reason"] == "not on brand"

    def test_entry_schema(self, audit_env: Path) -> None:
        record_review_decision(
            "prj-schema1",
            "H0",
            "approve",
            reason="looks good",
            diff_record_path="/projects/prj-schema1/.automedia/gate_diffs/H0_1.json",
        )
        (entry,) = _read_lines(audit_env)
        assert set(entry) == _EXPECTED_KEYS
        assert entry["project_id"] == "prj-schema1"
        assert entry["gate_name"] == "H0"
        assert entry["decision"] == "approve"
        assert entry["reason"] == "looks good"
        assert entry["diff_record_path"] == "/projects/prj-schema1/.automedia/gate_diffs/H0_1.json"
        assert entry["actor"] == "mcp"
        assert entry["timestamp"]
        parsed = datetime.fromisoformat(str(entry["timestamp"]))
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_log_path_resolved_via_get_user_config_dir(self, audit_env: Path) -> None:
        """The module and the test must agree on path resolution: the log
        lives under ``get_user_config_dir()/audit/``.  With
        AUTOMEDIA_CONFIG_DIR set, get_user_config_dir() resolves to exactly
        that dir — proving the env override flows through to the writer."""
        record_review_decision("prj-pathres", "H0", "approve")
        assert get_user_config_dir() == audit_env
        assert (audit_env / "audit" / "review_decisions.log").is_file()

    def test_actor_is_caller_supplied(self, audit_env: Path) -> None:
        """``actor`` is caller-supplied per the plan's JSON contract
        (``"mcp"``/``"cli"``); the default is ``"mcp"``
        (pinned by test_entry_schema)."""
        record_review_decision("prj-actorsrc", "H0", "reject", reason="x", actor="cli")
        (entry,) = _read_lines(audit_env)
        assert entry["actor"] == "cli"

    def test_append_preserves_existing_log_content(self, audit_env: Path) -> None:
        record_review_decision("prj-append1", "H0", "approve")
        log_file = audit_env / "audit" / "review_decisions.log"
        before = log_file.read_text(encoding="utf-8")

        record_review_decision("prj-append2", "H0", "reject")

        after = log_file.read_text(encoding="utf-8")
        assert after.startswith(before)
        entries = _read_lines(audit_env)
        assert [e["project_id"] for e in entries] == ["prj-append1", "prj-append2"]


# ---------------------------------------------------------------------------
# Swallow semantics: a log-write failure must never raise
# ---------------------------------------------------------------------------


class TestSwallowSemantics:
    def test_config_dir_is_a_file_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Point AUTOMEDIA_CONFIG_DIR at an existing FILE: the module's
        ``log_path.parent.mkdir(parents=True, exist_ok=True)`` cannot create
        ``<file>/audit`` (NotADirectoryError/FileExistsError, both OSError
        subclasses) — the write is swallowed and nothing is created."""
        blocked = tmp_path / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(blocked))

        record_review_decision("prj-blocked1", "H0", "approve")

        assert blocked.is_file()
        assert not (blocked / "audit").exists()

    def test_read_only_config_parent_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Read-only parent dir: creating the ``audit`` subdir raises
        PermissionError (an OSError) — swallowed, nothing created.  chmod is
        unreliable on some mounts, so the file-in-path variant above is the
        primary guarantee; this one is skipped when it cannot hold (root,
        or a filesystem that ignores mode bits)."""
        if os.geteuid() == 0:
            pytest.skip("permissions are not enforced for root")
        read_only = tmp_path / "ro"
        read_only.mkdir()
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(read_only / "automedia"))
        before = stat.S_IMODE(read_only.stat().st_mode)
        read_only.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            probe = read_only / "automedia"
            try:
                probe.mkdir()
                probe.rmdir()
                pytest.skip("filesystem ignores permission bits")
            except PermissionError:
                pass

            record_review_decision("prj-ro-parent", "H0", "approve")
            assert not probe.exists()
        finally:
            read_only.chmod(before)

    def test_open_failure_is_swallowed(
        self, audit_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even when mkdir succeeds but the append itself fails (e.g. ENOSPC
        on open), the error is swallowed and no partial log line appears."""
        real_open = builtins.open

        def _deny(path: object, mode: str = "r", *args: object, **kwargs: object) -> object:
            if str(path).endswith("review_decisions.log"):
                raise OSError(28, "No space left on device")
            return real_open(path, mode, *args)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "open", _deny)
        record_review_decision("prj-enospc1", "H0", "approve")

        assert (audit_env / "audit").is_dir()
        assert not (audit_env / "audit" / "review_decisions.log").exists()


# ---------------------------------------------------------------------------
# Wiring cross-check: review_decision tool -> record_review_decision
# ---------------------------------------------------------------------------


class TestReviewToolWiring:
    def test_review_decision_records_via_review_audit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """review_decision (mcp/tools/review.py:187-197) must call the audit
        writer on EVERY decision path (approve and reject) with actor="mcp".

        Full integration (real H0 pause -> approve -> line on disk) is
        asserted by tests/test_mcp/test_review_decision.py
        (TestReviewDecisionAuditLog), which runs together with this file.

        Note on the plan's CLI branch: the "or" fork from todo 9 was decided
        there — the stale ``automedia hitl approve/reject`` instructions doc
        was corrected instead of adding CLI subcommands that cannot reach the
        in-process ``_hitl_waiters`` registry, so ``actor="cli"`` has no live
        caller today.  ``actor`` stays caller-supplied (see
        test_actor_is_caller_supplied) so a future same-process CLI surface
        can adopt the log without a schema change.
        """
        import automedia.mcp.tools.review as review_mod
        from automedia.pipelines.gate_types import PipelineProgress

        config_dir = tmp_path / "config"
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(config_dir))

        captures: list[dict[str, object]] = []

        def _capture(**kwargs: object) -> None:
            captures.append(kwargs)

        monkeypatch.setattr(review_mod, "record_review_decision", _capture)

        progress = PipelineProgress(project_id="prj-wiring1")
        with review_mod._hitl_lock:
            review_mod._hitl_waiters["prj-wiring1"] = progress

        def _fake_wait(self: PipelineProgress, project_dir: str, timeout: float) -> bool:
            return False

        monkeypatch.setattr(PipelineProgress, "wait_for_hitl", _fake_wait)

        approved = review_mod.review_decision("prj-wiring1", "H0", "approve")
        assert approved["success"] is True
        assert approved["approved"] is True

        # approve_hitl pops the waiter from the registry (gate_types.py) —
        # a real pipeline re-pauses by re-registering; mirror that for the
        # second decision on the same paused run.
        with review_mod._hitl_lock:
            review_mod._hitl_waiters["prj-wiring1"] = progress

        rejected = review_mod.review_decision("prj-wiring1", "H0", "reject", reason="no")
        assert rejected["success"] is True
        assert rejected["rejected"] is True

        assert [c["decision"] for c in captures] == ["approve", "reject"]
        assert all(c["actor"] == "mcp" for c in captures)
        assert all(c["project_id"] == "prj-wiring1" for c in captures)
        assert captures[1]["reason"] == "no"
