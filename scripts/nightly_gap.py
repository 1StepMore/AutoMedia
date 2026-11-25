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
          有诚实生产者的 V1/V2/V5/V7 必须真跑且 pass（#414 口径统一）；
          V0/V3/V4/V6 计为已登记能力债（#193），任何新增 skip 判红；
          media_stage 有 video_render_failed / video_render_degraded 注记
          ⇒ 判红，且原因写明渲染失败/降级（#414）
三态（#361）：每条轨 pass / fail / unverified。unverified = 该轨毫无证据
  （没有视频文件 / 没有图 / 没有跑过的项目）——不作能力宣称，也绝不当作 pass；
  「没跑过」与「跑过没过」必须分开报告。

用法：python3 scripts/nightly_gap.py [--json-out F] [--md-out F] [--scan-root DIR]
      [--validate-scope none|hard|all]（#447：默认 hard 真跑边界场景；none 需显式传；
      all 整库 run --all，让矩阵获得真实 last_status）
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
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECT_RE = re.compile(r"^\d{8}_.+")
MIN_DRAFT_BYTES = 500
MIN_IMAGE_BYTES = 1024
MIN_VIDEO_BYTES = 10 * 1024
# 视频轨 V 门口径（#414 起与 validation/gate_inputs.py 的静态可达性审计唯一对齐）：
# 必跑集合 = 有诚实生产者的门（audit 的 reachable）；能力债 = 无生产者的门
# （audit 的 unreachable）。V1 自 #387 起有真实生产者（_produce_vision_entries），
# 从债集合移除；V0 自 #470 起有真实生产者（pipelines/lint_executor.run_lint：
# SRT 结构 / 时间单调 / 脚本字段完整性），V3 自 #471 起有真实生产者
# （keyword_extractor：topic 与源材料齐备时生产三件套），V4 自 #472 起有真实
# 生产者（TTS 适配层回传 voice 参数，品牌资产同源期望值），同样移除；
# tests/test_nightly_gap.py 用该审计逐值 pin 这两个常量。
VIDEO_GATES_MUST_RUN = ("V0", "V1", "V2", "V3", "V4", "V5", "V7")  # 有诚实生产者：必须真跑且 pass
VIDEO_GATES_CAPABILITY_DEBT = ("V6",)  # 无诚实生产者：允许 skip，但须登记
VIDEO_GATE_DEBT_ISSUE = "#193"
GATE_REPORT_GLOB = "05_review/gate-report/gate-report-*.json"
#: 跑批结论里判「这次跑批没成」的状态位（issue #361）。success/awaiting_review 不拦。
BLOCKING_PIPELINE_STATUSES = ("partial", "failed")
#: gate-report 行里判「门链失败」的词（issue #361）。review = 门崩溃待复核，同样没通过；
#: skip 是「刻意没评」（模式本就没有该输入），不拦文本/图文轨——视频轨另有 must-run 规则。
BLOCKING_GATE_VERDICTS = ("fail", "failed", "review", "error")
#: 轨名 → 每项目三态字段的映射（报告层用）。
TRACK_STATE_KEYS = {"文本轨": "text_state", "图文轨": "image_state", "视频轨": "video_state"}

#: 连续多少天一次场景都没执行，就在 gap 报告里报红（#447）。
UNEXECUTED_STREAK_RED_DAYS = 2
UNEXECUTED_STREAK_FILENAME = "nightly-gap-unexecuted-streak.json"

#: Agent 用它声明「我把产物放在哪」。扫描器认这个位置，**不限定必须在 repo 内**。
PROJECTS_DIR_ENV = "AUTOMEDIA_PROJECTS_DIR"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VID_EXT = {".mp4", ".mov", ".webm", ".mkv"}


def _files(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.is_file()] if d.is_dir() else []


def _biggest(files: list[Path], exts: set[str] | None = None) -> int:
    cand = [f for f in files if exts is None or f.suffix.lower() in exts]
    return max((f.stat().st_size for f in cand), default=0)


