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

from scripts.nightly_gap import (
    MIN_VIDEO_BYTES,
    _bench_line,
    _track_red_reason,
    _video_red_reason,
    _video_track_note,
    scan_projects,
    video_gate_evidence,
)

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
            # 文件名去冒号：Windows 文件名不允许 ``:``（真实报告名由 writer 生成，
            # 这里的 ts 只是标签，排序判据是报告内的 generated_at）。
            (gr_dir / f"gate-report-{ts.replace(':', '')}.json").write_text(
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
    assert gates["report"] == ("05_review/gate-report/gate-report-2026-01-01T000000+0000.json")


# ── 「同上」继承：图文/视频轨共用文本轨证据子句（issue #195）────────────────


def test_image_ok_with_full_evidence(tmp_path: Path) -> None:
    # #361：达标叠加门链结论——夹具带一份无 failed 行的干净报告。
    _project(
        tmp_path,
        image_bytes=2 * 1024,
        reports=[("2026-01-01T00:00:00+0000", _report(list(MUST_RUN), []))],
    )
    p = _one(tmp_path)
    assert p["gate_chain"]["ok"] is True
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
    _project(
        tmp_path,
        image_bytes=2 * 1024,
        reports=[("2026-01-01T00:00:00+0000", _report(list(MUST_RUN), []))],
    )
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
    assert ev["report"].endswith("gate-report-2026-01-02T000000+0000.json")
    assert ev["reason"] == ""
    assert ev["passed"] == ["V2", "V5", "V7"]
    p = _one(tmp_path)
    assert p["video_ok"] is True


# ── #235：判红原因按合取顺序，别把「没视频」伪装成 `no gate-report` ───────────


def test_red_reason_is_video_size_when_no_video(tmp_path: Path) -> None:
    """无视频的项目：原因必须是尺寸子句，而不是会被藏起候选的 `no gate-report`。"""
    _project(tmp_path, video_bytes=0, reports=None)
    p = _one(tmp_path)
    assert p["video_ok"] is False
    assert p["video_gates"]["reason"] == "no gate-report"
    assert _video_red_reason(p) == f"视频文件 <{MIN_VIDEO_BYTES}B"


def test_red_reason_is_text_evidence_when_missing(tmp_path: Path) -> None:
    """缺文本证据时取第一个 false 的子句——即使门证据本身违规。"""
    _project(tmp_path, cost_lines=0, video_bytes=0, reports=None)
    p = _one(tmp_path)
    assert _video_red_reason(p) == "缺文本证据（draft < 500B 或 cost_log 空）"


def test_red_reason_falls_through_to_gate_evidence(tmp_path: Path) -> None:
    """尺寸与文本都过、只差 V 门证据 → 用门证据自己的 reason。"""
    _project(tmp_path, reports=[("2026-01-01T00:00:00+0000", _report([], []))])
    p = _one(tmp_path)
    assert p["video_max_bytes"] >= MIN_VIDEO_BYTES
    assert p["text_evidence_ok"] is True
    assert p["video_gates"]["ok"] is False
    assert _video_red_reason(p).startswith("must-run gate not passed")


# ── #235：选样优先「离达标最近」的候选（尺寸降序），不再按项目名 ─────────────


def test_sampling_covers_nearest_candidates(tmp_path: Path) -> None:
    # 3 个近失候选：尺寸 + 文本都过，只差 V 门证据（报告全 skipped）。
    near_bytes = {
        "20260822_near-94kb": 94 * 1024,
        "20260822_near-4mb": 4900 * 1024,
        "20260822_near-7mb": 7800 * 1024,
    }
    for name, nbytes in near_bytes.items():
        _project(
            tmp_path,
            name=name,
            video_bytes=nbytes,
            reports=[("2026-01-01T00:00:00+0000", _report([], []))],
        )
    # 若干无关项目（字母序更靠前、无视频）——#361 起它们是 unverified，
    # 不进判红名单；这里验证「无证据的项目不再伪装成判红原因」。
    for i in range(6):
        _project(tmp_path, name=f"20260822_aaa-unrelated-{i}", video_bytes=0, reports=None)

    projects = scan_projects(root=tmp_path)
    note = _video_track_note(projects, {"ok": False})
    listed = note.split("：", 1)[1].split("；")
    assert len(listed) == 3
    for name in near_bytes:
        assert any(entry.startswith(name + ":") for entry in listed), name
    for i in range(6):
        assert not any(f"20260822_aaa-unrelated-{i}:" in entry for entry in listed)
    # 近失候选按 video_max_bytes 降序排在最前。
    near_order = [
        entry.split(":", 1)[0] for entry in listed if entry.split(":", 1)[0] in near_bytes
    ]
    assert near_order == [
        "20260822_near-7mb",
        "20260822_near-4mb",
        "20260822_near-94kb",
    ]


# ── #235：报告头部有 bench 行 ────────────────────────────────────────────────


def test_bench_line_shape() -> None:
    line = _bench_line()
    assert line.startswith("- bench：")
    assert "@" in line


def test_main_md_header_has_bench(tmp_path: Path, monkeypatch) -> None:
    from scripts import nightly_gap

    _project(tmp_path, video_bytes=0, reports=None)
    real_scan = nightly_gap.scan_projects
    monkeypatch.setattr(
        nightly_gap, "scan_projects", lambda root=None, extra_root=None: real_scan(root=tmp_path)
    )
    out = tmp_path / "gap.md"
    rc = nightly_gap.main(["--skip-validate", "--md-out", str(out)])
    assert rc == 1
    lines = out.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("- bench：") for line in lines[:6])


