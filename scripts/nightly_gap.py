#!/usr/bin/env python3
"""nightly_gap.py — 不眠计划 · AutoMedia 差距计算器（L2-a）

把「当前产出 vs 完成定义（DoD）」算成机器可读矩阵。
**冻结区**：docs/NIGHTLY.md 的 DoD 文本另案处理；本脚本的判据按 issue #361
的授权修订（2026-11-04，owner 登记）。

DoD（见 docs/dev/plans/NIGHTLY.md，与 L1 一致）：三条轨各有 ≥1 次真模型端到端跑，
且产物落在**持久目录**。产物位置由 **Agent 自由决定**（owner 2026-10-30 裁定，
见 NIGHTLY.md「修订请求」）——不限定 repo 内、也不禁止 `/tmp`；
扫描器通过 `AUTOMEDIA_PROJECTS_DIR` 环境变量发现产物目录。

三轨判定（全部机械化，尽量少主观；#361 起必须叠加门链结论）：
  共同前提 门链通过：最新 gate-report 无 fail/review 行，且跑批 status 位
           不是 partial/failed——门说「这篇不能用」，矩阵就不许说「达标」
  文本轨   cost_log.jsonl 非空，且 01_content/drafts/ 里有 ≥1 个 ≥500B 的 md
  图文轨   文本轨两条（同上）+ 02_images/ 里有 ≥1 个 ≥1KB 的图片
  视频轨   文本轨两条（同上）+ 03_video/ 里有 ≥1 个 ≥10KB 的视频，
          且该项目有可解析 gate-report：
          有诚实生产者的 V2/V5/V7 必须真跑且 pass；
          V0/V1/V3/V4/V6 计为已登记能力债（#193），任何新增 skip 判红
三态（#361）：每条轨 pass / fail / unverified。unverified = 该轨毫无证据
  （没有视频文件 / 没有图 / 没有跑过的项目）——不作能力宣称，也绝不当作 pass；
  「没跑过」与「跑过没过」必须分开报告。

用法：python3 scripts/nightly_gap.py [--json-out F] [--md-out F] [--scan-root DIR]
退出码：0 = 三轨全达标 / 1 = 仍有差距（未达标或未验证）/ 2 = 用法或环境错误
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECT_RE = re.compile(r"^\d{8}_.+")
MIN_DRAFT_BYTES = 500
MIN_IMAGE_BYTES = 1024
MIN_VIDEO_BYTES = 10 * 1024
VIDEO_GATES_MUST_RUN = ("V2", "V5", "V7")  # 有诚实生产者：必须真跑且 pass
VIDEO_GATES_CAPABILITY_DEBT = ("V0", "V1", "V3", "V4", "V6")  # 无诚实生产者：允许 skip，但须登记
VIDEO_GATE_DEBT_ISSUE = "#193"
GATE_REPORT_GLOB = "05_review/gate-report/gate-report-*.json"
#: 跑批结论里判「这次跑批没成」的状态位（issue #361）。success/awaiting_review 不拦。
BLOCKING_PIPELINE_STATUSES = ("partial", "failed")
#: gate-report 行里判「门链失败」的词（issue #361）。review = 门崩溃待复核，同样没通过；
#: skip 是「刻意没评」（模式本就没有该输入），不拦文本/图文轨——视频轨另有 must-run 规则。
BLOCKING_GATE_VERDICTS = ("fail", "failed", "review", "error")
#: 轨名 → 每项目三态字段的映射（报告层用）。
TRACK_STATE_KEYS = {"文本轨": "text_state", "图文轨": "image_state", "视频轨": "video_state"}

#: Agent 用它声明「我把产物放在哪」。扫描器认这个位置，**不限定必须在 repo 内**。
PROJECTS_DIR_ENV = "AUTOMEDIA_PROJECTS_DIR"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VID_EXT = {".mp4", ".mov", ".webm", ".mkv"}


def _files(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.is_file()] if d.is_dir() else []


def _biggest(files: list[Path], exts: set[str] | None = None) -> int:
    cand = [f for f in files if exts is None or f.suffix.lower() in exts]
    return max((f.stat().st_size for f in cand), default=0)


def _read_gate_report(path: Path) -> dict | None:
    """解析单份 gate-report；失败返回 None（这一份跳过，不致命）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _best_gate_report(project_dir: Path) -> tuple[Path, dict] | None:
    """挑该项目 generated_at 最新、且可解析的那份 gate-report。

    门链结论（#361）与视频轨 V 门证据（#181）必须读**同一份**报告，否则
    「门链看旧报告、V 门看新报告」会拼出两个真相。
    """
    best: tuple[str, Path, dict] | None = None  # (generated_at, 路径, 解析结果)
    for f in sorted(project_dir.glob(GATE_REPORT_GLOB)):
        data = _read_gate_report(f)
        if data is None:
            continue  # 某份 JSON 解析失败就跳过该份
        ts = str(data.get("generated_at") or "")
        if best is None or ts > best[0]:
            best = (ts, f, data)
    return None if best is None else (best[1], best[2])