def _project_date(project_dir: Path) -> date:
    """项目日期：目录名开头 8 位 ``YYYYMMDD``；解析失败回退到目录 mtime。"""
    m = re.match(r"^(\d{8})", project_dir.name)
    if m:
        raw = m.group(1)
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            pass
    try:
        return date.fromtimestamp(project_dir.stat().st_mtime)
    except OSError:
        return date.today()


def _video_window_cutoff(today: date, days: int) -> date | None:
    """视频窗口起点；``days <= 0`` 表示不设窗口（返回 None）。"""
    if days <= 0:
        return None
    return today - timedelta(days=days - 1)


def bench_state(branch: str, is_ancestor: bool, tree_equal: bool = False) -> str:
    """纯函数：只有「在 main 上且 main 是 origin/main 祖先」或「树与 origin/main
    字节一致」才认 main 读数。

    「树一致」是 main 等价（issue #684 / B24）：contents-API 的 sync 提交不是
    origin/main 的祖先（``merge-base --is-ancestor`` 失败），但它的树与
    origin/main 字节一致（``diff --quiet origin/main HEAD`` 通过）——量出来的
    就是 main，标 ``unverified`` 会让报告分不清「真 feature 分支读数」和
    「main 等价读数」。真正的 feature 分支（树不同）依旧 ``unverified``：
    非 main 的树不得冒充主线读数。``tree_equal`` 有默认值，旧的两参调用点不受影响。
    """
    if tree_equal or (branch == "main" and is_ancestor):
        return "main"
    return "unverified"


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

    判据（owner 2026-10-07 裁定「带能力债的达标」；#414 起口径与
    ``validation/gate_inputs.py`` 的可达性审计统一）：
      - 有诚实生产者的 V1/V2/V5/V7 必须真跑且 pass；
      - 无诚实生产者的 V0/V3/V4/V6 允许 skip，但只允许这四门（能力债登记 #193）；
      - media_stage 注记 ``video_render_failed`` / ``video_render_degraded``
        ⇒ 判红，且判红原因写明「渲染失败 / 降级 slideshow」——修渲染还是
        补产物，一眼可辨（#414）。
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
        "render_failed": "",
        "render_degraded": "",
        "skip_reasons": {},
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
        if status == "skipped":
            out["skip_reasons"][name] = str(
                item.get("skip_reason") or item.get("reason") or ""
            )
    for key, val in buckets.items():
        buckets[key] = sorted(set(val))
    out.update(buckets)
    out["missing"] = sorted(set(all_v) - seen)
    out["debt_skipped"] = sorted(set(buckets["skipped"]) & set(VIDEO_GATES_CAPABILITY_DEBT))

    # media_stage 注记里的渲染事实（#414）：失败 / 降级都要浮出到判红原因
    media_stage = data.get("media_stage")
    notes = media_stage.get("notes") if isinstance(media_stage, dict) else None
    for note in notes if isinstance(notes, list) else []:
        if not isinstance(note, dict):
            continue
        event = str(note.get("event") or "")
        if event == "video_render_failed" and not out["render_failed"]:
            out["render_failed"] = str(note.get("error") or "")[:200]
        elif event == "video_render_degraded" and not out["render_degraded"]:
            out["render_degraded"] = str(note.get("reason") or "")[:200]

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

    # #414：渲染失败/降级压过一切「结构合格」——即使门行齐整（例如
    # allow_degrade 下降级件 + V 门真跑），视频轨也判红，且原因直说渲染。
    if out["render_failed"]:
        out["ok"] = False
        out["reason"] = f"video render failed: {out['render_failed']}"
    elif out["render_degraded"]:
        out["ok"] = False
        out["reason"] = f"video degraded to slideshow: {out['render_degraded']}"
    return out


#: 项目没喂源材料时 V3 必然 skip —— #661 之后 V3 需要
#: ``source_keywords/content_keywords/source_texts``，而旧的项目路径没有生产者。
#: 这不是「能力退步」，是「该项目不可判」；owner 2026-11-25 裁定归历史债务。
V3_NO_SOURCE_MARKER = "not produced by this pipeline"


