"""RED-phase tests for the pipeline state view (graph-engineering-rollout Wave 3, Todo 9).

The module does not exist yet — this file pins the contract for
``aggregate_pipeline_state`` and ``GateState``, which Todo 10 will implement.
Importing them is expected to fail with ``ImportError`` until Todo 10 lands
(RED phase).

Pinned aggregation contract (the spec)
--------------------------------------
``aggregate_pipeline_state(project_dir: str, mode: str = "auto") -> list[GateState]``
where ``GateState`` is a dataclass with fields:

* ``gate``: str — the gate name
* ``status``: Literal["passed", "failed", "pending"]
* ``track``: str — from ``AUTO_GATE_DAG[gate].track``
* ``md5``: str | None — from ``pipeline_md5.json``, present only for
  asset-producing gates
* ``recorded_at``: str | None — from ``pipeline_md5.json recorded_at``

Status determination (best-effort, READ-ONLY — Metis G3/G8):

* For each gate in ``_MODE_MAP[mode]`` (in ``_MODE_MAP`` order):
  * **passed**: the latest history row (by id) for that gate has action
    ``"{gate}:completed"`` AND ``metadata_json.passed == true``
  * **failed**: the latest history row for that gate is ``"{gate}:completed"``
    with ``passed: false``, OR ``"{gate}:failed"``
  * **pending**: no ``completed``/``failed`` row for that gate (only
    ``started`` or nothing at all)
  * **"latest row per gate wins"**: if a gate has multiple ``completed`` rows,
    the LAST (highest id) determines status.
* ``md5``/``recorded_at``: from ``get_pipeline_md5(project_dir)["gates"][gate]``
  if present, else None.
* ``track``: from ``AUTO_GATE_DAG[gate].track``.

The function is READ-ONLY: it aggregates from the existing ``history.db`` and
``pipeline_md5.json``. It performs NO new state writes. Best-effort: no
run-boundary segmentation — the latest ``completed`` row per gate wins.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from pathlib import Path

from automedia.hooks.md5_tracker import record_md5
from automedia.hooks.pipeline_history import _db_path, _ensure_schema
from automedia.pipelines.dag import AUTO_GATE_DAG
from automedia.pipelines.runner import _MODE_MAP
from automedia.pipelines.state_view import GateState, aggregate_pipeline_state

PROJECT_ID = "test-proj-001"


# =========================================================================
# Seeding helper (adapted from tests/test_runner/test_auto_resume.py:45-107)
# =========================================================================


def _create_project_with_history(
    project_dir: Path,
    project_id: str,
    rows: list[tuple[str, bool | None]],
) -> str:
    """Create a project directory with a seeded ``.automedia/history.db``.

    Parameters
    ----------
    project_dir:
        Directory to create (e.g. ``tmp_path / "20260707_test-topic"``).
    project_id:
        Value for the ``project_id`` column and ``00_project_info.json``.
    rows:
        Ordered list of ``(action, passed_or_None)`` tuples, one history row
        each, inserted in order (ascending ``id``).  ``passed`` values become
        ``metadata_json["passed"]`` (``None`` omits the key — matching
        ``started`` rows which carry no ``passed`` field).  Every row's
        ``metadata_json`` includes ``"gate"`` and ``"project_id"``, matching
        what ``PipelineHistoryHook`` writes.

    Returns
    -------
    str
        The project directory as a string (the helper's first parameter).
    """
    project_dir.mkdir(parents=True, exist_ok=True)

    info = {
        "project_id": project_id,
        "topic": "Test Topic",
        "brand": "TestBrand",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

    db_file = Path(_db_path(str(project_dir)))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        _ensure_schema(conn)
        base_ts = time.time()
        for i, (action, passed) in enumerate(rows):
            gate_name = action.split(":", 1)[0]
            meta: dict[str, object] = {"gate": gate_name, "project_id": project_id}
            if passed is not None:
                meta["passed"] = passed
            conn.execute(
                "INSERT INTO pipeline_history (project_id, action, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (project_id, action, base_ts + i, json.dumps(meta, ensure_ascii=False)),
            )
        conn.commit()
    finally:
        conn.close()

    return str(project_dir)


def _completed(gate: str) -> tuple[str, bool | None]:
    """A ``{gate}:completed`` row with ``passed: true``."""
    return (f"{gate}:completed", True)


# =========================================================================
# Tests
# =========================================================================


class TestMixedHistoryAggregation:
    """Core aggregation across a mixed passed/failed/pending history."""

    def test_state_for_mixed_history(self, tmp_path: Path) -> None:
        """G0 passed (with md5), G2 completed+failed, V1 only started, V0 no
        rows → each maps to its status; all 22 auto gates get a row."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [
                ("pre-gate:completed", True),
                ("CW:completed", True),
                _completed("G0"),
                ("G2:completed", False),
                ("V1:started", None),
            ],
        )

        # Seed pipeline_md5.json for G0 via the real tracker (writes
        # gates.G0.{file_path, md5, recorded_at} with an ISO recorded_at).
        asset = Path(project_dir) / "article.md"
        asset.write_text("draft content", encoding="utf-8")
        seeded_md5 = record_md5(project_dir, "G0", str(asset))

        result = aggregate_pipeline_state(project_dir, "auto")

        # G0 → passed, with md5 metadata from pipeline_md5.json.
        g0 = next(row for row in result if row.gate == "G0")
        assert g0.status == "passed"
        assert g0.md5 == seeded_md5
        assert g0.recorded_at is not None
        assert g0.track == "copy"

        # G2 → failed (completed row with passed: false).
        g2 = next(row for row in result if row.gate == "G2")
        assert g2.status == "failed"
        assert g2.track == "copy"

        # V1 → pending (only a `started` row, no completed/failed).
        v1 = next(row for row in result if row.gate == "V1")
        assert v1.status == "pending"
        assert v1.track == "video"

        # V0 → pending (no history rows at all).
        v0 = next(row for row in result if row.gate == "V0")
        assert v0.status == "pending"

        # Every gate in the mode list gets a row — none dropped.
        assert len(result) == len(_MODE_MAP["auto"])
        assert {row.gate for row in result} == set(_MODE_MAP["auto"])

    def test_completed_passed_false_is_failed(self, tmp_path: Path) -> None:
        """A lone ``{gate}:completed`` row with ``passed: false`` → failed.

        This is where retry-exhausted gates land (gate_engine writes
        ``completed`` with passed=false after retries are exhausted)."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [("G2:completed", False)],
        )

        result = aggregate_pipeline_state(project_dir, "auto")

        g2 = next(row for row in result if row.gate == "G2")
        assert g2.status == "failed"

    def test_failed_action_row_is_failed(self, tmp_path: Path) -> None:
        """A ``{gate}:failed`` row (gate raised) → failed."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [("V1:failed", None)],
        )

        result = aggregate_pipeline_state(project_dir, "auto")

        v1 = next(row for row in result if row.gate == "V1")
        assert v1.status == "failed"

    def test_md5_absent_for_non_asset_gates(self, tmp_path: Path) -> None:
        """Gates with no entry in pipeline_md5.json → md5/recorded_at None.

        Most quality gates produce no asset, so their md5 is None even when
        other gates have records in the same project."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("G0"), _completed("G1")],
        )
        asset = Path(project_dir) / "article.md"
        asset.write_text("draft content", encoding="utf-8")
        record_md5(project_dir, "G0", str(asset))

        result = aggregate_pipeline_state(project_dir, "auto")

        g1 = next(row for row in result if row.gate == "G1")
        assert g1.md5 is None
        assert g1.recorded_at is None


class TestLatestRowWins:
    """The 'latest row per gate wins' tie-break."""

    def test_latest_completed_row_wins(self, tmp_path: Path) -> None:
        """G0 completed+passed (id 1), then G0 completed+failed (id 2) →
        failed. The LAST (highest id) completed row determines status."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [
                _completed("G0"),  # id 1: completed, passed=true
                ("G0:completed", False),  # id 2: completed, passed=false
            ],
        )

        result = aggregate_pipeline_state(project_dir, "auto")

        g0 = next(row for row in result if row.gate == "G0")
        assert g0.status == "failed"

    def test_latest_completed_row_wins_reverse_order(self, tmp_path: Path) -> None:
        """Mirror of the above: G0 completed+failed (id 1), then G0
        completed+passed (id 2) → passed."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [
                ("G0:completed", False),  # id 1: completed, passed=false
                _completed("G0"),  # id 2: completed, passed=true
            ],
        )

        result = aggregate_pipeline_state(project_dir, "auto")

        g0 = next(row for row in result if row.gate == "G0")
        assert g0.status == "passed"


class TestEmptyProject:
    """No history and no md5 → best-effort all-pending view."""

    def test_empty_project_all_pending(self, tmp_path: Path) -> None:
        """No history.db, no pipeline_md5.json → all 22 auto gates pending
        with md5 None (not an exception)."""
        project_dir_obj = tmp_path / "20260707_test-topic"
        project_dir_obj.mkdir(parents=True)
        info = {"project_id": PROJECT_ID, "topic": "Test Topic", "brand": "TestBrand"}
        (project_dir_obj / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = aggregate_pipeline_state(str(project_dir_obj), "auto")

        assert len(result) == len(_MODE_MAP["auto"])
        assert all(row.status == "pending" for row in result)
        assert all(row.md5 is None for row in result)
        assert all(row.recorded_at is None for row in result)


class TestModeSubset:
    """The mode parameter scopes the returned gate list."""

    def test_mode_subset(self, tmp_path: Path) -> None:
        """``qa_only`` returns exactly the 5 qa_only gates, one row each."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("G0"), _completed("G2")],
        )

        result = aggregate_pipeline_state(project_dir, "qa_only")

        assert [row.gate for row in result] == _MODE_MAP["qa_only"]
        assert len(result) == 5
        statuses = {row.gate: row.status for row in result}
        assert statuses == {
            "G0": "passed",
            "G2": "passed",
            "G3": "pending",
            "V1": "pending",
            "V6": "pending",
        }


