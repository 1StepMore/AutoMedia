"""resume_from must rehydrate the on-disk draft (issue #269)."""

from __future__ import annotations

import os
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from automedia.gates._context import GateContext
from automedia.pipelines.runner import _build_pipeline_context, _latest_draft, run_full_pipeline


def _project(project_dir: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(project_id="resume", project_dir=str(project_dir))


def _write_draft(project_dir: Path, name: str, text: str) -> Path:
    drafts = project_dir / "01_content" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    path = drafts / name
    path.write_text(text, encoding="utf-8")
    return path


def _context(
    project_dir: Path, gate_names: list[str], *, resume_from: str | None = "G0"
) -> GateContext:
    return _build_pipeline_context(
        "topic",
        "brand",
        "auto",
        _project(project_dir),
        {},
        "default",
        None,
        False,
        False,
        None,
        "",
        "",
        "corr",
        gate_names,
        resume_from=resume_from,
    )


def test_latest_draft_picks_newest_markdown(tmp_path: Path) -> None:
    older = _write_draft(tmp_path, "20261023_100000_draft.md", "older")
    newer = _write_draft(tmp_path, "20261023_110000_draft.md", "newer")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    assert _latest_draft(tmp_path) == newer


def test_latest_draft_returns_none_without_files(tmp_path: Path) -> None:
    assert _latest_draft(tmp_path) is None
    (tmp_path / "01_content" / "drafts").mkdir(parents=True)
    assert _latest_draft(tmp_path) is None


def test_resume_rehydrates_latest_draft(tmp_path: Path) -> None:
    _write_draft(tmp_path, "20261023_100000_draft.md", "  # Real draft\n\nBody.  ")
    context = _context(tmp_path, ["G0"])
    assert context["content"] == "# Real draft\n\nBody."
    assert context["draft"] == "# Real draft\n\nBody."


def test_resume_keeps_placeholder_without_draft(tmp_path: Path) -> None:
    context = _context(tmp_path, ["G0"])
    assert context["content"] == "[content skipped in auto mode]"
    assert context["draft"] == "[content skipped in auto mode]"


def test_cw_less_mode_rehydrates_without_resume_flag(tmp_path: Path) -> None:
    _write_draft(tmp_path, "20261023_100000_draft.md", "draft")
    context = _context(tmp_path, ["G0"], resume_from=None)
    assert context["content"] == "draft"


def test_cw_run_does_not_read_draft(tmp_path: Path) -> None:
    _write_draft(tmp_path, "20261023_100000_draft.md", "draft")
    context = _context(tmp_path, ["CW", "G0"])
    assert context["content"] == ""


class _CaptureGate:
    gate_name = "G0"
    failure_mode = "stop"

    def __init__(self, captured: dict[str, object]) -> None:
        self._captured = captured

    def execute(self, context: dict[str, object]) -> dict[str, object]:
        self._captured["content"] = context["content"]
        return {"passed": True, "gate": "G0", "checks": []}


def test_run_full_pipeline_resume_uses_draft(tmp_path: Path) -> None:
    _write_draft(tmp_path, "20261023_100000_draft.md", "resumed draft")
    captured: dict[str, object] = {}

    with (
        patch("automedia.core.config_loader.load_config", return_value={}),
        patch("automedia.core.project.Project") as project_cls,
        patch("automedia.pipelines.runner._build_gates_from_names") as build,
        patch("automedia.pipelines.runner._record_gate_md5s"),
    ):
        project = MagicMock()
        project.project_id = "resume-e2e"
        project.project_dir = str(tmp_path)
        project_cls.init.return_value = project
        build.return_value = [_CaptureGate(captured)]

        result = run_full_pipeline("topic", "brand", mode="auto", resume_from="G0")

    assert result.status == "success"
    assert captured["content"] == "resumed draft"