def video_unjudgeable_no_source(ev: dict) -> bool:
    """视频轨「不可判」判定：只差 V3，且 V3 的 skip 原因是「本 pipeline 没产出源材料」。

    与「判红」区分开：判红 = 门真跑没过 / 渲染失败；不可判 = 这条项目根本
    没喂源材料，V3 无输入。把后者算红会让视频轨永久挂一个修不掉的项
    （owner 2026-11-25 裁定：归历史债务单列）。
    """
    reason = str(ev.get("reason") or "")
    prefix = "must-run gate not passed:"
    if not reason.startswith(prefix):
        return False
    if reason.split(prefix, 1)[1].strip() != "V3":
        return False
    return V3_NO_SOURCE_MARKER in str((ev.get("skip_reasons") or {}).get("V3", ""))


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
                    "project_date": _project_date(d).isoformat(),
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


def _last_suite_record() -> str:
    """最近一次整库 suite 记录的 run 目录名（自带 UTC 时间戳），无则空串。

    矩阵的 ``last_status`` 只认 ``validation-runs/latest.txt`` 指向的那份
    ``scenarios.json``；没有记录时一切场景都是「未执行」而不是「未过」
    （issue #415）。把记录时间戳写进报告，读者才能区分「没人跑过」与
    「记录过期」。
    """
    latest = REPO / "validation-runs" / "latest.txt"
    try:
        name = latest.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    return name if name else ""


def _read_streak_state(path: Path) -> tuple[str, int]:
    """Best-effort read of the streak state; missing or corrupt data reads as zero."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", 0
    if not isinstance(data, dict):
        return "", 0
    try:
        return str(data.get("date") or ""), int(data.get("streak") or 0)
    except (TypeError, ValueError):
        return "", 0


def _write_streak_state(path: Path, day: str, streak: int) -> None:
    """Persist the streak; an unwritable state file must not abort the report."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"date": day, "streak": streak}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return


def _update_unexecuted_streak(scope_used: str, executed: dict) -> dict:
    """Track consecutive days on which no validation scenario actually ran (#447).

    ``--validate-scope none`` and ``--skip-validate`` leave the chain idle; an
    idle day increments the streak, any real execution resets it.  Same-day
    reruns keep the count, so a manual rerun cannot inflate it.  The state file
    lives under the gitignored ``validation-runs/`` directory.
    """
    today = time.strftime("%Y-%m-%d")
    did_run = scope_used == "all" or bool(executed.get("executed")) or bool(executed.get("note"))
    path = REPO / "validation-runs" / UNEXECUTED_STREAK_FILENAME
    last_day, streak = _read_streak_state(path)
    if did_run:
        streak = 0
    elif last_day != today:
        streak += 1
    _write_streak_state(path, today, streak)
    return {
        "days": streak,
        "red": streak >= UNEXECUTED_STREAK_RED_DAYS,
        "executed_this_run": did_run,
    }


def _coverage_unreachable_names(python: str) -> list[str]:
    """从 ``validate coverage`` 取执行不可达门的具体名单。

    矩阵输出只带 ``gates_unreachable`` 计数；名单在 coverage audit 的
    ``unreachable_gates`` 键里（issue #415：看不到门名的数字无法驱动修复）。
    失败不致命，只标注（调用方负责降级为空名单）。
    """
    try:
        cmd = [*_automedia_cmd(python), "--json", "validate", "coverage"]
        r = subprocess.run(  # noqa: S603 — argv is literals from _automedia_cmd, no shell
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=600,
        )
        data = json.loads(r.stdout)
    except Exception:
        return []
    names = data.get("unreachable_gates")
    return [str(n) for n in names] if isinstance(names, list) else []


