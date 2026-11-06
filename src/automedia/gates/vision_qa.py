"""V1 Vision QA Gate — per-entry visual quality assurance.

Checks:
    1. mid_frame_valid     — mid-frame image exists and is readable
    2. end_silence_valid   — end-silence frame image exists and is readable
    3. all_entries_passed  — all entries passed their individual QA
    4. red_line_6          — full coverage (not sampling), every entry checked

Red Line 6: Every entry must be individually QA'd (no sampling).
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result, missing_input_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "mid_frame_valid",
    "end_silence_valid",
    "all_entries_passed",
    "red_line_6",
]


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_mid_frame_valid(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 1: every *judged* entry has a valid mid_frame_path.

    中文说明（#387）：未判定（``checked=False``）的场次，帧可能因抽取失败而
    缺失——那由 ``red_line_6`` 的 unjudged 记账负责，不在这里产生关于空值的
    失败；已判定（面板短路/将来的 VLM）的场次必须有帧，缺了就是生产者缺陷。
    """
    name = "mid_frame_valid"
    if not entries:
        return {"name": name, "passed": False, "detail": "no entries provided"}
    missing = [
        i for i, e in enumerate(entries) if e.get("checked", False) and not e.get("mid_frame_path")
    ]
    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"entries {missing} missing mid_frame_path",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(entries)} entries have mid_frame_path",
    }


def _check_end_silence_frame_valid(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 2: every *judged* entry has a valid end_silence_frame_path."""
    name = "end_silence_valid"
    if not entries:
        return {"name": name, "passed": False, "detail": "no entries provided"}
    missing = [
        i
        for i, e in enumerate(entries)
        if e.get("checked", False) and not e.get("end_silence_frame_path")
    ]
    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"entries {missing} missing end_silence_frame_path",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(entries)} entries have end_silence_frame_path",
    }


def _check_all_entries_passed(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 3: every *judged* entry has qa_passed=True.

    中文说明：未判定（``checked=False`` 且 ``verdict`` 以 ``unjudged`` 开头）
    的场次不在此判 fail——它们的记账在 ``red_line_6`` 里；但只要有一个已判定
    的场次不通过，整门失败（负样本验收路径，#387）。
    """
    name = "all_entries_passed"
    if not entries:
        return {"name": name, "passed": False, "detail": "no entries provided"}
    failed = [
        i
        for i, e in enumerate(entries)
        if e.get("checked", False) and not e.get("qa_passed", False)
    ]
    if failed:
        return {"name": name, "passed": False, "detail": f"entries {failed} failed vision QA"}
    unjudged = sum(1 for e in entries if not e.get("checked", False))
    if unjudged:
        return {
            "name": name,
            "passed": True,
            "detail": (
                f"all judged entries passed vision QA ({unjudged} scene(s) "
                f"recorded unjudged — see red_line_6)"
            ),
        }
    return {"name": name, "passed": True, "detail": f"all {len(entries)} entries passed vision QA"}


def _check_red_line_6(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 4 (Red Line 6): full coverage — every entry must be checked, no sampling.

    中文说明：生产者（``vision_entries``，#387）对无法判定的场次写
    ``checked=False`` 且 ``verdict`` 以 ``unjudged`` 开头——这类场次在此**记账**
    （子检查标 ``skipped``，不静默 pass）；其余未判定场次（没有 unjudged 标记，
    多半是生产者缺位或测试造的裸数据）仍然按红线判 fail。
    """
    name = "red_line_6"
    if not entries:
        return {
            "name": name,
            "passed": False,
            "detail": "no entries to verify (Red Line 6: full coverage required)",
        }
    unchecked = [i for i, e in enumerate(entries) if not e.get("checked", False)]
    if unchecked:
        unjudged = [
            i for i in unchecked if str(entries[i].get("verdict", "")).startswith("unjudged")
        ]
        if len(unjudged) == len(unchecked):
            scenes = [entries[i].get("scene_id", i + 1) for i in unjudged]
            return {
                "name": name,
                "passed": True,
                "status": "skipped",
                "detail": (
                    f"scenes {scenes} recorded unjudged — no vision-capable model "
                    f"configured and no text panel to short-circuit; not counted as pass"
                ),
            }
        plain = [i for i in unchecked if i not in unjudged]
        return {
            "name": name,
            "passed": False,
            "detail": f"entries {plain} not checked — Red Line 6 requires full coverage",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"Red Line 6 satisfied: all {len(entries)} entries checked (full coverage)",
    }


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# V1VisionQA gate
# ---------------------------------------------------------------------------


class V1VisionQA(BaseGate):
    """V1 Vision QA Gate — per-entry visual quality assurance (Red Line 6).

    ``gate_context`` expected keys:
        - ``entries``: list of dicts, each with:
            - ``mid_frame_path``: str
            - ``end_silence_frame_path``: str
            - ``qa_passed``: bool (result of vision QA)
            - ``checked``: bool (whether entry was actually judged)
            - ``verdict`` (optional, #387): ``"panel …"`` for text-panel
              short-circuits, ``"unjudged: …"`` when no vision model exists —
              unjudged scenes are accounted in ``red_line_6`` (skipped with a
              reason, never a silent pass), never counted as failures
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Producer: ``pipelines/vision_entries.build_vision_entries`` (issue #387) —
    per-scene mid/end frames from the rendered video.  When *no* entry is
    judgeable the whole gate reports ``skipped`` with the accounting in its
    reason instead of a hollow pass.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V1"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V1 vision QA checks and return structured result."""
        if not gate_context.get("hyperframes_available", True):
            return {
                "passed": True,
                "gate": "V1",
                "status": "skipped",
                "reason": "HyperFrames not installed — video QA skipped",
            }

        # ``entries`` (per-scene frame paths + QA verdicts) is produced by the
        # video pipeline.  Absent means there is no rendered scene to inspect.
        skipped = missing_input_result("V1", gate_context, ("entries",))
        if skipped is not None:
            return skipped

        entries: list[dict[str, Any]] = gate_context.get("entries", [])
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        # #387：entries 由 ``pipelines/vision_entries`` 生产——每场都有抽好的帧
        # 与裁决字段。当**没有任何场次可判定**、且未判定场次都带 ``unjudged``
        # 标记（生产者的如实记账，而非裸数据）时，整门 skip 并记账；裸的
        # 未检查数据仍交给 red_line_6 判 fail。
        judged = [e for e in entries if e.get("checked", False)]
        all_unjudged = (
            bool(entries)
            and not judged
            and all(str(e.get("verdict", "")).startswith("unjudged") for e in entries)
        )
        if all_unjudged:
            paths = "; ".join(
                str(e.get("mid_frame_path", "")) for e in entries[:3] if e.get("mid_frame_path")
            )
            return {
                "passed": True,
                "gate": "V1",
                "status": "skipped",
                "reason": (
                    f"V1 entries produced ({len(entries)} scene(s)) but none judgeable — "
                    f"no vision-capable model configured and no text panel to "
                    f"short-circuit; frames recorded unjudged ({paths}…)"
                ),
            }

        check_fns: list[tuple[str, Any]] = [
            ("mid_frame_valid", lambda: _check_mid_frame_valid(entries)),
            ("end_silence_valid", lambda: _check_end_silence_frame_valid(entries)),
            ("all_entries_passed", lambda: _check_all_entries_passed(entries)),
            ("red_line_6", lambda: _check_red_line_6(entries)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V1", expected_suffix=".")
