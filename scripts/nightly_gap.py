#!/usr/bin/env python3
"""nightly_gap.py — 不眠计划 · AutoMedia 差距计算器（L2-a）

把「当前产出 vs 完成定义（DoD）」算成机器可读矩阵。
**冻结区**：coding agent 只跑、不改。

DoD（见 docs/dev/plans/NIGHTLY.md，与 L1 一致）：三条轨各有 ≥1 次真模型端到端跑，
且产物落在**持久目录**（repo 内，非 /tmp）。

三轨判定（全部机械化，尽量少主观）：
  文本轨   01_content/drafts/ 里有 ≥1 个 ≥500B 的 md，且 cost_log.jsonl 非空
  图文轨   02_images/ 里有 ≥1 个 ≥1KB 的图片
  视频轨   03_video/ 里有 ≥1 个 ≥10KB 的视频

用法：python3 scripts/nightly_gap.py [--json-out F] [--md-out F]
退出码：0 = 三轨全达标 / 1 = 仍有差距 / 2 = 用法或环境错误
"""
from __future__ import annotations

import argparse
import json
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
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VID_EXT = {".mp4", ".mov", ".webm", ".mkv"}


def _files(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.is_file()] if d.is_dir() else []


def _biggest(files: list[Path], exts: set[str] | None = None) -> int:
    cand = [f for f in files if exts is None or f.suffix.lower() in exts]
    return max((f.stat().st_size for f in cand), default=0)


def scan_projects() -> list[dict]:
    out: list[dict] = []
    for d in sorted(REPO.iterdir()):
        if not d.is_dir() or not PROJECT_RE.match(d.name):
            continue
        drafts = _files(d / "01_content" / "drafts")
        images = _files(d / "02_images")
        videos = _files(d / "03_video")
        cost = d / "cost_log.jsonl"
        cost_lines = 0
        if cost.is_file():
            cost_lines = sum(1 for ln in cost.read_text(errors="ignore").splitlines()
                             if ln.strip())
        draft_max = _biggest(drafts, {".md"})
        img_max = _biggest(images, IMG_EXT)
        vid_max = _biggest(videos, VID_EXT)
        out.append({
            "project": d.name,
            "cost_log_lines": cost_lines,
            "draft_count": len(drafts),
            "draft_max_bytes": draft_max,
            "image_max_bytes": img_max,
            "video_max_bytes": vid_max,
            "has_pipeline_md5": (d / "pipeline_md5.json").is_file(),
            "text_ok": cost_lines > 0 and draft_max >= MIN_DRAFT_BYTES,
            "image_ok": img_max >= MIN_IMAGE_BYTES,
            "video_ok": vid_max >= MIN_VIDEO_BYTES,
        })
    return out


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
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO,  # noqa: S603
                           timeout=600)
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
        "hard_not_passed": [s["name"] for s in sc
                            if s.get("hard") and s.get("last_status") != "passed"],
        "gates_missing": summ.get("gates_missing"),
        "gates_unreachable": summ.get("gates_unreachable"),
        "mcp_missing": summ.get("mcp_missing"),
        "cli_missing": summ.get("cli_missing"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nightly_gap.py")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--md-out", default="")
    args = ap.parse_args(argv)

    projects = scan_projects()
    text = [p["project"] for p in projects if p["text_ok"]]
    image = [p["project"] for p in projects if p["image_ok"]]
    video = [p["project"] for p in projects if p["video_ok"]]
    tracks = {
        "文本轨": {"ok": bool(text), "evidence": text[:5], "count": len(text)},
        "图文轨": {"ok": bool(image), "evidence": image[:5], "count": len(image)},
        "视频轨": {"ok": bool(video), "evidence": video[:5], "count": len(video)},
    }
    gap = [k for k, v in tracks.items() if not v["ok"]]
    vs = {} if args.skip_validate else validate_summary(args.python)

    result = {
        "schema": "nightly-gap/1",
        "project": "AutoMedia",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_units": 3,
        "passing_units": 3 - len(gap),
        "gap": gap,
        "tracks": tracks,
        "projects": projects,
        "validate": vs,
    }
    if gap:
        result["exit_reason"] = f"{len(gap)} / 3 条轨未达标"

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    verdict = ("- 判定：**三轨全达标（机器可判部分完成）**" if not gap
               else f"- 判定：**{len(gap)} / 3 条轨未达标**")
    md = ["# AutoMedia 差距矩阵", "", verdict, "",
          f"- 项目目录：{len(projects)} 个（真模型 cost_log 非空："
          f"{sum(1 for p in projects if p['cost_log_lines'] > 0)} 个）"]
    for name, v in tracks.items():
        mark = "✅" if v["ok"] else "❌"
        ev = "、".join(v["evidence"]) if v["evidence"] else "无"
        md.append(f"- {mark} **{name}**：{v['count']} 个达标；证据：{ev}")
    if vs and "error" not in vs:
        md += ["", "## 验证矩阵（自动生成，复用 automedia 自带）",
               f"- 场景 {vs['scenarios_total']} 条：{vs['scenario_status']}",
               f"- hard 场景 {vs['hard_total']} 条，未过：{vs['hard_not_passed'] or '无'}",
               f"- 门：missing={vs['gates_missing']} unreachable={vs['gates_unreachable']}"]
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
