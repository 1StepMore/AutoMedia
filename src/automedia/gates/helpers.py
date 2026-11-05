"""Shared helper utilities for gate implementations.

Provides reusable boilerplate to reduce duplication across gate
``execute()`` methods — particularly the mock-override pattern
used by most gates for deterministic test results.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from structlog import get_logger

from automedia.gates._result import CheckResult

log = get_logger(__name__)

#: Characters that make up Chinese/Japanese prose (CJK Unified + Ext-A).
_CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

#: Share of CJK characters at which a document is treated as Chinese copy.
#: A Chinese headline inside an English article must not flip the whole
#: document onto the CJK judgement rules.
_CJK_RATIO_THRESHOLD = 0.30


def is_cjk_dominant(text: str, threshold: float = _CJK_RATIO_THRESHOLD) -> bool:
    """Return ``True`` when *text* reads as Chinese (CJK-majority) copy.

    Every judgement vocabulary in this repo started out English-only, which
    made Chinese content fail forever (#375, #388).  Gates use this to pick the
    matching rule set instead of piling Chinese into an English regex.
    """
    visible = [ch for ch in text if not ch.isspace()]
    if not visible:
        return False
    cjk = sum(1 for ch in visible if _CJK_CHAR_RE.match(ch))
    return cjk / len(visible) >= threshold


def apply_mock_overrides(
    check_fns: list[tuple[str, Callable[[], CheckResult]]],
    mock_results: dict[str, dict[str, Any]] | None,
) -> list[CheckResult]:
    """Build a list of check result dicts, overriding with mock values
    when the gate is running under test.

    Each callable in *check_fns* is a ``(name, fn)`` pair where ``fn``
    is a zero-argument callable that returns ``{"name": str, "passed": bool,
    "detail": str}``.

    When *mock_results* is provided and contains a key matching the check
    name, the mock value is used verbatim instead of calling *fn* — making
    the gate fully deterministic for unit testing.

    Args:
        check_fns: Sequence of ``(check_name, callable)`` pairs.
        mock_results: Optional dict of ``{check_name: {"passed": bool,
            "detail": str}}`` from ``gate_context["_mock_results"]``.

    Returns:
        List of check result dicts compatible with ``build_gate_result()``.
    """
    checks: list[CheckResult] = []
    for name, fn in check_fns:
        if mock_results is not None and name in mock_results:
            mock = mock_results[name]
            checks.append(
                {
                    "name": name,
                    "passed": bool(mock["passed"]),
                    "detail": str(mock.get("detail", "")),
                }
            )
        else:
            checks.append(fn())
    return checks