# ── #361：三轨达标必须叠加门链结论，并区分 pass / fail / unverified ──────────


def _g0_dead_report() -> dict:
    """G0 判死的报告（#361 现象：门说「这篇不能用」）。"""
    return {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "gates": [{"gate": "G0", "verdict": "fail", "status": "failed"}],
        "blocked_by_gate": "G0",
        "summary": {"total": 1, "passed": 0, "failed": 1, "errored": 0, "skipped": 0},
    }


CLEAN_REPORT_TS = "2026-01-01T00:00:00+0000"


def test_partial_project_not_pass_on_text_and_image(tmp_path: Path) -> None:
    """验收 1（假绿必须消失）：G0 判死的项目，文本/图文轨不得为 pass。"""
    _project(
        tmp_path,
        image_bytes=2 * 1024,
        reports=[(CLEAN_REPORT_TS, _g0_dead_report())],
    )
    p = _one(tmp_path)
    assert p["gate_chain"]["ok"] is False
    assert p["gate_chain"]["blocker"] == "G0"
    assert "G0" in p["gate_chain"]["reason"]
    assert p["text_state"] == "fail"
    assert p["image_state"] == "fail"
    assert p["text_ok"] is False
    assert p["image_ok"] is False
    # 判红原因写明卡在哪道门（验收要求含 "G0"）。
    assert _track_red_reason(p, "文本轨") == "卡在 G0"
    assert _track_red_reason(p, "图文轨") == "卡在 G0"


def test_video_track_unverified_when_no_video(tmp_path: Path) -> None:
    """验收 2：纯文本项目（无视频文件）→ 视频轨 unverified，不是 ❌。"""
    _project(
        tmp_path,
        video_bytes=0,
        reports=[(CLEAN_REPORT_TS, _report(list(MUST_RUN), []))],
    )
    p = _one(tmp_path)
    assert p["video_state"] == "unverified"
    assert p["video_ok"] is False  # unverified 绝不当作 pass


def test_completed_project_passes_tracks(tmp_path: Path) -> None:
    """验收 3（正向不回归）：门全过 + 产物齐 → 三轨按产物如实 pass。"""
    _project(
        tmp_path,
        image_bytes=2 * 1024,
        video_bytes=10 * 1024,
        reports=[(CLEAN_REPORT_TS, _report(list(MUST_RUN), []))],
    )
    p = _one(tmp_path)
    assert (p["text_state"], p["image_state"], p["video_state"]) == ("pass", "pass", "pass")