def _pipeline_status(project_dir: Path) -> str:
    """读 ``00_project_info.json`` 里的跑批结论状态位（issue #361）。

    生产写入方（``core/project.py``）目前并不落 status 字段——真跑批结论的
    持久化形态是 gate-report 本身；这里兼容读取 ``status`` / ``pipeline_status``
    / ``pipeline.status`` 三种位置，主要服务 #361 的验收夹具（改状态位即可
    复现 partial），也让未来 runner 落盘 status 时判据自动生效。
    """
    try:
        info = json.loads((project_dir / "00_project_info.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(info, dict):
        return ""
    candidates = [info.get("status"), info.get("pipeline_status")]
    nested = info.get("pipeline")
    if isinstance(nested, dict):
        candidates.append(nested.get("status"))
    for v in candidates:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def gate_chain_evidence(project_dir: Path) -> dict:
    """门链结论（issue #361）：三轨达标都必须叠加「这次跑批没有失败」。

    两个来源，按优先级：
      1. ``00_project_info.json`` 的 status 位（partial/failed ⇒ 直接不达标）；
      2. 最新 gate-report（与 :func:`video_gate_evidence` 同一份）里有无
         fail/review 行，``blocked_by_gate`` 直接点名卡在哪道门。

    没有任何 gate-report ⇒ 同样不许达标（``no gate-report``）：达标主张
    需要「门链没有失败」的证据，缺报告只是没人证明它通过。
    """
    out: dict = {
        "ok": False,
        "reason": "",
        "blocker": "",
        "report": "",
        "pipeline_status": _pipeline_status(project_dir),
    }
    if out["pipeline_status"] in BLOCKING_PIPELINE_STATUSES:
        out["reason"] = f"pipeline status={out['pipeline_status']}"
        return out

    best = _best_gate_report(project_dir)
    if best is None:
        has_files = bool(sorted(project_dir.glob(GATE_REPORT_GLOB)))
        out["reason"] = "gate-report unreadable" if has_files else "no gate-report"
        return out
    path, data = best
    out["report"] = path.relative_to(project_dir).as_posix()

    blocker = ""
    entries = data.get("gates")
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("gate") or "").strip()
        verdict = str(item.get("verdict") or "").strip()
        status = str(item.get("status") or "").strip()
        if verdict in BLOCKING_GATE_VERDICTS or status in ("failed", "error"):
            blocker = name
            break
    if not blocker:
        blocked_by = str(data.get("blocked_by_gate") or "").strip()
        if blocked_by:
            blocker = blocked_by
    if blocker:
        out["blocker"] = blocker
        out["reason"] = f"卡在 {blocker}"
        return out

    out["ok"] = True
    return out


def video_gate_evidence(project_dir: Path) -> dict:
    """读该项目最新的 gate-report，给出视频轨 V 门证据（#181：只看文件大小会假绿）。

    判据（owner 2026-10-07 裁定「带能力债的达标」）：
      - 有诚实生产者的 V2/V5/V7 必须真跑且 pass；
      - 无诚实生产者的 V0/V1/V3/V4/V6 允许 skip，但只允许这五门（能力债登记 #193）。
    """
    all_v = ("V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7")
    buckets: dict[str, list[str]] = {
        "passed": [],
        "skipped": [],
        "failed": [],
        "errored": [],
        "other": [],
    }
    out: dict = {
        "ok": False,
        "reason": "",
        "report": "",
        "passed": [],
        "skipped": [],
        "failed": [],
        "errored": [],
        "other": [],
        "missing": [],
        "debt_skipped": [],
    }

    files = sorted(project_dir.glob(GATE_REPORT_GLOB))
    if not files:
        out["reason"] = "no gate-report"
        return out

    best = _best_gate_report(project_dir)
    if best is None:
        out["reason"] = "gate-report unreadable"
        return out
    report_path, data = best

    out["report"] = report_path.relative_to(project_dir).as_posix()
    seen: set[str] = set()
    entries = data.get("gates")
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("gate") or "").strip()
        status = str(item.get("status") or "").strip()
        if name not in all_v or name in seen:
            continue
        seen.add(name)
        buckets[status if status in buckets else "other"].append(name)
    for key, val in buckets.items():
        buckets[key] = sorted(set(val))
    out.update(buckets)
    out["missing"] = sorted(set(all_v) - seen)
    out["debt_skipped"] = sorted(set(buckets["skipped"]) & set(VIDEO_GATES_CAPABILITY_DEBT))

    # ok 当且仅当五条全满足；reason 取第一条不满足的
    if out["missing"]:
        out["reason"] = "gates missing from report: " + ",".join(out["missing"])
    elif buckets["failed"] or buckets["errored"] or buckets["other"]:
        first = sorted(set(buckets["failed"]) | set(buckets["errored"]) | set(buckets["other"]))[0]
        out["reason"] = f"gate failed: {first}"
    elif not set(VIDEO_GATES_MUST_RUN) <= set(buckets["passed"]):
        first = sorted(set(VIDEO_GATES_MUST_RUN) - set(buckets["passed"]))[0]
        out["reason"] = f"must-run gate not passed: {first}"
    elif not set(buckets["skipped"]) <= set(VIDEO_GATES_CAPABILITY_DEBT):
        first = sorted(set(buckets["skipped"]) - set(VIDEO_GATES_CAPABILITY_DEBT))[0]
        out["reason"] = f"unregistered skip: {first}"
    else:
        out["ok"] = True
        out["reason"] = ""
    return out


