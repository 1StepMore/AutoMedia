"""RED-phase tests for the ``--auto-resume`` feature (graph-engineering-rollout Wave 2, Todo 6).

The feature does not exist yet in ``runner.py`` — this file pins the contract for
``_find_auto_resume_point``, the helper Todo 7 will implement.  Importing it is
expected to fail with ``ImportError`` until Todo 7 lands (RED phase).

Pinned resume semantic (Momus blocker #2)
-----------------------------------------
* anchor = the LATEST history row (by ``id``) with action ``"{gate}:completed"``
  AND ``metadata_json.passed == true``
* resume point = ``gate_names[gate_names.index(anchor) + 1]`` — the gate AFTER
  the last passed gate, so a failed gate following the anchor IS re-run.
* A ``completed`` row with ``passed: false`` does NOT anchor (retry-exhausted
  gates also land here; see ``PipelineHistoryHook.after_gate`` and
  ``gate_engine.py`` retry-exhaustion writes).
* The lookup computes against the EFFECTIVE ``gate_names`` list passed in
  (post-mode / post-modifiers), never the raw history gate set.

Integration concerns (explicit ``resume_from`` precedence over ``auto_resume``,
and ``auto_resume=False`` never auto-resuming) live in ``_run_pipeline`` wiring
and are covered by Todo 7's runner integration tests — not here.

The helper is the seam: ``run_full_pipeline`` performs real work (LLM, video,
render) and is never invoked end-to-end in unit tests.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from automedia.hooks.pipeline_history import _db_path, _ensure_schema
from automedia.pipelines.runner import _MODE_MAP, _find_auto_resume_point

PROJECT_ID = "test-proj-001"


# =========================================================================
# Seeding helper (adapted from tests/test_cli/test_history_cmd.py:28-60)
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


class TestFindAutoResumePoint:
    """Contract for ``_find_auto_resume_point(project_dir, mode, gate_names) -> str | None``.

    The helper reads ``.automedia/history.db`` via ``_read_history``, filters
    rows by ``project_id``, and returns the gate AFTER the latest passed gate.
    """

    # -- (a) anchor selection: latest passed completed row -------------------

    def test_anchor_is_latest_passed_completed_row(self, tmp_path: Path) -> None:
        """G0..G3 all completed+passed → anchor G3 → resume at G6."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed(g) for g in ["G0", "G1", "G2", "G3"]],
        )
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(project_dir, "auto", gate_names)

        assert result == "G6"

    # -- (a2) completed-with-failure does not anchor -------------------------

    def test_completed_with_passed_false_is_not_anchor(self, tmp_path: Path) -> None:
        """V0 passed; V1 completed with ``passed: false`` (failed check, not
        exception) → anchor stays V0 → resume at V1, re-running the failed
        gate."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [
                _completed("V0"),
                ("V1:completed", False),
            ],
        )
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(project_dir, "auto", gate_names)

        assert result == "V1"

    # -- (a3) raised gate (failed action) does not anchor ---------------------

    def test_failed_action_row_is_not_anchor(self, tmp_path: Path) -> None:
        """V0 passed; V1 raised (``V1:failed`` row, no completed row) → anchor
        stays V0 → resume at V1."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [
                _completed("V0"),
                ("V1:failed", None),
            ],
        )
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(project_dir, "auto", gate_names)

        assert result == "V1"

    # -- (b) fresh mid-pipeline seed ------------------------------------------

    def test_resumes_after_last_passed_gate(self, tmp_path: Path) -> None:
        """G0, G1 completed+passed → anchor G1 → resume at G2."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("G0"), _completed("G1")],
        )
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(project_dir, "auto", gate_names)

        assert result == "G2"

    # -- (c) no history → full run from start ---------------------------------

    def test_missing_history_db_returns_none(self, tmp_path: Path) -> None:
        """No ``history.db`` at all → ``None`` (run from the beginning)."""
        project_dir_obj = tmp_path / "20260707_test-topic"
        project_dir_obj.mkdir(parents=True)
        info = {"project_id": PROJECT_ID, "topic": "Test Topic", "brand": "TestBrand"}
        (project_dir_obj / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(str(project_dir_obj), "auto", gate_names)

        assert result is None

    def test_empty_history_returns_none(self, tmp_path: Path) -> None:
        """Existing ``history.db`` with zero rows → ``None``."""
        project_dir = _create_project_with_history(tmp_path / "20260707_test-topic", PROJECT_ID, [])
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(project_dir, "auto", gate_names)

        assert result is None

    def test_rows_for_other_project_id_are_ignored(self, tmp_path: Path) -> None:
        """History rows belonging to a different project_id must not anchor.

        The info file carries THIS project's id (``PROJECT_ID``); the history
        rows are seeded under a foreign id (``other-proj-999``) — the fixture
        must decouple the two so the "foreign rows" are genuinely foreign.
        """
        foreign_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic", "other-proj-999", [_completed("G3")]
        )
        info = {
            "project_id": PROJECT_ID,
            "topic": "Test Topic",
            "brand": "TestBrand",
            "tenant_id": "default",
            "created_at": "2026-07-07T00:00:00+00:00",
        }
        (Path(foreign_dir) / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(foreign_dir, "auto", gate_names)

        assert result is None

    # -- (d) anchor outside the effective gate list → None, never raise -------

    def test_anchor_not_in_gate_names_returns_none_no_valueerror(self, tmp_path: Path) -> None:
        """V3 passed but mode is ``text_only`` (no V gates) → ``None`` (full
        run).  MUST NOT raise ``ValueError`` (unlike explicit ``resume_from``)."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("V3")],
        )
        gate_names = _MODE_MAP["text_only"]

        result = _find_auto_resume_point(project_dir, "text_only", gate_names)

        assert result is None

    # -- (e) anchor is the last gate → nothing to resume ----------------------

    def test_anchor_is_last_gate_returns_none(self, tmp_path: Path) -> None:
        """H0 (auto's final gate) passed → ``index + 1`` out of range → ``None``."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("H0")],
        )
        gate_names = _MODE_MAP["auto"]

        result = _find_auto_resume_point(project_dir, "auto", gate_names)

        assert result is None

    # -- (h) effective-list pin: compute against the passed gate_names --------

    def test_resume_point_computed_against_effective_gate_list(self, tmp_path: Path) -> None:
        """The helper uses the PASSED ``gate_names`` (the effective list after
        mode/brand/workflow modifiers), not the raw mode list.

        Anchor G1 with G2 excluded from the effective list: the next gate in
        the effective list is G3, so that is what resume lands on.
        """
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("G0"), _completed("G1")],
        )
        effective = [g for g in _MODE_MAP["auto"] if g != "G2"]

        result = _find_auto_resume_point(project_dir, "auto", effective)

        assert result == "G3"

    def test_anchor_last_in_effective_list_returns_none(self, tmp_path: Path) -> None:
        """Anchor at the end of the EFFECTIVE list (even though later gates
        exist in the raw mode list) → ``None``, not an out-of-range error."""
        project_dir = _create_project_with_history(
            tmp_path / "20260707_test-topic",
            PROJECT_ID,
            [_completed("V3")],
        )
        # Effective list truncated right after V3.
        effective = _MODE_MAP["auto"][: _MODE_MAP["auto"].index("V3") + 1]

        result = _find_auto_resume_point(project_dir, "auto", effective)

        assert result is None