class TestTrackAssignment:
    """Track comes from AUTO_GATE_DAG."""

    def test_track_assignment(self, tmp_path: Path) -> None:
        """G0→copy, V1→video, H0→qa (auto preset; lifecycle is DAG-only now)."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("G0"), _completed("V1"), _completed("H0")],
        )

        result = aggregate_pipeline_state(project_dir, "auto")

        by_gate = {row.gate: row for row in result}
        assert by_gate["G0"].track == "copy"
        assert by_gate["V1"].track == "video"
        assert by_gate["H0"].track == "qa"
        assert AUTO_GATE_DAG["L1"].track == "lifecycle"
        # And it mirrors the DAG exactly for every gate in the mode.
        for row in result:
            assert row.track == AUTO_GATE_DAG[row.gate].track


class TestOrderMatchesModeMap:
    """The returned list order follows _MODE_MAP[mode]."""

    def test_order_matches_mode_map(self, tmp_path: Path) -> None:
        """Gate order == _MODE_MAP[mode] order for auto and qa_only,
        regardless of the order rows were inserted in history."""
        # Seeded in reverse order — the view must NOT follow insertion order.
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [
                ("V1:started", None),
                ("G2:completed", False),
                _completed("G0"),
                ("CW:completed", True),
                ("pre-gate:completed", True),
            ],
        )

        for mode in ("auto", "qa_only", "text_only"):
            result = aggregate_pipeline_state(project_dir, mode)
            assert [row.gate for row in result] == _MODE_MAP[mode]


class TestGateStateShape:
    """GateState is a dataclass with exactly the 5 pinned fields."""

    def test_gate_state_is_dataclass(self, tmp_path: Path) -> None:
        """Rows are GateState instances with the 5 fields (and only those)."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("G0")],
        )

        result = aggregate_pipeline_state(project_dir, "auto")

        assert len(result) == len(_MODE_MAP["auto"])
        for row in result:
            assert isinstance(row, GateState)
            assert dataclasses.is_dataclass(row)
            field_names = [f.name for f in dataclasses.fields(row)]
            assert field_names == ["gate", "status", "track", "md5", "recorded_at"]

    def test_default_mode_is_auto(self, tmp_path: Path) -> None:
        """``aggregate_pipeline_state(dir)`` defaults to mode ``"auto"``."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("G0")],
        )

        with_default = aggregate_pipeline_state(project_dir)
        explicit = aggregate_pipeline_state(project_dir, "auto")

        assert [row.gate for row in with_default] == [row.gate for row in explicit]
        assert [row.status for row in with_default] == [row.status for row in explicit]


class TestMissingHistoryDb:
    """Missing history.db is a state, not an error."""

    def test_missing_history_db_returns_all_pending(self, tmp_path: Path) -> None:
        """Directory with no ``.automedia/history.db`` → all 22 gates pending
        (never raises)."""
        project_dir_obj = tmp_path / "20260707_bare-project"
        project_dir_obj.mkdir(parents=True)

        result = aggregate_pipeline_state(str(project_dir_obj), "auto")

        assert len(result) == len(_MODE_MAP["auto"])
        assert all(row.status == "pending" for row in result)
        assert [row.gate for row in result] == _MODE_MAP["auto"]
