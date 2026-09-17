"""Shared gate result builder.

Provides :func:`build_gate_result` — the single implementation of the
``_build_result`` helper that was previously duplicated across all gate
modules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypedDict

from structlog import get_logger

if TYPE_CHECKING:
    from automedia.gates._context import GateContext

log = get_logger(__name__)


class CheckResult(TypedDict):
    """Individual check dict produced by a gate check function.

    Every gate check returns at minimum ``name``, ``passed``, and ``detail``.
    Additional keys (e.g. ``method``, ``confidence``) may be present when
    the check was performed by an LLM.
    """

    name: str
    passed: bool
    detail: str


class ExpectedVsActual(TypedDict):
    """Expected-vs-actual comparison for the first failing check."""

    check: str
    expected: str
    actual: str
    context: dict[str, Any]


class GateResult(TypedDict, total=False):
    """Structured result produced by a gate execution.

    ``passed``, ``gate``, ``checks``, ``error``, and
    ``expected_vs_actual`` are always present when the gate runs
    successfully.  ``duration_s`` is injected by ``GateEngine`` after
    execution.  Extra keys such as ``output_path``, ``modified_content``,
    or ``retry_count`` are gate-specific.
    """

    passed: bool
    gate: str
    checks: list[CheckResult]
    error: str | None
    expected_vs_actual: ExpectedVsActual
    duration_s: float
    output_path: str
    retry_count: int
    modified_content: str
    method: str
    confidence: float


def _derive_expected(
    check_name: str,
    *,
    expected_map: dict[str, str] | None = None,
    suffix: str = "",
) -> str:
    """Convert a snake-case *check_name* to a human-readable expected statement.

    If *expected_map* is provided and contains *check_name*, the mapped value
    is returned.  Otherwise the check name is title-cased with underscores
    replaced by spaces, and *suffix* is appended.
    """
    if expected_map is not None and check_name in expected_map:
        return expected_map[check_name]
    return check_name.replace("_", " ").capitalize() + suffix


def _derive_suggestion(check_name: str, threshold: str) -> str:
    """Derive a remediation suggestion from the check name and expected threshold."""
    check_label = check_name.replace("_", " ")
    threshold_lower = threshold.lower()

    if threshold_lower.startswith(("no ", "not ")):
        return f"Remove or avoid {check_label} to satisfy: {threshold}"
    if "must" in threshold_lower or "should" in threshold_lower:
        return f"Ensure {check_label} to satisfy: {threshold}"
    if (
        "between" in threshold_lower
        or "within" in threshold_lower
        or threshold_lower.startswith("all ")
    ):
        return f"Verify {check_label} meets: {threshold}"

    return f"Address {check_label} to match expected: {threshold}"


def _enrich_failing_checks(
    checks: list[CheckResult],
    *,
    expected_map: dict[str, str] | None = None,
    expected_suffix: str = "",
) -> None:
    """Add structured error fields to all failing check dicts in-place.

    Each failing check (``passed=False``) receives ``check_name``,
    ``actual_value``, ``threshold``, ``detail``, and ``suggestion`` keys
    for a standardized error schema.
    """
    for check in checks:
        if not check["passed"]:
            check_name = check["name"]
            threshold = _derive_expected(
                check_name, expected_map=expected_map, suffix=expected_suffix
            )
            check["check_name"] = check_name
            check["actual_value"] = check.get("detail", "")
            check["threshold"] = threshold
            check["suggestion"] = _derive_suggestion(check_name, threshold)


def build_gate_result(
    checks: list[CheckResult],
    *,
    gate: str,
    error: str | None = None,
    expected_map: dict[str, str] | None = None,
    expected_suffix: str = "",
    **extra: Any,  # noqa: ANN401 — pass-through to result dict; gate-specific keys vary
) -> dict[str, Any]:
    """Assemble the final gate result dict from individual *checks*.

    Parameters
    ----------
    checks:
        List of individual check dicts (each must have ``name``, ``passed``,
        and ``detail`` keys).
    gate:
        Gate identifier string (e.g. ``"G0"``, ``"V1"``, ``"pre-gate"``).
    error:
        Optional error message.
    expected_map:
        Optional mapping of check names to human-readable expected statements.
        When provided, lookups are tried here before falling back to the
        default title-case derivation.
    expected_suffix:
        Optional suffix appended to the derived expected statement (e.g.
        ``"."``).  Only affects the fallback derivation, not explicit map
        entries.
    **extra:
        Additional key-value pairs merged into the result dict (e.g.
        ``modified_content``, ``confidence``).
    """
    all_passed = all(c["passed"] for c in checks)

    # Build expected_vs_actual from first failing check, or first check if all pass
    target = next(
        (c for c in checks if not c["passed"]),
        checks[0] if checks else None,
    )
    expected_vs_actual: ExpectedVsActual | dict[str, Any] = {}
    if target:
        expected_vs_actual = {
            "check": target["name"],
            "expected": _derive_expected(
                target["name"],
                expected_map=expected_map,
                suffix=expected_suffix,
            ),
            "actual": target.get("detail", ""),
            "context": {},
        }

    # Enrich failing checks with structured error fields
    _enrich_failing_checks(checks, expected_map=expected_map, expected_suffix=expected_suffix)

    result: dict[str, Any] = {
        "passed": all_passed,
        "gate": gate,
        "checks": checks,
        "error": error,
        "expected_vs_actual": expected_vs_actual,
    }
    result.update(extra)
    return result


def _was_produced(gate_context: GateContext | Mapping[str, Any], key: str) -> bool:
    """该键是否由本流水线的生产者真实产出过。

    中文说明：``GateContext`` 实现了 ``was_written()``（只认显式下标赋值），
    普通 dict 则用成员测试。二者的共同语义是"**这个键被写出来了**"，与"值是
    否为真"无关——生产者写出 ``0`` / ``""`` / ``[]`` 同样算产出。

    Args:
        gate_context: 门的上下文（``GateContext`` 或普通 dict）。
        key: 待判定的上下文键。

    Returns:
        ``True`` 表示上游确实产出了该键。
    """
    probe = getattr(gate_context, "was_written", None)
    if callable(probe):
        return bool(probe(key))
    return key in gate_context


def missing_input_result(
    gate: str,
    gate_context: GateContext | Mapping[str, Any],
    required_keys: Sequence[str],
) -> dict[str, Any] | None:
    """Return a ``skipped`` result when the gate's inputs were never produced.

    中文说明：V0–V7 这些视频质量门读的是**上游产出的上下文键**。在此之前，
    当这些键根本不存在时，门会拿着空值跑真实判定并得出「失败」，或在无
    HyperFrames 时把 ``skipped`` 记成 ``passed``（健康度报告 P0-1）。本函数
    给出第三种、也是唯一诚实的结论：**没有输入 ⇒ 明确记为跳过**。

    判据是「**键是否被生产者显式写出过**」，而不是「值是否为真」——这一点是
    刻意的：生产者只要写出该键（哪怕写的是 ``0`` / ``""`` / ``[]``），就说明
    这门确实拿到了本流水线的产物，此时应当照常执行真实判定并允许它失败。
    反过来，若把空值也算作「缺失」，一个合法的全黑帧（``avg_brightness=0``）
    就会被误判为跳过。因此判据是"是否产出过"，不是真值性。

    「产出过」必须走 :meth:`automedia.gates._context.GateContext.was_written`
    而不能用 ``key in gate_context``：``GateContext.__contains__`` 对**任何
    已声明 dataclass 字段**恒返回 ``True``（字段都有声明默认值），用 ``in``
    会让本函数在生产路径上**永远返回 ``None``**、永不跳过——这是本轮修复前
    的真实缺陷（条件化曾是死代码）。普通 dict 上下文（测试里大量使用）仍按
    成员测试判定，语义不变。

    只有当**全部** ``required_keys`` 都缺失时才跳过：任何一项存在都说明
    上游确实跑到了，残缺的输入该由真实判定去失败，而不是被静默跳过。

    Parameters
    ----------
    gate:
        门标识（如 ``"V1"``），写入返回结果的 ``gate`` 字段。
    gate_context:
        门的上下文（``GateContext`` 或普通 dict）。
    required_keys:
        该门「由本流水线产出」的输入键列表，见各门 docstring 的映射表。

    Returns
    -------
    dict[str, Any] | None
        全部键缺失时返回 ``{"passed": True, "gate": ..., "status": "skipped",
        "reason": ...}``；否则返回 ``None``，调用方继续正常判定。
    """
    if any(_was_produced(gate_context, key) for key in required_keys):
        return None

    return {
        "passed": True,
        "gate": gate,
        "status": "skipped",
        "reason": (
            f"{'/'.join(required_keys)} not produced by this pipeline — "
            f"{gate} has no video artifact to inspect"
        ),
    }
