"""scripts/agent/autonomy.py 的判据测试（owner 2026-11-17：读仓就能自驱）。

重点测三件容易写错、错了就会出事的东西：
  1. 缺省时段的边界（宁可少算，不能两边都算成自己的）；
  2. 租约优先于时钟，且到期后自动退回时钟（不许留下悬空授权）；
  3. 取活口径：有 owner 标签 / 已认领 / 已被 open PR 认领的，一律不进名单。
"""

import importlib.util
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "agent_autonomy", Path(__file__).resolve().parents[1] / "scripts" / "agent" / "autonomy.py"
)
assert _spec is not None and _spec.loader is not None
au = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(au)

TZ = au.TZ


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=TZ)


# ---------------------------------------------------------------- 时段
def test_default_lane_boundaries():
    assert au.lane_at(_dt("2026-11-16T09:00:00"))[0] == au.MINE  # 周一 09:00
    assert au.lane_at(_dt("2026-11-16T22:59:00"))[0] == au.MINE
    assert au.lane_at(_dt("2026-11-16T23:00:00"))[0] == au.HUMAN  # 周一 23:00
    assert au.lane_at(_dt("2026-11-17T08:59:00"))[0] == au.HUMAN
    assert au.lane_at(_dt("2026-11-21T12:00:00"))[0] == au.HUMAN  # 周六
    assert au.lane_at(_dt("2026-11-23T09:00:00"))[0] == au.MINE  # 周一 09:00 交回


def test_parse_until_rolls_forward():
    now = _dt("2026-11-17T22:00:00")
    assert au.parse_until("23:30", now) == _dt("2026-11-17T23:30:00")
    assert au.parse_until("09:00", now) == _dt("2026-11-18T09:00:00")  # 已过 ⇒ 次日
    assert au.parse_until("2026-11-18T01:00:00", now) == _dt("2026-11-18T01:00:00")


# ---------------------------------------------------------------- 租约
def test_lease_overrides_clock(tmp_path):
    lease = tmp_path / "lease.json"
    au.write_lease(
        {"lane": au.MINE, "goal": "g", "status": "active", "until": "2026-11-18T02:00:00+08:00"},
        lease,
    )
    lane, why, _ = au.effective_lane(_dt("2026-11-17T23:30:00"), lease)  # 本属主人侧
    assert lane == au.MINE and "租约" in why


def test_expired_lease_falls_back_to_clock(tmp_path):
    lease = tmp_path / "lease.json"
    au.write_lease(
        {"lane": au.MINE, "goal": "g", "status": "active", "until": "2026-11-17T14:00:00+08:00"},
        lease,
    )
    lane, _why, d = au.effective_lane(_dt("2026-11-17T23:30:00"), lease)
    assert lane == au.HUMAN and d.get("_expired") is True


def test_stopped_lease_is_ignored(tmp_path):
    lease = tmp_path / "lease.json"
    au.write_lease(
        {"lane": au.MINE, "goal": "g", "status": "stopped", "until": "2026-11-18T02:00:00+08:00"},
        lease,
    )
    assert au.effective_lane(_dt("2026-11-17T23:30:00"), lease)[0] == au.HUMAN


# ---------------------------------------------------------------- 取活
def _issue(n, labels, title="t"):
    return {"number": n, "title": title, "labels": [{"name": x} for x in labels], "updatedAt": ""}


def test_pick_excludes_owned_and_claimed():
    issues = [
        _issue(1, ["agent-ready", "bug"]),  # 可开工
        _issue(2, ["agent-ready", "bug", "owner:human-agent"]),  # 已归属
        _issue(3, ["agent-ready", "status:claimed"]),  # 已认领
        _issue(4, ["agent-ready", "owner:master"]),  # 等拍板
        _issue(5, ["agent-ready", "pinned"]),  # 常开件
        _issue(6, ["bug"]),  # 非 ready
    ]
    got = [i["number"] for i in au.pick(issues, [])]
    assert got == [1]


def test_pick_excludes_issues_already_in_open_pr():
    issues = [_issue(10, ["agent-ready", "bug"]), _issue(11, ["agent-ready", "bug"])]
    prs = [
        {"title": "fix(tests): something (suite#10)", "body": ""},
        {"title": "fix: other", "body": "Closes #11\n"},
    ]
    assert au.pick(issues, prs) == []


def test_pick_priority_bug_first_then_oldest():
    issues = [
        _issue(30, ["agent-ready"]),
        _issue(12, ["agent-ready", "bug"]),
        _issue(9, ["agent-ready", "bug"]),
    ]
    assert [i["number"] for i in au.pick(issues, [])] == [9, 12, 30]


def test_new_manifest_is_committed_state_not_local_state():
    # 租约必须 gitignore（本机状态），否则一台机器的授权会"传染"给另一台
    root = Path(__file__).resolve().parents[1]
    assert ".agents/autonomy/" in (root / ".gitignore").read_text(encoding="utf-8")


def test_goal_cmd_declared_in_goals_md():
    # 目标必须用可执行判据表达，不接受「我觉得差不多了」
    cmd = au.goal_cmd()
    assert cmd and "nightly_gap.py" in " ".join(cmd)


def test_goal_verdict_only_zero_is_achieved():
    assert au.goal_verdict(0) == "ACHIEVED"
    assert au.goal_verdict(1) == "ACTIVE"
    # 2 = 判据跑不起来（环境问题）⇒ ERROR，不能伪装成"未达标"让 agent 继续硬推
    assert au.goal_verdict(2) == "ERROR"