def _text_evidence_ok(cost_lines: int, draft_max: int) -> bool:
    """文本轨证据子句——DoD 里「同上」二字所指的正是它（issue #195）。

    图文轨/视频轨在 DoD 表里以「同上 **+**」开头，故完整继承本子句两条条件：
    `cost_log.jsonl` 非空（真模型调用记录）且 有 ≥500B 的 md 正文。收敛到唯一
    出口是为了让「继承」成为结构事实：此前 `image_ok` / `video_ok` 各判各的产物
    大小，静默漏掉这两条，一个无真模型记录、只有一张图的阶段目录会被判达标。
    """
    return cost_lines > 0 and draft_max >= MIN_DRAFT_BYTES


def scan_projects(root: Path | None = None, extra_root: Path | None = None) -> list[dict]:
    """Scan REPO root plus every location the Agent declared.

    The Agent picks where products land (owner 2026-10-30 ruling: free choice,
    no repo-internal requirement). Locations scanned:
      1. ``REPO`` — the repo root, where in-repo projects live
      2. ``extra_root`` — an explicit ``--scan-root`` argument
      3. ``$AUTOMEDIA_PROJECTS_DIR`` — where the Agent said it put the products
    """
    roots = [root or REPO]
    # 产物位置由 Agent 自由决定（owner 2026-10-30 裁定）：除显式传入的 extra_root，
    # 也认 ``AUTOMEDIA_PROJECTS_DIR`` 声明的位置——不限 repo 内、也不禁止 /tmp。
    for cand in (extra_root, os.environ.get(PROJECTS_DIR_ENV, "").strip()):
        if not cand:
            continue
        p = Path(cand)
        if p.is_dir() and p not in roots:
            roots.append(p)
    out: list[dict] = []
    seen: set[str] = set()
    for r in roots:
        for d in sorted(r.iterdir()):
            if not d.is_dir() or not PROJECT_RE.match(d.name):
                continue
            if d.name in seen:
                continue
            seen.add(d.name)
            drafts = _files(d / "01_content" / "drafts")
            images = _files(d / "02_images")
            videos = _files(d / "03_video")
            cost = d / "cost_log.jsonl"
            cost_lines = 0
            if cost.is_file():
                cost_lines = sum(
                    1 for ln in cost.read_text(errors="ignore").splitlines() if ln.strip()
                )
            draft_max = _biggest(drafts, {".md"})
            img_max = _biggest(images, IMG_EXT)
            vid_max = _biggest(videos, VID_EXT)
            ev = video_gate_evidence(d)
            chain = gate_chain_evidence(d)
            # DoD 表里图文轨/视频轨均以「同上 +」开头，故继承文本轨这两条（#195）。
            # #361 起三轨达标还必须叠加门链结论：门说不行，产物再多也不算数。
            text_evidence = _text_evidence_ok(cost_lines, draft_max)
            text_ok = text_evidence and chain["ok"]
            image_ok = text_ok and img_max >= MIN_IMAGE_BYTES
            video_ok = text_ok and vid_max >= MIN_VIDEO_BYTES and ev["ok"]
            # 三态（#361）：unverified = 该轨毫无证据（没跑过/没产物），
            # 不作能力宣称，也绝不当作 pass；「没跑过」≠「跑过没过」。
            out.append(
                {
                    "project": d.name,
                    "cost_log_lines": cost_lines,
                    "draft_count": len(drafts),
                    "draft_max_bytes": draft_max,
                    "image_max_bytes": img_max,
                    "video_max_bytes": vid_max,
                    "has_pipeline_md5": (d / "pipeline_md5.json").is_file(),
                    "text_ok": text_ok,
                    "image_ok": image_ok,
                    "video_ok": video_ok,
                    "text_evidence_ok": text_evidence,
                    "text_state": _tri_state(cost_lines > 0 or draft_max > 0, text_ok),
                    "image_state": _tri_state(img_max > 0, image_ok),
                    "video_state": _tri_state(vid_max > 0, video_ok),
                    "gate_chain": chain,
                    "video_gates": ev,
                }
            )
    return out


