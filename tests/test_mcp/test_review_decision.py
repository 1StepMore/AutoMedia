"""Tests for the ``review_decision`` MCP tool (productization-roadmap todo 9).

Contract: the tool resolves a LIVE paused pipeline through the in-process
``_hitl_waiters`` registry (same-process constraint — NOT the dormant
engine-registry path used by ``approve_gate``/``reject_gate``), signals
``approve_hitl``/``reject_hitl``, and records the decision to the
review-decision audit log.  ``show_diff=True`` renders a unified diff from
the todo-8 diff records under ``<project_dir>/.automedia/gate_diffs/``;
without a record it reports ``diff_unavailable: true``.  A project that is
not paused (including CLI-started pipelines in another process) gets a
fast structured error — never a deadlock.

All tests use synthetic data and real :class:`H0HumanReviewGate` pause
flows — no LLM API calls.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from automedia.gates.h0_human_review import H0HumanReviewGate
from automedia.mcp.allowlist import _reset_allowlist_cache
from automedia.mcp.tools.review import review_decision
from automedia.pipelines.gate_engine import GateEngine, PipelineProgress
from automedia.pipelines.gate_types import _hitl_lock, _hitl_waiters


@pytest.fixture(autouse=True)
def _clean_hitl_waiters() -> Iterator[None]:
    """Guarantee a clean waiter registry around each test (real pipelines
    register themselves; leaked entries would cross-contaminate asserts)."""
    with _hitl_lock:
        _hitl_waiters.clear()
    yield
    with _hitl_lock:
        _hitl_waiters.clear()


@pytest.fixture(autouse=True)
def _audit_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect the user config dir so audit-log asserts are hermetic and
    allowlist the temp projects root so show_diff can resolve the project
    (mirrors test_gate_report_tool's cache-poke pattern)."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "projects"))
    _reset_allowlist_cache()
    import automedia.mcp.server as _server_mod

    _server_mod._cached_allowlist = [str(tmp_path.resolve())]
    yield config_dir
    _reset_allowlist_cache()
    monkeypatch.delenv("AUTOMEDIA_PROJECTS_DIR")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pause_h0_pipeline(
    project_id: str,
) -> tuple[GateEngine, PipelineProgress, threading.Thread, dict[str, Any]]:
    """Start a REAL H0 pipeline in a daemon thread and wait until it is
    paused at the HITL wait (registered in ``_hitl_waiters``)."""
    engine = GateEngine([H0HumanReviewGate()])
    progress = PipelineProgress(project_id=project_id)
    results: dict[str, Any] = {"done": False, "return_value": None, "error": None}

    def _run() -> None:
        try:
            results["return_value"] = engine.run(
                {"topic": "review-decision-test", "skip_review": False},
                progress=progress,
            )
        except Exception as exc:
            results["error"] = exc
        finally:
            results["done"] = True

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with _hitl_lock:
            waiter = _hitl_waiters.get(project_id)
        if waiter is not None:
            break
        if results["done"]:
            raise AssertionError("pipeline finished without ever pausing at H0")
        time.sleep(0.01)
    else:
        raise AssertionError("pipeline never registered in _hitl_waiters")

    return engine, progress, thread, results


def _seed_project_with_diff_record(
    tmp_path: Path,
    project_id: str,
    *,
    gate: str = "G1",
    before: str = "ORIGINAL",
    after: str = "MODIFIED",
) -> Path:
    """Seed a todo-8 style diff record under <project_dir>/.automedia/gate_diffs/."""
    project_dir = tmp_path / "projects" / f"20260905_review_{project_id}"
    diffs_dir = project_dir / ".automedia" / "gate_diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "gate": gate,
        "timestamp": "2026-09-05T00:00:00+00:00",
        "before": before,
        "after": after,
        "reasons": [{"name": "ai_taste", "passed": False, "detail": "still robotic"}],
        "error": "AI patterns detected",
        "applied": True,
        "truncated": False,
    }
    (diffs_dir / f"{gate}_1.json").write_text(json.dumps(record), encoding="utf-8")
    info = {
        "project_id": project_id,
        "topic": "review-diff-test",
        "brand": "test-brand",
        "tenant_id": "default",
        "created_at": "2026-09-05T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")
    return project_dir


# =========================================================================
# Tests: approve / reject on the LIVE pause path
# =========================================================================


class TestReviewDecisionApprove:
    def test_approve_resumes_paused_pipeline(self, _audit_dir: Path) -> None:
        project_id = "rvw-approve01"
        _seed_project_with_diff_record(Path(str(_audit_dir)).parent, project_id)
        _, _, thread, results = _pause_h0_pipeline(project_id)

        result = review_decision(project_id=project_id, gate_name="H0", action="approve")

        assert result["success"] is True
        assert result["approved"] is True
        assert result["gate_name"] == "H0"
        thread.join(timeout=5.0)
        assert results["done"], "paused pipeline thread did not resume"
        ok, gate_results = results["return_value"]
        assert ok is True
        assert gate_results[0].get("_hitl_approved") is True

    def test_approve_not_paused_returns_structured_error(self, _audit_dir: Path) -> None:
        result = review_decision(project_id="rvw-notpaus1", gate_name="H0", action="approve")
        assert result["success"] is False
        error = result["error"]
        assert error["code"] == "NOT_FOUND"
        combined = error["message"] + " " + error["resolution"]
        assert "same process" in combined.lower() or "separate process" in combined.lower()
        # Fast rejection — no wait, no deadlock.
        assert "review_decision" in combined


class TestReviewDecisionReject:
    def test_reject_halts_pipeline(self, _audit_dir: Path) -> None:
        project_id = "rvw-reject001"
        _seed_project_with_diff_record(Path(str(_audit_dir)).parent, project_id)
        _, _, thread, results = _pause_h0_pipeline(project_id)

        result = review_decision(
            project_id=project_id,
            gate_name="H0",
            action="reject",
            reason="tone is off-brand",
        )

        assert result["success"] is True
        assert result["rejected"] is True
        thread.join(timeout=5.0)
        assert results["done"], "pipeline did not finish after reject"
        ok, gate_results = results["return_value"]
        # Part A semantics: the run itself FAILS on reject.
        assert ok is False
        assert gate_results[0]["passed"] is False
        assert gate_results[0].get("_hitl_approved") is False

    def test_reject_not_paused_returns_structured_error(self, _audit_dir: Path) -> None:
        result = review_decision(
            project_id="rvw-notpaus2",
            gate_name="H0",
            action="reject",
            reason="n/a",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"


class TestReviewDecisionValidation:
    def test_invalid_action_returns_error(self, _audit_dir: Path) -> None:
        result = review_decision(
            project_id="rvw-badact01",
            gate_name="H0",
            action="maybe",  # type: ignore[arg-type] — intentionally invalid
        )
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_PARAM"

    def test_waiter_left_registered_after_error(self, _audit_dir: Path) -> None:
        with _hitl_lock:
            before = dict(_hitl_waiters)
        review_decision(project_id="rvw-nowaiter", gate_name="H0", action="approve")
        with _hitl_lock:
            assert _hitl_waiters == before


# =========================================================================
# Tests: show_diff
# =========================================================================


class TestReviewDecisionShowDiff:
    def test_show_diff_false_omits_diff(self, _audit_dir: Path) -> None:
        project_id = "rvw-nodiff01"
        tmp = Path(str(_audit_dir)).parent
        _seed_project_with_diff_record(tmp, project_id)
        _, _, thread, results = _pause_h0_pipeline(project_id)

        result = review_decision(project_id=project_id, gate_name="H0", action="approve")

        thread.join(timeout=5.0)
        assert results["done"]
        assert "diff" not in result
        assert "diff_unavailable" not in result

    def test_show_diff_true_renders_unified_diff(self, _audit_dir: Path) -> None:
        project_id = "rvw-showdiff1"
        tmp = Path(str(_audit_dir)).parent
        _seed_project_with_diff_record(tmp, project_id)
        _, _, thread, results = _pause_h0_pipeline(project_id)

        result = review_decision(
            project_id=project_id,
            gate_name="H0",
            action="approve",
            show_diff=True,
        )

        thread.join(timeout=5.0)
        assert results["done"]
        assert result["success"] is True
        assert result["diff_unavailable"] is False
        diff_text: str = result["diff"]
        assert "-ORIGINAL" in diff_text
        assert "+MODIFIED" in diff_text
        assert "---" in diff_text and "+++" in diff_text
        assert result["diff_record_path"].endswith("G1_1.json")

    def test_show_diff_true_without_record(self, _audit_dir: Path) -> None:
        project_id = "rvw-norecord"
        tmp = Path(str(_audit_dir)).parent
        project_dir = tmp / "projects" / f"20260905_review_{project_id}"
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "00_project_info.json").write_text(
            json.dumps({"project_id": project_id}), encoding="utf-8"
        )
        _, _, thread, results = _pause_h0_pipeline(project_id)

        result = review_decision(
            project_id=project_id,
            gate_name="H0",
            action="approve",
            show_diff=True,
        )

        thread.join(timeout=5.0)
        assert results["done"]
        assert result["success"] is True
        assert result["diff_unavailable"] is True
        assert "diff" not in result

    def test_show_diff_unknown_project_reports_unavailable_on_error(self, _audit_dir: Path) -> None:
        """show_diff on a not-paused project still fails fast with the
        structured error (diff resolution never blocks the error path)."""
        result = review_decision(
            project_id="rvw-nopaussd",
            gate_name="H0",
            action="approve",
            show_diff=True,
        )
        assert result["success"] is False


# =========================================================================
# Tests: audit log
# =========================================================================


class TestReviewDecisionAuditLog:
    def test_approve_appends_audit_line(self, _audit_dir: Path) -> None:
        project_id = "rvw-auditap1"
        tmp = Path(str(_audit_dir)).parent
        _seed_project_with_diff_record(tmp, project_id)
        _, _, thread, _results = _pause_h0_pipeline(project_id)

        review_decision(project_id=project_id, gate_name="H0", action="approve")
        thread.join(timeout=5.0)

        log_file = _audit_dir / "audit" / "review_decisions.log"
        assert log_file.is_file()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["project_id"] == project_id
        assert entry["gate_name"] == "H0"
        assert entry["decision"] == "approve"
        assert entry["actor"] == "mcp"
        assert entry["timestamp"]

    def test_reject_appends_audit_line_with_reason(self, _audit_dir: Path) -> None:
        project_id = "rvw-auditrj1"
        tmp = Path(str(_audit_dir)).parent
        _seed_project_with_diff_record(tmp, project_id)
        _, _, thread, _results = _pause_h0_pipeline(project_id)

        review_decision(
            project_id=project_id,
            gate_name="H0",
            action="reject",
            reason="not on brand",
        )
        thread.join(timeout=5.0)

        log_file = _audit_dir / "audit" / "review_decisions.log"
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[-1])
        assert entry["decision"] == "reject"
        assert entry["reason"] == "not on brand"

    def test_audit_failure_never_fails_review(
        self, _audit_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import automedia.decision.review_audit as review_audit

        project_id = "rvw-auditfail"

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(review_audit, "record_review_decision", _boom)
        _, _, thread, results = _pause_h0_pipeline(project_id)

        result = review_decision(project_id=project_id, gate_name="H0", action="approve")

        thread.join(timeout=5.0)
        assert results["done"]
        assert result["success"] is True
        assert result["approved"] is True


# =========================================================================
# Tests: server registration
# =========================================================================


class TestReviewDecisionRegistration:
    def test_tool_registered_on_server(self) -> None:
        from automedia.mcp.server import create_server

        server = create_server()
        assert "review_decision" in server._tool_manager._tools

    def test_health_count_is_68(self) -> None:
        from automedia.mcp.tools import health_check

        result = health_check()
        assert result["tools_count"] == 68
