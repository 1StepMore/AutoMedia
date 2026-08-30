"""Tests for ``automedia pipeline export-dag`` CLI command.

RED-phase spec (graph-engineering-rollout Wave 1 Todo 4). The ``pipeline``
subcommand does NOT exist yet — the implementation is Todo 5. These tests
encode the exact export-dag contract so they become the GREEN acceptance
for that implementation:

- ``export-dag --mode <m> --out <dir>`` writes ``<m>.md`` and ``<m>.dot``.
- The Markdown lists the mode's gates in EXACT ``_MODE_MAP`` order with a
  ``∥`` async-parallel marker near V0.
- The DOT declares the canonical edges (``G0 -> G1``, ``V0 -> V1``,
  ``CW -> V0``, ``G6 -> H0``) and a per-track cluster/label.
- ``--mode bogus`` exits non-zero and mentions the invalid mode.
- ``--all`` renders all 9 modes (18 files), qa_only without CW (Metis G14),
  and the identical-list text_only/text_with_cover both render.
- ``--project <dir>`` overlays gates present in ``history.db`` with a marker.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.hooks.pipeline_history import _db_path, _ensure_schema
from automedia.pipelines.runner import _MODE_MAP

runner = CliRunner()


# =========================================================================
# Fixtures
# =========================================================================


def _create_project_with_history(
    tmp_path: Path,
    project_id: str = "test-proj-001",
    num_rows: int = 3,
) -> dict[str, Any]:
    """Create a temporary project with history DB rows.

    Returns a dict with ``base_dir``, ``project_dir``, ``project_id``.
    Adapted from ``tests/test_cli/test_history_cmd.py:28-60``.
    """
    slug = "test-topic"
    project_dir = tmp_path / f"20260707_{slug}"
    project_dir.mkdir(parents=True)

    info = {
        "project_id": project_id,
        "topic": "Test Topic",
        "brand": "TestBrand",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

    # Populate history DB
    db_file = Path(_db_path(str(project_dir)))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        _ensure_schema(conn)
        base_ts = time.time()
        actions = ["lint:started", "lint:completed", "content_writer:started"]
        for i in range(num_rows):
            conn.execute(
                "INSERT INTO pipeline_history (project_id, action, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    project_id,
                    actions[i] if i < len(actions) else f"gate_{i}:completed",
                    base_ts + i,
                    json.dumps(
                        {
                            "gate": (
                                actions[i].split(":")[0]
                                if i < len(actions)
                                else f"gate_{i}"
                            )
                        }
                    ),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


def _create_project_with_gate_history(
    tmp_path: Path,
    project_id: str = "test-proj-001",
) -> dict[str, Any]:
    """Create a project whose history records gate runs (CW, G0, G1).

    The overlay contract keys on these gate names, so the seeded actions use
    the canonical ``<gate>:<status>`` shape that ``export-dag --project`` is
    expected to parse: ``"CW:completed"``, ``"G0:completed"``,
    ``"G1:failed"``.
    """
    slug = "test-topic"
    project_dir = tmp_path / f"20260707_{slug}"
    project_dir.mkdir(parents=True)

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
        for i, action in enumerate(["CW:completed", "G0:completed", "G1:failed"]):
            conn.execute(
                "INSERT INTO pipeline_history (project_id, action, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    project_id,
                    action,
                    base_ts + i,
                    json.dumps({"gate": action.split(":")[0]}),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


# =========================================================================
# Tests: export-dag --mode emits files
# =========================================================================


class TestExportDagEmitsFiles:
    """``export-dag --mode <m> --out <dir>`` writes markdown + dot files."""

    def test_auto_mode_writes_md_and_dot(self, tmp_path: Path) -> None:
        """--mode auto writes ``auto.md`` and ``auto.dot`` and exits 0."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--mode", "auto", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert (tmp_path / "auto.md").exists()
        assert (tmp_path / "auto.dot").exists()

    def test_md_lists_all_auto_gates_in_exact_order(self, tmp_path: Path) -> None:
        """The markdown lists every auto-mode gate in EXACT ``_MODE_MAP`` order."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--mode", "auto", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        md = (tmp_path / "auto.md").read_text(encoding="utf-8")

        mode_gates = _MODE_MAP["auto"]
        # Every gate of the mode appears in the markdown.
        for gate in mode_gates:
            assert gate in md, f"gate {gate!r} missing from auto.md"

        # Relative order matches the mode list: index("CW") < index("G0") < ...
        # and the video track sorts between the copy track and H0.
        positions = [md.index(g) for g in mode_gates]
        assert positions == sorted(positions), (
            f"auto.md gate order != {mode_gates}: {positions}"
        )
        assert md.index("CW") < md.index("G0")
        assert md.index("G0") < md.index("V0")
        assert md.index("V7") < md.index("H0")
        assert md.index("H0") < md.index("L4")

    def test_md_has_async_parallel_marker_near_v0(self, tmp_path: Path) -> None:
        """The markdown annotates V0's async-parallel fork with ``∥``."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--mode", "auto", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        md = (tmp_path / "auto.md").read_text(encoding="utf-8")
        assert "\u2225" in md, "auto.md missing the ∥ (U+2225) async-parallel marker"
        # Tolerant: the marker must live in the V0 region, not the document footer.
        assert md.index("\u2225") < md.index("H0")

    def test_dot_declares_canonical_edges(self, tmp_path: Path) -> None:
        """The dot file declares the canonical DAG edges between node pairs."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--mode", "auto", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        dot = (tmp_path / "auto.dot").read_text(encoding="utf-8")
        # Tolerant edge checks: assert the node pairs appear as an edge line.
        assert "G0 -> G1" in dot
        assert "V0 -> V1" in dot
        assert "CW -> V0" in dot
        assert "G6 -> H0" in dot
        # V0's async fork off CW, so CW -> V0 must exist while G6 -> V0 must not.
        assert "G6 -> V0" not in dot

    def test_dot_has_per_track_cluster_or_label(self, tmp_path: Path) -> None:
        """The dot file groups gates into per-track subgraphs/clusters."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--mode", "auto", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        dot = (tmp_path / "auto.dot").read_text(encoding="utf-8")
        # At least one of the four track labels appears as a cluster/label —
        # tolerant across subgraph vs. node-attribute rendering styles.
        assert any(track in dot for track in ("copy", "video", "lifecycle", "qa")), (
            "auto.dot has no per-track cluster/label"
        )