def _tri_state(has_evidence: bool, ok: bool) -> str:
    """单项目单轨的三态归约（issue #361）：unverified / fail / pass。"""
    if not has_evidence:
        return "unverified"
    return "pass" if ok else "fail"


def _track_red_reason(p: dict, track: str) -> str:
    """单项目在该轨的判红原因：门链结论优先（#361 要求写明卡在哪道门）。"""
    chain_reason = p["gate_chain"]["reason"]
    if chain_reason:
        return chain_reason
    if track == "文本轨":
        return "缺文本证据（draft < 500B 或 cost_log 空）"
    if track == "图文轨":
        if not p["text_evidence_ok"]:
            return "缺文本证据（draft < 500B 或 cost_log 空）"
        return f"图片 <{MIN_IMAGE_BYTES}B"
    return _video_red_reason(p)


def _automedia_cmd(python: str) -> list[str]:
    """用与解释器同 venv 的 console script（`-m automedia.cli.app` 无效，无 __main__）。"""
    if "/" in python:
        cand = Path(python).absolute().parent / "automedia"
        if cand.exists():
            return [str(cand)]
    return [python, "-m", "automedia"]


def validate_summary(python: str) -> dict:
    """复用 automedia 自己的验证矩阵（不另造门）。失败不致命，只标注。"""
    try:
        cmd = [*_automedia_cmd(python), "--json", "validate", "matrix"]
        r = subprocess.run(  # noqa: S603 — argv is literals from _automedia_cmd, no shell
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=600,
        )
        data = json.loads(r.stdout)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    sc = data.get("scenarios") or []
    status: dict[str, int] = {}
    for s in sc:
        k = str(s.get("last_status"))
        status[k] = status.get(k, 0) + 1
    summ = data.get("summary") or {}
    return {
        "scenarios_total": len(sc),
        "scenario_status": status,
        "hard_total": sum(1 for s in sc if s.get("hard")),
        "hard_not_passed": [
            s["name"] for s in sc if s.get("hard") and s.get("last_status") != "passed"
        ],
        "gates_missing": summ.get("gates_missing"),
        "gates_unreachable": summ.get("gates_unreachable"),
        "mcp_missing": summ.get("mcp_missing"),
        "cli_missing": summ.get("cli_missing"),
    }