def validate_summary(python: str) -> dict:
    """复用 automedia 自己的验证矩阵（不另造门）。失败不致命，只标注。

    「未过」与「未执行」分开报告（issue #415）：``last_status is None``
    表示该场景从未落过 suite 记录，把它算进「未过」是把「没人跑」
    误报成「跑红了」。
    """
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
    hard = [s for s in sc if s.get("hard")]
    return {
        "scenarios_total": len(sc),
        "scenario_status": status,
        "hard_total": len(hard),
        "hard_passed": [s["name"] for s in hard if s.get("last_status") == "passed"],
        "hard_failed": [s["name"] for s in hard if s.get("last_status") == "failed"],
        "hard_unexecuted": [s["name"] for s in hard if s.get("last_status") is None],
        # 向后兼容：旧读者（含既有测试）按 != passed 聚合；新口径见上面两个字段
        "hard_not_passed": [s["name"] for s in hard if s.get("last_status") != "passed"],
        "last_suite_record": _last_suite_record(),
        "gates_missing": summ.get("gates_missing"),
        "gates_unreachable": summ.get("gates_unreachable"),
        "gates_unreachable_names": _coverage_unreachable_names(python),
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


def _bench_line(bench: dict | None = None) -> str:
    """报告正文里的 `bench：<branch>@<sha>`——让「这份矩阵测的是哪棵树」可见。

    2026-10-18 那轮实际测的不是 main（见 e2e-test-suite#186），所以把 benchmark
    的树写进报告头部，而不是只在 CI 日志里。``bench`` 可传入 :func:`_bench_snapshot`
    的结果以复用 git 读数（不传则现算，旧调用点不受影响）。sync 提交（树与
    origin/main 一致但非祖先，issue #684 / B24）标注 ``(sync of origin/main)``，
    让读者一眼看出这是 main 等价树，不是 feature 分支。
    """
    snap = bench if bench is not None else _bench_snapshot()
    branch = snap["bench_branch"]
    sha = snap["bench_head"]
    if snap.get("bench_sync_commit"):
        return f"- bench：{branch}@{sha} (sync of origin/main)"
    return f"- bench：{branch}@{sha}"


def _git_ok(*args: str) -> bool:
    """跑一条只靠退出码回答问题的 git 命令；异常 / 非零一律 False。"""
    try:
        r = subprocess.run(  # noqa: S603 — argv is literals from _git_ok callers, no shell
            ["git", *args],  # noqa: S607 — bare `git` resolved via PATH is intended
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=10,
        )
    except Exception:
        return False
    return r.returncode == 0


def _bench_snapshot() -> dict:
    """机器可读的 bench 读数（bench_branch / bench_head / bench_state）。

    ``bench_state`` 只有在 HEAD 位于 main 且 main 是 origin/main 祖先、
    或树与 origin/main 字节一致时才是 ``main``；否则是 ``unverified``
    ——非 main 读数不得被当作主线结论（issue #684 / B24）。
    ``bench_sync_commit`` 只在「树一致但非祖先」（即 contents-API sync 提交）
    时记录短 sha，供报告头部标注 ``(sync of origin/main)``。
    """
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    head = _git("rev-parse", "--short", "HEAD")
    ancestor = _git_ok("merge-base", "--is-ancestor", "HEAD", "origin/main")
    tree_equal = _git_ok("diff", "--quiet", "origin/main", "HEAD")
    return {
        "bench_branch": branch,
        "bench_head": head,
        "bench_state": bench_state(branch, ancestor, tree_equal),
        # sync 提交：树一致但不是祖先——正是 contents-API 重写留下的形状
        "bench_sync_commit": head if tree_equal and not ancestor else "",
    }


def run_validation_scope(python: str, scope: str) -> dict:
    """按 ``--validate-scope`` 真执行场景（issue #415 选项 A：要么跑、要么别报）。

    - ``hard``：逐条真跑 hard 场景（10 条边界场景，快）。单条 run 只落
      1 场景的 suite 记录、且 ``latest.txt`` 被指到最后一条——矩阵的
      ``last_status`` 因此**不会**保留这批结果；所以本函数把每条的真实
      status 直接写进返回值，由报告如实呈现，不经过矩阵转述。
    - ``all``：整库 ``validate run --all``，落一份完整 suite 记录并刷新
      ``latest.txt``，矩阵从此有真实 ``last_status``（周一次足矣）。
    失败不致命：单条失败记入返回值，继续跑下一条。
    """
    out: dict = {"scope": scope, "executed": [], "error": ""}
    if scope == "all":
        cmd = [*_automedia_cmd(python), "--json", "validate", "run", "--all"]
        t0 = time.time()
        try:
            r = subprocess.run(  # noqa: S603 — argv is literals, no shell
                cmd,
                capture_output=True,
                text=True,
                cwd=REPO,
                timeout=3600,
            )
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
            return out
        out["seconds"] = round(time.time() - t0, 1)
        out["exit_code"] = r.returncode
        data: dict = {}
        try:
            data = json.loads(r.stdout)
            suite = data.get("suite") or data
            rows = suite.get("scenarios") or []
            out["status_counts"] = {}
            for row in rows if isinstance(rows, list) else []:
                k = str(row.get("status"))
                out["status_counts"][k] = out["status_counts"].get(k, 0) + 1
        except Exception:
            out["status_counts"] = {}
        out["run_dir"] = str(data.get("run_dir", ""))
        return out

    # scope == "hard"
    vs = validate_summary(python)
    if "error" in vs:
        out["error"] = f"matrix unavailable: {vs['error']}"
        return out
    hard_names = sorted(set(vs.get("hard_failed", [])) | set(vs.get("hard_unexecuted", [])))
    if not hard_names:
        # 矩阵里 hard 全部有记录且非 failed —— 没有需要重跑的；如实返回
        out["note"] = "no hard scenario is failed or unexecuted per matrix"
        return out
    for name in hard_names:
        cmd = [*_automedia_cmd(python), "--json", "validate", "run", "--scenario", name]
        t0 = time.time()
        try:
            r = subprocess.run(  # noqa: S603 — argv is literals, no shell
                cmd,
                capture_output=True,
                text=True,
                cwd=REPO,
                timeout=900,
            )
            data = json.loads(r.stdout)
            status = str(data.get("status") or f"exit:{r.returncode}")
        except Exception as e:
            status = f"error:{type(e).__name__}"
        out["executed"].append(
            {"scenario": name, "status": status, "seconds": round(time.time() - t0, 1)}
        )
    return out


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nightly_gap.py")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument(
        "--scan-root",
        default="",
        help="Additional project root to scan (defaults to $AUTOMEDIA_PROJECTS_DIR)",
    )
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument(
        "--validate-scope",
        choices=("none", "hard", "all"),
        default="hard",
        help=(
            "Scenario execution before reading the matrix: hard = actually run "
            "the hard boundary scenarios and report their real statuses "
            "(default, #447); none = read-only, must be explicit; all = "
            "full-library validate run --all so the matrix gains real "
            "last_status (weekly)"
        ),
    )
    ap.add_argument("--json-out", default="")
    ap.add_argument("--md-out", default="")
    ap.add_argument(
        "--video-window-days",
        type=int,
        default=14,
        help=(
            "视频轨只聚合最近 N 天的项目（按目录名 YYYYMMDD，解析失败用 mtime）；"
            "0 = 不设窗口（默认 14）"
        ),
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    explicit = Path(args.scan_root) if args.scan_root else None
    env_dir = os.environ.get(PROJECTS_DIR_ENV, "").strip()
    extra = explicit or (Path(env_dir) if env_dir else None)
    projects = scan_projects(extra_root=extra)

    # 视频轨只看近 N 天的新项目：窗口外的旧项目不参与 pass/fail，改记历史债务。
    cutoff = _video_window_cutoff(date.today(), args.video_window_days)
    if cutoff is None:
        video_projects = list(projects)
        history_debt: list[dict] = []
    else:
        video_projects = [p for p in projects if date.fromisoformat(p["project_date"]) >= cutoff]
        window_ids = {p["project"] for p in video_projects}
        history_debt = [
            {
                "project": p["project"],
                "state": p["video_state"],
                "reason": ("" if p["video_state"] == "pass" else _track_red_reason(p, "视频轨")),
            }
            for p in projects
            if p["project"] not in window_ids and p["video_state"] != "unverified"
        ]

    # 三轨各自的候选集：文本/图文仍是全量项目，视频轨只认窗口内项目。
    # owner 2026-11-25：窗口内「没喂源材料 ⇒ V3 无输入」的项目属「不可判」，
    # 归历史债务单列，不占视频轨 pass/fail（否则该轨永久挂一条修不掉的红）。
    unjudgeable = [
        p
        for p in video_projects
        if isinstance(p.get("video_gates"), dict)
        and video_unjudgeable_no_source(p["video_gates"])
    ]
    if unjudgeable:
        unjudgeable_ids = {p["project"] for p in unjudgeable}
        video_projects = [p for p in video_projects if p["project"] not in unjudgeable_ids]
        history_debt.extend(
            {
                "project": p["project"],
                "state": p["video_state"],
                "reason": "V3 无输入：该项目没喂源材料（不可判，owner 2026-11-25 归历史债务）",
            }
            for p in unjudgeable
        )

    track_items = {"文本轨": projects, "图文轨": projects, "视频轨": video_projects}

    def _track(key: str, items: list[dict], *, fail_overrides: bool = False) -> dict:
        """单轨三态聚合（issue #361）：有 pass 即 pass；否则有证据即 fail；
        全体项目都无该轨证据 ⇒ unverified（不作能力宣称）。

        视频轨用 ``fail_overrides=True``：窗口内任一项目判红即整轨判红，
        否则一个 green 会把窗口里的 red 盖掉（``--video-window-days 0``
        回到全量时尤其明显）。文本/图文轨维持原「有 pass 即 pass」。
        """
        has_fail = any(p[key] == "fail" for p in items)
        has_pass = any(p[key] == "pass" for p in items)
        state = "unverified"
        if fail_overrides and has_fail:
            state = "fail"
        elif has_pass:
            state = "pass"
        elif has_fail:
            state = "fail"
        passing = [p["project"] for p in items if p[key] == "pass"]
        return {
            "ok": state == "pass",
            "state": state,
            "evidence": passing[:5],
            "count": len(passing),
        }

    tracks = {
        "文本轨": _track("text_state", track_items["文本轨"]),
        "图文轨": _track("image_state", track_items["图文轨"]),
        "视频轨": _track("video_state", track_items["视频轨"], fail_overrides=True),
    }
    fail_tracks = [k for k, v in tracks.items() if v["state"] == "fail"]
    unverified_tracks = [k for k, v in tracks.items() if v["state"] == "unverified"]
    gap = [k for k, v in tracks.items() if v["state"] != "pass"]
    executed: dict = {}
    if not args.skip_validate and args.validate_scope != "none":
        executed = run_validation_scope(args.python, args.validate_scope)
    vs = {} if args.skip_validate else validate_summary(args.python)
    if executed:
        vs["executed_scope"] = executed
    chain = _update_unexecuted_streak(
        "none" if args.skip_validate else args.validate_scope, executed
    )
    bench = _bench_snapshot()

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
        "video_window_days": args.video_window_days,
        "history_debt": history_debt,
        "bench_state": bench["bench_state"],
        "bench_branch": bench["bench_branch"],
        "bench_head": bench["bench_head"],
        "bench_sync_commit": bench.get("bench_sync_commit", ""),
        "validate": vs,
        "validation_chain": chain,
        "capability_debt": {
            "视频轨": {
                "registered_gates": list(VIDEO_GATES_CAPABILITY_DEBT),
                "skipped_in_evidence": sorted(
                    {
                        g
                        for p in video_projects
                        if p["video_ok"]
                        for g in p["video_gates"]["debt_skipped"]
                    }
                ),
                "reason": (
                    "四门无诚实生产者（#193 登记；V1 自 #387 起有生产者、"
                    "#414 起移出债集合，口径与 gate_inputs 审计统一）"
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
                (
                    p
                    for p in track_items[fail_tracks[0]]
                    if p[TRACK_STATE_KEYS[fail_tracks[0]]] == "fail"
                ),
                None,
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
        _bench_line(bench),
        f"- bench_state：{bench['bench_state']}",
    ]
    for name, v in tracks.items():
        state = v["state"]
        key = TRACK_STATE_KEYS[name]
        items = track_items[name]
        if state == "pass":
            ev = "、".join(v["evidence"]) if v["evidence"] else "无"
            md.append(f"- ✅ **{name}**：{v['count']} 个达标；证据：{ev}")
        elif state == "fail":
            reds = [
                f"{p['project']}: {_track_red_reason(p, name)}" for p in items if p[key] == "fail"
            ][:5]
            reds_line = "；".join(reds) or "无项目"
            md.append(f"- ❌ **{name}**：未达标；判红原因（前 5 个）：{reds_line}")
        else:
            md.append(f"- ⏳ **{name}**：未验证（无证据，不作能力宣称）")
        if name == "视频轨" and state == "fail":
            md.append(_video_track_note(items, v))
    md.append(f"- 历史债务：{len(history_debt)} 个（不参与判定）")
    md.extend(f"  - {h['project']}: {h['reason'] or h['state']}" for h in history_debt)
    if vs and "error" not in vs:
        # 「未过」与「未执行」分开报（#415）：last_status=None 是「没人跑过」，
        # 不是「跑红了」；最近一次 suite 记录的时间戳一并给出，读者能区分
        # 「从未执行」与「记录过期」。
        hard_passed = vs.get("hard_passed") or []
        hard_failed = vs.get("hard_failed") or []
        hard_unexec = vs.get("hard_unexecuted") or []
        record = vs.get("last_suite_record") or ""
        unreachable = vs.get("gates_unreachable")
        unreachable_names = vs.get("gates_unreachable_names") or []
        md += [
            "",
            "## 验证矩阵（自动生成，复用 automedia 自带）",
            f"- 场景 {vs['scenarios_total']} 条：{vs['scenario_status']}",
            f"- 最近整库 suite 记录：{record or '无（validation-runs/ 下没有 latest.txt）'}",
            f"- hard 场景 {vs['hard_total']} 条："
            f"已执行-通过 {len(hard_passed)}（{'、'.join(hard_passed) or '无'}）；"
            f"已执行-失败 {len(hard_failed)}（{'、'.join(hard_failed) or '无'}）；"
            f"未执行 {len(hard_unexec)}（{'、'.join(hard_unexec) or '无'}）",
            f"- 门：missing={vs['gates_missing']} unreachable={unreachable}"
            f"（{'、'.join(unreachable_names) or '名单读取失败，见 validate coverage'}）",
        ]
        scope = vs.get("executed_scope") or {}
        if scope:
            md.append(
                f"- 本次执行（--validate-scope {scope.get('scope')}）："
                + (
                    f"{len(scope.get('executed', []))} 条："
                    + "；".join(f"{e['scenario']}={e['status']}" for e in scope.get("executed", []))
                    if scope.get("scope") == "hard"
                    else f"status_counts={scope.get('status_counts')} "
                    f"run_dir={scope.get('run_dir') or '未记录'}"
                )
            )
        md.append(
            f"- 验证链：连续未执行 {chain['days']} 天；"
            f"本次{'已执行' if chain['executed_this_run'] else '未执行'}场景"
        )
        if chain["red"]:
            md.append(f"- ❌ **验证链连续 {chain['days']} 天未执行任何场景**（#447）")
    else:
        reason = "--skip-validate" if args.skip_validate else "矩阵读取失败"
        md += [
            "",
            "## 验证矩阵（未读取）",
            f"- 本次 {reason}：未执行场景（连续未执行 {chain['days']} 天）",
        ]
        if chain["red"]:
            md.append(f"- ❌ **验证链连续 {chain['days']} 天未执行任何场景**（#447）")
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