def test_pipeline_status_partial_blocks_all_tracks(tmp_path: Path) -> None:
    """负样本：00_project_info.json 的 status 改成 partial ⇒ 三轨一律不达标。"""
    proj = _project(
        tmp_path,
        image_bytes=2 * 1024,
        video_bytes=10 * 1024,
        reports=[(CLEAN_REPORT_TS, _report(list(MUST_RUN), []))],
    )
    (proj / "00_project_info.json").write_text(json.dumps({"status": "partial"}), encoding="utf-8")
    p = _one(tmp_path)
    assert p["gate_chain"]["ok"] is False
    assert p["gate_chain"]["reason"] == "pipeline status=partial"
    assert p["text_state"] == p["image_state"] == p["video_state"] == "fail"


def test_failed_gate_in_report_blocks_all_tracks(tmp_path: Path) -> None:
    """负样本：gate 报告含 failed 门 ⇒ 有证据的轨全部降为 fail，点名该门。"""
    _project(
        tmp_path,
        image_bytes=2 * 1024,
        video_bytes=10 * 1024,
        reports=[(CLEAN_REPORT_TS, _report(list(MUST_RUN), ["V3"]))],
    )
    p = _one(tmp_path)
    assert p["gate_chain"]["blocker"] == "V3"
    assert p["text_state"] == p["image_state"] == p["video_state"] == "fail"
    assert _track_red_reason(p, "文本轨") == "卡在 V3"


def test_removing_video_makes_track_unverified(tmp_path: Path) -> None:
    """负样本：视频文件删掉 ⇒ 视频轨变 unverified（不是 pass，也不是 fail）。"""
    _project(
        tmp_path,
        video_bytes=0,  # 等价于「删掉视频」后的目录
        image_bytes=2 * 1024,
        reports=[(CLEAN_REPORT_TS, _report(list(MUST_RUN), []))],
    )
    p = _one(tmp_path)
    assert p["video_state"] == "unverified"
    assert _track_red_reason(p, "文本轨") != ""


def test_no_gate_report_blocks_text_track(tmp_path: Path) -> None:
    """没有 gate-report ⇒ 无法证明门链通过 ⇒ 文本轨不达标（不许默认绿）。"""
    _project(tmp_path, reports=None)
    p = _one(tmp_path)
    assert p["gate_chain"]["ok"] is False
    assert p["gate_chain"]["reason"] == "no gate-report"
    assert p["text_state"] == "fail"


def test_main_verdict_distinguishes_fail_and_unverified(tmp_path: Path, monkeypatch) -> None:
    """顶层判定行区分三态（#361 示例格式）。"""
    from scripts import nightly_gap

    # G0 判死 + 无图无视频：文本 fail，图文/视频 unverified——正是 issue 的例子的形状。
    _project(tmp_path, video_bytes=0, reports=[(CLEAN_REPORT_TS, _g0_dead_report())])
    real_scan = nightly_gap.scan_projects
    monkeypatch.setattr(
        nightly_gap, "scan_projects", lambda root=None, extra_root=None: real_scan(root=tmp_path)
    )
    out = tmp_path / "gap.md"
    rc = nightly_gap.main(["--skip-validate", "--md-out", str(out)])
    assert rc == 1
    text = out.read_text(encoding="utf-8")
    assert "1 条未达标（文本轨，卡在 G0）" in text
    assert "2 条未验证（图文轨、视频轨）" in text
    assert "0 条达标" in text
    assert "⏳ **视频轨**：未验证（无证据，不作能力宣称）" in text


