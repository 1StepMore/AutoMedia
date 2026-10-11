"""Unit tests for the video-track gate evidence (issue #181, scripts/nightly_gap.py).

Fixtures are synthetic (Red Line 4): each test builds a throwaway project tree
under ``tmp_path`` (never the real repo) holding a ``03_video/output.mp4`` and a
gate-report shaped exactly like the production one (``generated_at`` / ``gates``
/ ``summary``).  ``scan_projects`` is always called with an explicit ``root`` so
the real ``REPO`` is never touched or mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.nightly_gap import scan_projects, video_gate_evidence

V_GATES = ("V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7")
MUST_RUN = ("V2", "V5", "V7")
DEBT = ("V0", "V1", "V3", "V4", "V6")


def _report(
    passed: list[str], failed: list[str], generated_at: str = "2026-01-01T00:00:00+00:00"
) -> dict:
    """A gate-report doc: named gates get their status, the rest become skipped."""
    gates = []
    for name in V_GATES:
        if name in passed:
            status = "passed"
        elif name in failed:
            status = "failed"
        else:
            status = "skipped"
        gates.append(
            {
                "gate": name,
                "status": status,
                "verdict": "pass" if status == "passed" else status,
                "error": None,
            }
        )
    counts = {
        "passed": len(passed),
        "failed": len(failed),
        "errored": 0,
        "skipped": len(V_GATES) - len(passed) - len(failed),
    }
    return {
        "project_dir": "synthetic",
        "generated_at": generated_at,
        "gates": gates,
        "summary": {"total": len(V_GATES), **counts},
        "blocked_by_gate": None,
        "blocked_by": None,
    }


def _project(
    root: Path,
    name: str = "20260101_demo-topic",
    video_bytes: int = 10 * 1024,
    reports: list[tuple[str, dict]] | None = None,
    draft_bytes: int = 800,
    cost_lines: int = 1,
    image_bytes: int = 0,
) -> Path:
    """Build one synthetic project; ``reports`` is a list of (timestamp, doc).

    ``draft_bytes`` / ``cost_lines`` default to a project that HAS text-track
    evidence, which is what a real run leaves behind. Pass 0 to model a stage
    directory that skipped the text track (issue #195).
    """
    proj = root / name
    proj.mkdir(parents=True, exist_ok=True)
    if draft_bytes:
        d_dir = proj / "01_content" / "drafts"
        d_dir.mkdir(parents=True, exist_ok=True)
        (d_dir / "draft.md").write_bytes(b"0" * draft_bytes)
    if cost_lines:
        (proj / "cost_log.jsonl").write_text(
            "".join(f'{{"call": {i}}}\n' for i in range(cost_lines)), encoding="utf-8"
        )
    if image_bytes:
        i_dir = proj / "02_images"
        i_dir.mkdir(parents=True, exist_ok=True)
        (i_dir / "cover.png").write_bytes(b"0" * image_bytes)
    if video_bytes:
        video_dir = proj / "03_video"
        video_dir.mkdir(parents=True, exist_ok=True)
        (video_dir / "output.mp4").write_bytes(b"0" * video_bytes)
    if reports is not None:
        gr_dir = proj / "05_review" / "gate-report"
        gr_dir.mkdir(parents=True, exist_ok=True)
        for ts, doc in reports:
            (gr_dir / f"gate-report-{ts}.json").write_text(
                json.dumps(doc, ensure_ascii=False), encoding="utf-8"
            )
    return proj


def _one(root: Path) -> dict:
    projects = scan_projects(root=root)
    assert len(projects) == 1
    return projects[0]


# ── 达标：带能力债 ────────────────────────────────────────────────────────────


def test_video_ok_with_debt_skips(tmp_path: Path) -> None:
    _project(tmp_path, reports=[("2026-01-01T00:00:00+0000", _report(list(MUST_RUN), []))])
    p = _one(tmp_path)
    assert p["video_ok"] is True
    gates = p["video_gates"]
    assert gates["ok"] is True
    assert gates["reason"] == ""
    assert gates["debt_skipped"] == ["V0", "V1", "V3", "V4", "V6"]
    assert gates["passed"] == ["V2", "V5", "V7"]
    assert gates["failed"] == gates["errored"] == gates["other"] == []
    assert gates["missing"] == []
    assert gates["report"] == ("05_review/gate-report/gate-report-2026-01-01T00:00:00+0000.json")


# ── 「同上」继承：图文/视频轨共用文本轨证据子句（issue #195）────────────────


def test_image_ok_with_full_evidence(tmp_path: Path) -> None:
    _project(tmp_path, image_bytes=2 * 1024)
    p = _one(tmp_path)
    assert p["text_evidence_ok"] is True
    assert p["image_ok"] is True


def test_image_red_when_cost_log_empty(tmp_path: Path) -> None:
    """一张图 + 零真模型记录曾被判达标——正是 #195 记的假绿口子。"""
    _project(tmp_path, image_bytes=2 * 1024, cost_lines=0)
    p = _one(tmp_path)
    assert p["text_evidence_ok"] is False
    assert p["image_max_bytes"] == 2 * 1024
    assert p["image_ok"] is False


def test_image_red_when_draft_too_small(tmp_path: Path) -> None:
    _project(tmp_path, image_bytes=2 * 1024, draft_bytes=100)
    p = _one(tmp_path)
    assert p["text_evidence_ok"] is False
    assert p["image_ok"] is False


def test_video_red_when_cost_log_empty(tmp_path: Path) -> None:
    """video_gates ok 而 video_ok 假，说明拦下它的是文本证据子句而非门证据。"""
    _project(
        tmp_path,
        cost_lines=0,
        reports=[("2026-01-01T00:00:00+0000", _report(list(MUST_RUN), []))],
    )
    p = _one(tmp_path)
    assert p["video_gates"]["ok"] is True
    assert p["text_evidence_ok"] is False
    assert p["video_ok"] is False


def test_image_red_when_no_image(tmp_path: Path) -> None:
    _project(tmp_path, image_bytes=0)
    p = _one(tmp_path)
    assert p["text_evidence_ok"] is True
    assert p["image_ok"] is False


def test_image_ok_implies_text_ok(tmp_path: Path) -> None:
    _project(tmp_path, image_bytes=2 * 1024)
    p = _one(tmp_path)
    assert p["image_ok"] is True
    assert p["text_ok"] is True


def test_video_red_when_all_gates_skipped(tmp_path: Path) -> None:
    """全 skipped 的报告不能再靠文件大小蒙混过关——正是 #181 的假绿。"""
    _project(tmp_path, reports=[("2026-01-01T00:00:00+0000", _report([], []))])
    p = _one(tmp_path)
    assert p["video_ok"] is False
    assert p["video_gates"]["reason"].startswith("must-run gate not passed")
    assert p["video_gates"]["passed"] == []


def test_video_red_when_must_run_gate_skipped(tmp_path: Path) -> None:
    _project(tmp_path, reports=[("2026-01-01T00:00:00+0000", _report(["V5", "V7"], []))])
    p = _one(tmp_path)
    assert p["video_ok"] is False
    assert "not passed: V2" in p["video_gates"]["reason"]


def test_video_red_when_gate_failed(tmp_path: Path) -> None:
    _project(tmp_path, reports=[("2026-01-01T00:00:00+0000", _report(list(MUST_RUN), ["V3"]))])
    p = _one(tmp_path)
    assert p["video_ok"] is False
    assert "gate failed: V3" in p["video_gates"]["reason"]


def test_video_red_when_no_gate_report(tmp_path: Path) -> None:
    proj = _project(tmp_path, reports=None)
    ev = video_gate_evidence(proj)
    assert ev["ok"] is False
    assert ev["reason"] == "no gate-report"
    assert ev["report"] == ""
    assert _one(tmp_path)["video_ok"] is False


def test_video_red_when_file_too_small(tmp_path: Path) -> None:
    """门证据合规，但视频只有 5KB → 仍判红（文件下限这一半没放松）。"""
    _project(
        tmp_path,
        video_bytes=5 * 1024,
        reports=[("2026-01-01T00:00:00+0000", _report(list(MUST_RUN), []))],
    )
    p = _one(tmp_path)
    assert p["video_max_bytes"] == 5 * 1024
    assert p["video_gates"]["ok"] is True
    assert p["video_ok"] is False


def test_latest_report_wins(tmp_path: Path) -> None:
    """旧报告 V2 failed、新报告合规 → 取 generated_at 最大的那份，判绿。"""
    proj = _project(
        tmp_path,
        reports=[
            (
                "2026-01-01T00:00:00+0000",
                _report(["V5", "V7"], ["V2"], generated_at="2026-01-01T00:00:00+00:00"),
            ),
            (
                "2026-01-02T00:00:00+0000",
                _report(list(MUST_RUN), [], generated_at="2026-01-02T00:00:00+00:00"),
            ),
        ],
    )
    ev = video_gate_evidence(proj)
    assert ev["report"].endswith("gate-report-2026-01-02T00:00:00+0000.json")
    assert ev["reason"] == ""
    assert ev["passed"] == ["V2", "V5", "V7"]
    p = _one(tmp_path)
    assert p["video_ok"] is True