def _video_red_reason(p: dict) -> str:
    """视频轨判红的**合取**首因：文本证据 → 文件下限 → V 门证据（#235）。

    `video_ok = text_evidence AND vid_max >= 10KB AND video_gate_evidence.ok`，
    故原因必须按同一合取顺序取第一个 false 的子句，否则「根本没视频」的项目
    会被末尾的门证据原因（`no gate-report`）盖住，藏起真正可执行的信息。
    """
    if not p["text_evidence_ok"]:
        return "缺文本证据（draft < 500B 或 cost_log 空）"
    if p["video_max_bytes"] < MIN_VIDEO_BYTES:
        return f"视频文件 <{MIN_VIDEO_BYTES}B"
    return p["video_gates"]["reason"] or "视频门证据未通过"


def _is_near_miss(p: dict) -> bool:
    """「离达标最近」的候选：尺寸 + 文本都过，只差 gate-report 里的 V 门行。"""
    return (
        p["text_evidence_ok"]
        and p["video_max_bytes"] >= MIN_VIDEO_BYTES
        and not p["video_gates"]["ok"]
    )


def _video_track_note(projects: list[dict], track: dict) -> str:
    """视频轨那一行下面的附注：达标 → 登记的能力债；未达标 → 前 5 个判红原因。

    选样优先展示「离达标最近」的项目：先按 `video_max_bytes` 降序列只差 V 门证据
    的候选，再列其余（#235）——按项目名字母序会把 `20260822_*` 文本轨目录排到
    前面，把真视频候选藏起来。
    """
    if track["ok"]:
        return (
            f"  - 能力债（登记，不计入达标）："
            f"{'/'.join(VIDEO_GATES_CAPABILITY_DEBT)}（无诚实生产者，{VIDEO_GATE_DEBT_ISSUE}）"
        )
    # #361：只列「跑过没过」的候选——没有视频文件的项目是 unverified，
    # 混进判红名单会把「没跑过」伪装成「能力不行」。
    red = [p for p in projects if p["video_state"] == "fail"]
    near = sorted(
        (p for p in red if _is_near_miss(p)),
        key=lambda p: p["video_max_bytes"],
        reverse=True,
    )
    rest = [p for p in red if not _is_near_miss(p)]
    bad = [f"{p['project']}: {_video_red_reason(p)}" for p in (near + rest)[:5]]
    return "  - 判红原因（前 5 个）：" + ("；".join(bad) if bad else "无项目")


def _git(*args: str) -> str:
    """跑一条 git 命令；任何失败（非零返回 / 异常 / 空输出）都退化为 `<unknown>`。"""
    try:
        r = subprocess.run(  # noqa: S603 — argv is literals from _git callers, no shell
            ["git", *args],  # noqa: S607 — bare `git` resolved via PATH is intended
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=10,
        )
    except Exception:
        return "<unknown>"
    if r.returncode != 0:
        return "<unknown>"
    return r.stdout.strip() or "<unknown>"