def test_main_all_pass_exits_zero(tmp_path: Path, monkeypatch) -> None:
    """三轨全 pass ⇒ 判定行回到原措辞、退出码 0。"""
    from scripts import nightly_gap

    _project(
        tmp_path,
        image_bytes=2 * 1024,
        video_bytes=10 * 1024,
        reports=[(CLEAN_REPORT_TS, _report(list(MUST_RUN), []))],
    )
    real_scan = nightly_gap.scan_projects
    monkeypatch.setattr(
        nightly_gap, "scan_projects", lambda root=None, extra_root=None: real_scan(root=tmp_path)
    )
    out = tmp_path / "gap.md"
    rc = nightly_gap.main(["--skip-validate", "--md-out", str(out)])
    assert rc == 0
    assert "三轨全达标（机器可判部分完成）" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Validation-matrix honesty: 「未过」≠「未执行」(issue #415)
# ---------------------------------------------------------------------------


def _fake_proc(payload: dict) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(returncode=0, stdout=json.dumps(payload))


def test_validate_summary_splits_unexecuted_from_failed(monkeypatch) -> None:
    """hard 场景的 None（从未落 suite 记录）不得报成「未过」（issue #415）。"""
    from types import SimpleNamespace

    import scripts.nightly_gap as ng

    matrix = {
        "scenarios": [
            {"name": "h-pass", "hard": True, "last_status": "passed"},
            {"name": "h-fail", "hard": True, "last_status": "failed"},
            {"name": "h-never", "hard": True, "last_status": None},
        ],
        "summary": {"gates_missing": 4, "gates_unreachable": 2},
    }
    coverage = {"unreachable_gates": ["G4", "G5"]}

    def fake_run(cmd, **kwargs):
        payload = matrix if "matrix" in cmd else coverage
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    monkeypatch.setattr(ng.subprocess, "run", fake_run)
    monkeypatch.setattr(ng, "REPO", Path("/nonexistent-repo-for-test"))
    vs = ng.validate_summary("python")
    assert vs["hard_total"] == 3
    assert vs["hard_failed"] == ["h-fail"]
    assert vs["hard_unexecuted"] == ["h-never"]
    # backward-compat aggregate stays available for old readers
    assert vs["hard_not_passed"] == ["h-fail", "h-never"]
    # the unreachable COUNT is resolved to concrete gate names (#415)
    assert vs["gates_unreachable"] == 2
    assert vs["gates_unreachable_names"] == ["G4", "G5"]


def test_last_suite_record_reads_latest_pointer(tmp_path: Path, monkeypatch) -> None:
    import scripts.nightly_gap as ng

    monkeypatch.setattr(ng, "REPO", tmp_path)
    assert ng._last_suite_record() == ""
    runs = tmp_path / "validation-runs"
    runs.mkdir()
    (runs / "latest.txt").write_text("20261105-004359-871791\n", encoding="utf-8")
    assert ng._last_suite_record() == "20261105-004359-871791"


def test_run_validation_scope_hard_reports_each_scenario(monkeypatch) -> None:
    """hard 范围逐条真跑并把真实 status 直接写进结果（不经过矩阵转述）。"""
    import scripts.nightly_gap as ng

    monkeypatch.setattr(
        ng,
        "validate_summary",
        lambda p: {"hard_failed": [], "hard_unexecuted": ["a-boundary", "b-boundary"]},
    )

    def fake_run(cmd, **kwargs):
        name = cmd[cmd.index("--scenario") + 1]
        status = "passed" if name == "a-boundary" else "failed"
        return _fake_proc({"status": status})

    monkeypatch.setattr(ng.subprocess, "run", fake_run)
    out = ng.run_validation_scope("python", "hard")
    assert out["scope"] == "hard"
    assert [e["scenario"] for e in out["executed"]] == ["a-boundary", "b-boundary"]
    assert [e["status"] for e in out["executed"]] == ["passed", "failed"]


def test_run_validation_scope_hard_handles_subprocess_error(monkeypatch) -> None:
    import scripts.nightly_gap as ng

    monkeypatch.setattr(
        ng,
        "validate_summary",
        lambda p: {"hard_failed": ["x-boundary"], "hard_unexecuted": []},
    )

    def fake_run(cmd, **kwargs):
        raise OSError("network gone")

    monkeypatch.setattr(ng.subprocess, "run", fake_run)
    out = ng.run_validation_scope("python", "hard")
    assert out["executed"][0]["scenario"] == "x-boundary"
    assert out["executed"][0]["status"] == "error:OSError"


def test_run_validation_scope_hard_noop_when_matrix_has_real_records(monkeypatch) -> None:
    import scripts.nightly_gap as ng

    monkeypatch.setattr(
        ng,
        "validate_summary",
        lambda p: {"hard_failed": [], "hard_unexecuted": []},
    )
    out = ng.run_validation_scope("python", "hard")
    assert out["executed"] == []
    assert "no hard scenario" in out["note"]
