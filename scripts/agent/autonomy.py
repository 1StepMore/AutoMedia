#!/usr/bin/env python3
"""autonomy.py — 让任何 agent / harness 拉下这个仓就能自驱的最小工具集。

设计原则（owner 2026-11-17）
--------------------------------------------------------------------------
「谁来做」不该靠口头交代，也不该写死在某一台机器上。仓里能写的东西必须写进仓：
读完 `AGENTS.md` → `docs/dev/autonomy.md` → 跑一遍 `python3 scripts/agent/autonomy.py selfcheck`
就知道：现在该不该我干、下一件干什么、怎么认领、什么情况下必须停手问 owner。

两类状态，别混
--------------------------------------------------------------------------
· **授权（local）**：`.agents/autonomy/lease.json` —— owner 说「交给你了」才存在，机器本地、不入库。
· **认领（remote）**：GitHub issue 标签 `status:claimed` + `owner:*` + 一条认领评论
  —— 全局唯一真相，
  另一台机器/另一个 harness 看得到。

授权优先于钟表：有租约就按租约干，没租约退回缺省时段（工作日 09:00–23:00 归本机侧，
其余归主人侧），避免两侧同时动手。

用法
--------------------------------------------------------------------------
    python3 scripts/agent/autonomy.py status
    python3 scripts/agent/autonomy.py start --goal "OL --help 契约全绿" --until 22:00 \
        --evidence "chat 2026-11-17"
    python3 scripts/agent/autonomy.py gate --need-minutes 60   # 自带目标闸（E7）
    python3 scripts/agent/autonomy.py next -n 3
    python3 scripts/agent/autonomy.py claim 350 --branch fix/350-x
    python3 scripts/agent/autonomy.py release 350 --reason done
    python3 scripts/agent/autonomy.py selfcheck

退出码：0 正常；2 用法/环境错；3 =「现在不该你干」（不是错误）。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
LEASE = ROOT / ".agents" / "autonomy" / "lease.json"
TZ = ZoneInfo("Asia/Shanghai")

MINE = "owner:code-auto"
HUMAN = "owner:human-agent"
CLAIMED = "status:claimed"
READY = "agent-ready"
SKIP_LABELS = {"pinned", "tracking", "blocked-decision", "常开", "勿关", "blocked:env"}
OWNER_PREFIX = "owner:"

NIGHT_START_HOUR = 23
DAY_START_HOUR = 9
DEFAULT_NEED_MINUTES = 30
MAX_LEASE_HOURS = 12
CLOSING_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[^\n]{0,40}?#(\d+)"
)


# ---------------------------------------------------------------- 时间判据
def lane_at(dt: datetime) -> tuple[str, str]:
    """缺省时段判据：工作日 09:00–23:00 本机侧，其余主人侧。"""
    if dt.weekday() >= 5:
        return HUMAN, "周末全天归主人侧"
    if dt.hour >= NIGHT_START_HOUR:
        return HUMAN, f"工作日 {NIGHT_START_HOUR}:00 起归主人侧"
    if dt.hour < DAY_START_HOUR:
        return HUMAN, f"{DAY_START_HOUR}:00 前的夜班尾段归主人侧"
    return MINE, f"工作日 {DAY_START_HOUR}:00–{NIGHT_START_HOUR}:00 归本机侧"


def parse_until(raw: str, now: datetime) -> datetime:
    """HH:MM（取最近未来时刻）或完整 ISO。"""
    if len(raw) <= 5 and ":" in raw:
        hh, mm = (int(x) for x in raw.split(":"))
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return cand if cand > now else cand + timedelta(days=1)
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def read_lease(path: Path | None = None) -> dict:
    path = path or LEASE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_lease(d: dict, path: Path | None = None) -> None:
    path = path or LEASE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def default_lane() -> str:
    """本机立场：AUTONOMY_LANE 环境变量 > .agents/autonomy/lane 文件 > 缺省本机侧。

    三仓各一份工具、两侧 harness 共用同一批仓，缺省值只能有一个；所以"我是哪一侧"
    必须能在本机声明，否则主人侧照文档跑 gate 会拿 exit 3（"不是你的班"）误以为不能开工。
    主人侧一行：echo owner:human-agent > .agents/autonomy/lane
    """
    env = os.environ.get("AUTONOMY_LANE", "").strip()
    if env:
        return env
    f = ROOT / ".agents" / "autonomy" / "lane"
    if f.exists():
        v = f.read_text(encoding="utf-8").strip()
        if v:
            return v
    return MINE


def effective_lane(now: datetime, path: Path | None = None) -> tuple[str, str, dict]:
    """返回 (lane, 理由, 租约状态)。租约有效 ⇒ 租约说了算。"""
    d = read_lease(path)
    if d.get("status") == "active":
        until = datetime.fromisoformat(d["until"])
        if now < until:
            return (
                d.get("lane", MINE),
                f"租约有效，到 {d['until']}（目标：{d.get('goal', '')}）",
                d,
            )
        return (*lane_at(now), {**d, "_expired": True})
    return (*lane_at(now), d)


# ---------------------------------------------------------------- 取活
def pick(issues: list[dict], prs: list[dict], owner: str | None = None) -> list[dict]:
    """从 issue/PR 列表里挑出「我现在能开工」的条目，按优先级排序。

    可开工 = agent-ready ∧ 无任何 owner:* ∧ 无 status:claimed ∧ 未被 open PR 认领。
    """
    owner = owner or default_lane()
    claimed_by_pr: set[int] = set()
    for p in prs:
        for m in re.finditer(r"#(\d+)", p.get("title") or ""):
            claimed_by_pr.add(int(m.group(1)))
        for m in CLOSING_RE.finditer(p.get("body") or ""):
            claimed_by_pr.add(int(m.group(1)))

    out = []
    for it in issues:
        labels = {lbl["name"] for lbl in it.get("labels", [])}
        if labels & SKIP_LABELS or READY not in labels:
            continue
        if any(lbl.startswith(OWNER_PREFIX) for lbl in labels) or CLAIMED in labels:
            continue
        if int(it["number"]) in claimed_by_pr:
            continue
        # 优先级：bug > 其余；同类按编号升序（老单先做，避免烂尾）
        out.append({**it, "_prio": 0 if "bug" in labels else 1})
    return sorted(out, key=lambda x: (x["_prio"], int(x["number"])))


def _gh(args: list[str], timeout: int = 60) -> str:
    env = {k: v for k, v in os.environ.items() if "PROXY" not in k.upper()}
    env["NO_PROXY"] = "*"
    r = subprocess.run(
        [shutil.which("gh") or "gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} 失败：{r.stderr.strip()[:300]}")
    return r.stdout


def _gh_json(args: list[str]) -> list[dict]:
    out = _gh(args)
    data = json.loads(out) if out.strip() else []
    return data if isinstance(data, list) else [data]


def _gh_obj(args: list[str]) -> dict:
    out = _gh(args)
    data = json.loads(out) if out.strip() else {}
    return data if isinstance(data, dict) else {}


def repo_slug() -> str:
    return _gh(
        ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    ).strip()


# ---------------------------------------------------------------- 子命令
def cmd_status(a: argparse.Namespace) -> int:
    now = (
        datetime.fromisoformat(a.now).replace(tzinfo=TZ) if a.now else datetime.now(TZ)
    )
    lane, why, lease = effective_lane(now)
    d = {
        "now": now.isoformat(timespec="seconds"),
        "lane": lane,
        "reason": why,
        "lease": lease,
        "repo": None,
    }
    with contextlib.suppress(Exception):
        d["repo"] = repo_slug()
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1, default=str))
    else:
        print(f"仓库　　：{d['repo'] or '(未识别)'}")
        print(f"当前归属：{lane}")
        print(f"理由　　：{why}")
        if lease.get("status") == "active":
            left = int(
                (datetime.fromisoformat(lease["until"]) - now).total_seconds() // 60
            )
            print(f"租约剩余：{left} 分钟｜目标：{lease.get('goal', '')}")
    return 0


def cmd_start(a: argparse.Namespace) -> int:
    now = (
        datetime.fromisoformat(a.now).replace(tzinfo=TZ) if a.now else datetime.now(TZ)
    )
    until = parse_until(a.until, now) if a.until else (now + timedelta(hours=4))
    hours = (until - now).total_seconds() / 3600
    if hours <= 0:
        print("REFUSE: --until 必须晚于现在", file=sys.stderr)
        return 2
    if hours > MAX_LEASE_HOURS and not a.allow_long:
        print(
            f"REFUSE: 租约 {hours:.1f}h > {MAX_LEASE_HOURS}h 上限（确认要长跑加 --allow-long）",
            file=sys.stderr,
        )
        return 2
    write_lease(
        {
            "lane": a.lane,
            "goal": a.goal,
            "started_at": now.isoformat(timespec="seconds"),
            "until": until.isoformat(timespec="seconds"),
            "granted_by": a.granted_by,
            "evidence": a.evidence,
            "status": "active",
        }
    )
    print(
        f"租约已立：{a.lane} → {until.isoformat(timespec='seconds')}"
        f"（{hours:.1f}h）｜目标：{a.goal}"
    )
    return 0


def cmd_stop(a: argparse.Namespace) -> int:
    d = read_lease()
    if not d:
        print("没有租约", file=sys.stderr)
        return 2
    d.update(
        status="stopped",
        stop_reason=a.reason,
        stopped_at=datetime.now(TZ).isoformat(timespec="seconds"),
    )
    write_lease(d)
    print(f"租约已收：{a.reason}")
    return 0


def cmd_gate(a: argparse.Namespace) -> int:
    now = (
        datetime.fromisoformat(a.now).replace(tzinfo=TZ) if a.now else datetime.now(TZ)
    )
    lane, why, lease = effective_lane(now)
    if lane != a.lane:
        print(f"REFUSE: 当前归属 {lane}（{why}），不是 {a.lane}", file=sys.stderr)
        return 3
    if lease.get("status") == "active" and a.need_minutes:
        left = int((datetime.fromisoformat(lease["until"]) - now).total_seconds() // 60)
        if left < a.need_minutes:
            print(
                f"REFUSE: 租约剩 {left} 分钟 < 需要 {a.need_minutes}（排空保护）",
                file=sys.stderr,
            )
            return 3
    print(f"OK: {a.lane} 在班（{why}）")
    if not a.skip_goal:
        blocked = goal_gate()
        if blocked is not None:
            return blocked
    return 0


def cmd_next(a: argparse.Namespace) -> int:
    if not a.skip_goal:
        blocked = goal_gate()
        if blocked is not None:
            return blocked
    repo = repo_slug()
    issues = _gh_json(
        [
            "issue",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,title,labels,updatedAt",
        ]
    )
    prs = _gh_json(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,title,body",
        ]
    )
    picked = pick(issues, prs)[: a.n]
    if a.json:
        print(
            json.dumps(
                [{"number": i["number"], "title": i["title"]} for i in picked],
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0
    if not picked:
        print("没有可开工项（agent-ready 且无归属、无 open PR）")
        return 0
    for i in picked:
        print(f"#{i['number']} {i['title'][:80]}")
    return 0


def cmd_claim(a: argparse.Namespace) -> int:
    repo = repo_slug()
    cur = _gh_obj(
        ["issue", "view", str(a.issue), "-R", repo, "--json", "labels,number,title"]
    )
    labels = {lbl["name"] for lbl in cur.get("labels", [])}
    owners = {lbl for lbl in labels if lbl.startswith(OWNER_PREFIX)}
    if CLAIMED in labels and owners and a.owner not in owners:
        print(
            f"REFUSE: #{a.issue} 已被 {sorted(owners)} 认领（status:claimed）",
            file=sys.stderr,
        )
        return 3
    if owners and a.owner not in owners:
        print(
            f"REFUSE: #{a.issue} 带 {sorted(owners)} 标签，归属不是 {a.owner}",
            file=sys.stderr,
        )
        return 3
    _gh(
        [
            "issue",
            "edit",
            str(a.issue),
            "-R",
            repo,
            "--add-label",
            CLAIMED,
            "--add-label",
            a.owner,
        ]
    )
    body = (
        f"**认领**\n\n- 接活方：`{a.owner}`\n"
        f"- 时间：{datetime.now(TZ).isoformat(timespec='seconds')}\n"
        f"- 分支：`{a.branch or '(未指定)'}`\n"
        f"- 撞车声明：认领前已核无 `status:claimed`、无关联 open PR；"
        f"如另一侧也在动，请在下方留言，我停手。"
    )
    _gh(["issue", "comment", str(a.issue), "-R", repo, "--body", body])
    print(f"已认领 #{a.issue} → {a.owner}")
    return 0


def cmd_release(a: argparse.Namespace) -> int:
    repo = repo_slug()
    _gh(["issue", "edit", str(a.issue), "-R", repo, "--remove-label", CLAIMED])
    _gh(
        [
            "issue",
            "comment",
            str(a.issue),
            "-R",
            repo,
            "--body",
            f"**放回队列**：{a.reason}（{datetime.now(TZ).isoformat(timespec='seconds')}）",
        ]
    )
    print(f"已放回 #{a.issue}（{a.reason}）")
    return 0


# ---------------------------------------------------------------- 目标
GOALS = ROOT / "docs" / "dev" / "goals.md"
GOAL_CMD_RE = re.compile(r"<!--\s*goal-cmd:\s*(.+?)\s*-->")


def goal_cmd() -> list[str] | None:
    """从 docs/dev/goals.md 抽判据命令。约定：exit 0 = 当前目标达标。"""
    if not GOALS.exists():
        return None
    m = GOAL_CMD_RE.search(GOALS.read_text(encoding="utf-8"))
    if not m:
        return None
    cmd = shlex.split(m.group(1))
    if cmd and cmd[0] in ("python", "python3"):
        cmd = [sys.executable, *cmd[1:]]
    return cmd


def goal_verdict(rc: int) -> str:
    """退出码 → 结论。

    0 ⇒ ACHIEVED；2 ⇒ ERROR（判据跑不起来，属环境问题，**不能**当成"未达标"继续硬推）；
    其它非 0 ⇒ ACTIVE（真的还有差距）。
    """
    if rc == 0:
        return "ACHIEVED"
    if rc == 2:
        return "ERROR"
    return "ACTIVE"


def cmd_goal(a: argparse.Namespace) -> int:
    cmd = shlex.split(a.cmd) if a.cmd else goal_cmd()
    if not cmd:
        print(
            "REFUSE: 找不到判据命令（docs/dev/goals.md 缺 `<!-- goal-cmd: … -->`，或加 --cmd）",
            file=sys.stderr,
        )
        return 2
    try:
        r = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=a.timeout
        )
    except subprocess.TimeoutExpired:
        print(f"REFUSE: 判据命令超过 {a.timeout}s", file=sys.stderr)
        return 2
    out = (r.stdout or "").strip() or (r.stderr or "").strip()
    tail = out.splitlines()[-a.tail :] if out else []
    verdict = goal_verdict(r.returncode)
    if a.json:
        print(
            json.dumps(
                {"verdict": verdict, "exit": r.returncode, "cmd": cmd, "tail": tail},
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        print(f"判据命令：{' '.join(cmd)}")
        print(f"退出码　：{r.returncode}  ⇒ {verdict}")
        for line in tail:
            print(f"  {line}")
        if verdict == "ACHIEVED":
            print(
                "\nACHIEVED：当前目标已达标（E7）。按 docs/dev/goals.md 四步走，然后停手："
            )
            print("  1) autonomy.py stop --reason done")
            print("  2) 开 [goal-achieved] issue，贴上面原始输出")
            print("  3) goals.md 里下一阶段标 asked-owner")
            print("  4) 停止从 next 领活")
        elif verdict == "ERROR":
            print(
                "\nERROR：判据命令跑不起来（环境/用法问题，E4 类）"
                "——不要硬推，先修环境或报 owner。"
            )
        else:
            print("\nACTIVE：未达标，继续推进当前目标。")
    if verdict == "ACHIEVED":
        return 0
    return 2 if verdict == "ERROR" else 4


GOAL_CACHE = ROOT / ".agents" / "autonomy" / "goal.json"


def goal_check(max_age_s: int = 600) -> tuple[str, int]:
    """跑（或复用缓存里的）目标判据，返回 (verdict, rc)。

    缓存默认 10 分钟：`gate` / `next` 每个班次都会调用，没必要每次都跑一遍矩阵。
    """
    if GOAL_CACHE.exists():
        with contextlib.suppress(Exception):
            d = json.loads(GOAL_CACHE.read_text(encoding="utf-8"))
            if time.time() - float(d.get("at", 0)) < max_age_s:
                return str(d["verdict"]), int(d["rc"])
    cmd = goal_cmd()
    if not cmd:
        return "NONE", 0
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
        rc = r.returncode
        tail = (r.stdout or r.stderr or "")[-400:]
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        rc, tail = 2, f"{type(exc).__name__}: {exc}"
    verdict = goal_verdict(rc)
    with contextlib.suppress(OSError):
        GOAL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        GOAL_CACHE.write_text(
            json.dumps(
                {"at": time.time(), "verdict": verdict, "rc": rc, "tail": tail},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return verdict, rc


def goal_gate() -> int | None:
    """目标闸：不需要任何人记得跑 goal —— gate / next 自动判。

    ACHIEVED ⇒ 5（别领活，去走 goals.md 的四步）
    ERROR    ⇒ 6（判据跑不起来 = 环境问题，先修环境，别当成"没达标"硬推）
    ACTIVE / NONE ⇒ None（照常干活）
    """
    verdict, _rc = goal_check()
    if verdict == "ACHIEVED":
        print(
            "E7 目标已达成（`docs/dev/goals.md` 的判据 exit 0）：\n"
            "  1) autonomy.py stop --reason done\n"
            "  2) 开 [goal-achieved] issue 贴原始输出\n"
            "  3) 下一阶段交回 owner（P2 标 asked-owner）\n"
            "  4) 停手——别自己找活干"
        )
        return 5
    if verdict == "ERROR":
        print(
            "⚠️ 目标判据跑不起来（E4 环境问题，不是「没达标」）：先修环境或报 owner，别硬推。",
            file=sys.stderr,
        )
        return 6
    return None


def cmd_selfcheck(a: argparse.Namespace) -> int:
    """这台机器 + 这个 clone 能不能自驱？缺什么直接说缺什么。"""
    problems, notes = [], []
    v = sys.version_info
    if v < (3, 10):
        problems.append(f"Python {v.major}.{v.minor} < 3.10")
    else:
        notes.append(f"Python {v.major}.{v.minor}.{v.micro} ✓")

    for rel in ("AGENTS.md", "docs/dev/autonomy.md", ".agents/roles"):
        (notes if (ROOT / rel).exists() else problems).append(
            f"{rel} {'✓' if (ROOT / rel).exists() else '缺失'}"
        )

    try:
        me = _gh(["api", "user", "--jq", ".login"]).strip()
        notes.append(f"gh 已登录：{me} ✓")
    except Exception as e:
        problems.append(f"gh 不可用：{str(e)[:120]}")

    repo = None
    try:
        repo = repo_slug()
        labels = {
            lbl["name"]
            for lbl in _gh_json(
                ["label", "list", "-R", repo, "--limit", "100", "--json", "name"]
            )
        }
        need = {READY, CLAIMED, MINE, HUMAN}
        missing = need - labels
        if missing:
            problems.append(
                f"仓库缺标签 {sorted(missing)}（先 `gh label create <name>` 再开工）"
            )
        else:
            notes.append(f"标签齐全 ✓（{repo}）")
    except Exception as e:
        problems.append(f"读仓库标签失败：{str(e)[:120]}")

    print("自检结果：")
    for n in notes:
        print(f"  ✓ {n}")
    for p in problems:
        print(f"  ✗ {p}")
    if problems:
        print(
            "\n⇒ 不能自驱：先补齐上面 ✗"
            "（这些多数是 harness 侧要提供的，见 docs/dev/autonomy.md §4）"
        )
        return 2
    print("\n⇒ 可以自驱：`autonomy.py status` 看在不在班，`next` 拿下一件活。")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="仓内自驱工具（授权/取活/认领/自检）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s.add_argument("--now")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("start")
    s.add_argument("--goal", required=True)
    s.add_argument("--until", default=None)
    s.add_argument("--lane", default=default_lane())
    s.add_argument("--granted-by", default="owner")
    s.add_argument("--evidence", default="")
    s.add_argument("--allow-long", action="store_true")
    s.add_argument("--now")
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("stop")
    s.add_argument(
        "--reason",
        default="owner-reclaim",
        choices=["done", "blocked", "owner-reclaim", "expired-manual"],
    )
    s.set_defaults(fn=cmd_stop)

    s = sub.add_parser("gate")
    s.add_argument("--lane", default=default_lane())
    s.add_argument("--need-minutes", type=int, default=0)
    s.add_argument("--now")
    s.add_argument("--skip-goal", action="store_true", help="跳过目标闸（调试用）")
    s.set_defaults(fn=cmd_gate)

    s = sub.add_parser("next")
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--json", action="store_true")
    s.add_argument("--skip-goal", action="store_true", help="跳过目标闸（调试用）")
    s.set_defaults(fn=cmd_next)

    s = sub.add_parser("claim")
    s.add_argument("issue", type=int)
    s.add_argument("--owner", default=default_lane())
    s.add_argument("--branch", default="")
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("release")
    s.add_argument("issue", type=int)
    s.add_argument("--reason", default="not-mine")
    s.set_defaults(fn=cmd_release)

    s = sub.add_parser("goal")
    s.add_argument("--cmd", default=None)
    s.add_argument("--timeout", type=int, default=1800)
    s.add_argument("--tail", type=int, default=12)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_goal)

    s = sub.add_parser("selfcheck")
    s.set_defaults(fn=cmd_selfcheck)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