def _bench_line() -> str:
    """报告正文里的 `bench：<branch>@<sha>`——让「这份矩阵测的是哪棵树」可见。

    2026-10-18 那轮实际测的不是 main（见 e2e-test-suite#186），所以把 benchmark
    的树写进报告头部，而不是只在 CI 日志里。
    """
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    sha = _git("rev-parse", "--short", "HEAD")
    return f"- bench：{branch}@{sha}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nightly_gap.py")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument(
        "--scan-root",
        default="",
        help="Additional project root to scan (defaults to $AUTOMEDIA_PROJECTS_DIR)",
    )
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--md-out", default="")
    args = ap.parse_args(argv)

    explicit = Path(args.scan_root) if args.scan_root else None
    env_dir = os.environ.get(PROJECTS_DIR_ENV, "").strip()
    extra = explicit or (Path(env_dir) if env_dir else None)
    projects = scan_projects(extra_root=extra)

    def _track(key: str) -> dict:
        """单轨三态聚合（issue #361）：有 pass 即 pass；否则有证据即 fail；
        全体项目都无该轨证据 ⇒ unverified（不作能力宣称）。"""
        state = "unverified"
        if any(p[key] == "fail" for p in projects):
            state = "fail"
        if any(p[key] == "pass" for p in projects):
            state = "pass"
        passing = [p["project"] for p in projects if p[key] == "pass"]
        return {
            "ok": state == "pass",
            "state": state,
            "evidence": passing[:5],
            "count": len(passing),
        }

    tracks = {
        "文本轨": _track("text_state"),
        "图文轨": _track("image_state"),
        "视频轨": _track("video_state"),
    }
    fail_tracks = [k for k, v in tracks.items() if v["state"] == "fail"]
    unverified_tracks = [k for k, v in tracks.items() if v["state"] == "unverified"]
    gap = [k for k, v in tracks.items() if v["state"] != "pass"]
    vs = {} if args.skip_validate else validate_summary(args.python)

    n_pass, n_fail, n_unv = 3 - len(gap), len(fail_tracks), len(unverified_tracks)
    result = {
        "schema": "nightly-gap/2",
        "project": "AutoMedia",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_units": 3,
        "passing_units": n_pass,
        "gap": gap,
        "tracks": tracks,
        "projects": projects,
        "validate": vs,
        "capability_debt": {
            "视频轨": {
                "registered_gates": list(VIDEO_GATES_CAPABILITY_DEBT),
                "skipped_in_evidence": sorted(
                    {g for p in projects if p["video_ok"] for g in p["video_gates"]["debt_skipped"]}
                ),
                "reason": (
                    "五门无诚实生产者（见 .trae/documents/video-track-remediation-plan.md §一）"
                ),
                "tracked_by": VIDEO_GATE_DEBT_ISSUE,
            }
        },
    }
    if gap:
        result["exit_reason"] = f"未达标 {n_fail} · 未验证 {n_unv}（共 3 轨）"

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 判定行区分三态（#361）：「未达标」与「未验证」不许混报，更不许都算绿。
    if not gap:
        verdict = "- 判定：**三轨全达标（机器可判部分完成）**"
    else:
        seg = []
        if fail_tracks:
            names = "、".join(fail_tracks)
            first_failer = next(
                (p for p in projects if p[TRACK_STATE_KEYS[fail_tracks[0]]] == "fail"), None
            )
            red = _track_red_reason(first_failer, fail_tracks[0]) if first_failer else ""
            seg.append(
                f"{n_fail} 条未达标（{names}，{red}）" if red else f"{n_fail} 条未达标（{names}）"
            )
        if unverified_tracks:
            seg.append(f"{n_unv} 条未验证（{'、'.join(unverified_tracks)}）")
        seg.append(f"{n_pass} 条达标")
        verdict = f"- 判定：**{' · '.join(seg)}**"
    md = [
        "# AutoMedia 差距矩阵",
        "",
        verdict,
        "",
        f"- 项目目录：{len(projects)} 个（真模型 cost_log 非空："
        f"{sum(1 for p in projects if p['cost_log_lines'] > 0)} 个）",
        _bench_line(),
    ]
    for name, v in tracks.items():
        state = v["state"]
        key = TRACK_STATE_KEYS[name]
        if state == "pass":
            ev = "、".join(v["evidence"]) if v["evidence"] else "无"
            md.append(f"- ✅ **{name}**：{v['count']} 个达标；证据：{ev}")
        elif state == "fail":
            reds = [
                f"{p['project']}: {_track_red_reason(p, name)}"
                for p in projects
                if p[key] == "fail"
            ][:5]
            reds_line = "；".join(reds) or "无项目"
            md.append(f"- ❌ **{name}**：未达标；判红原因（前 5 个）：{reds_line}")
        else:
            md.append(f"- ⏳ **{name}**：未验证（无证据，不作能力宣称）")
        if name == "视频轨" and state == "fail":
            md.append(_video_track_note(projects, v))
    if vs and "error" not in vs:
        md += [
            "",
            "## 验证矩阵（自动生成，复用 automedia 自带）",
            f"- 场景 {vs['scenarios_total']} 条：{vs['scenario_status']}",
            f"- hard 场景 {vs['hard_total']} 条，未过：{vs['hard_not_passed'] or '无'}",
            f"- 门：missing={vs['gates_missing']} unreachable={vs['gates_unreachable']}",
        ]
    md_text = "\n".join(md) + "\n"
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(md_text, encoding="utf-8")
    print(md_text)
    return 1 if gap else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"环境/用法错误：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