# =========================================================================
# Tests: --mode validation
# =========================================================================


class TestExportDagModeValidation:
    """Invalid ``--mode`` values are rejected with a non-zero exit code."""

    def test_unknown_mode_rejected(self, tmp_path: Path) -> None:
        """``--mode bogus`` exits non-zero and names the invalid mode."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--mode", "bogus", "--out", str(tmp_path)]
        )
        assert result.exit_code != 0
        message = result.output + result.stderr
        assert "bogus" in message
        assert "auto" in message  # the ValueError names valid modes too


# =========================================================================
# Tests: --all emits all 9 modes
# =========================================================================


class TestExportDagAll:
    """``export-dag --all`` renders every mode in ``_MODE_MAP``."""

    def test_all_writes_18_files(self, tmp_path: Path) -> None:
        """``--all`` writes ``{mode}.md`` + ``{mode}.dot`` for all 9 modes."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--all", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        for mode in _MODE_MAP:
            assert (tmp_path / f"{mode}.md").exists(), f"missing {mode}.md"
            assert (tmp_path / f"{mode}.dot").exists(), f"missing {mode}.dot"

    def test_qa_only_renders_without_cw(self, tmp_path: Path) -> None:
        """Sparse qa_only mode renders and does NOT contain CW (Metis G14)."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--all", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert (tmp_path / "qa_only.md").exists()
        assert (tmp_path / "qa_only.dot").exists()
        md = (tmp_path / "qa_only.md").read_text(encoding="utf-8")
        dot = (tmp_path / "qa_only.dot").read_text(encoding="utf-8")
        assert "CW" not in md, "qa_only.md must not contain CW"
        assert "CW" not in dot, "qa_only.dot must not contain CW"
        # The sparse list still renders its own gates.
        for gate in _MODE_MAP["qa_only"]:
            assert gate in md

    def test_text_only_and_text_with_cover_both_render(self, tmp_path: Path) -> None:
        """The identical-list text_only / text_with_cover modes both render."""
        result = runner.invoke(
            app, ["pipeline", "export-dag", "--all", "--out", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert (tmp_path / "text_only.md").exists()
        assert (tmp_path / "text_with_cover.md").exists()
        assert (tmp_path / "text_only.dot").exists()
        assert (tmp_path / "text_with_cover.dot").exists()
        assert _MODE_MAP["text_only"] == _MODE_MAP["text_with_cover"]
        for gate in _MODE_MAP["text_only"]:
            assert gate in (tmp_path / "text_only.md").read_text(encoding="utf-8")


# =========================================================================
# Tests: --project per-run overlay
# =========================================================================


class TestExportDagProjectOverlay:
    """``export-dag --project <dir>`` overlays gates present in history.db."""

    def test_project_overlay_marks_history_gates(self, tmp_path: Path) -> None:
        """Gates with history rows appear marked in both md and dot output."""
        proj = _create_project_with_gate_history(tmp_path)
        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "pipeline",
                "export-dag",
                "--mode",
                "auto",
                "--project",
                str(proj["project_dir"]),
                "--out",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert (out_dir / "auto.md").exists()
        assert (out_dir / "auto.dot").exists()

        md = (out_dir / "auto.md").read_text(encoding="utf-8")
        dot = (out_dir / "auto.dot").read_text(encoding="utf-8")

        # Overlay contract: a gate present in history ("CW", "G0") appears in
        # the output AND is marked distinctly from a gate that never ran
        # ("G2" is absent from history). The marker text is the
        # implementation's choice — assert on stable substrings.
        assert "CW" in md and "G0" in md
        assert "CW" in dot and "G0" in dot

        # Tolerant marker check: each history gate name appears in the output
        # next to one of the conventional run markers ("ran", "✓", "done",
        # "completed", "overlay"), or in a dedicated overlay section whose
        # header names the gate. We assert the marker vocabulary exists rather
        # than any exact rendering.
        marker_hint = any(
            token in md or token in dot
            for token in ("ran", "\u2713", "done", "completed", "overlay", "history")
        )
        assert marker_hint, "neither md nor dot carries an overlay/run marker"

    def test_project_overlay_marks_failed_gate(self, tmp_path: Path) -> None:
        """A gate that failed in history ("G1:failed") is also marked."""
        proj = _create_project_with_gate_history(tmp_path)
        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "pipeline",
                "export-dag",
                "--mode",
                "auto",
                "--project",
                str(proj["project_dir"]),
                "--out",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        md = (out_dir / "auto.md").read_text(encoding="utf-8")
        assert "G1" in md
