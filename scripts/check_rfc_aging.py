"""RFC aging checks: a ``Proposed`` RFC must stay current (issue #286).

Two independent failure modes, both silent until a human notices:

1. **Age.** An RFC that has sat in ``Proposed`` for months is a decision the
   project never made.  Past ``PROPOSED_MAX_AGE_DAYS`` the check says: adopt
   it, supersede it, or convert its findings into issues.
2. **Metric drift.** A ``Proposed`` RFC justifies itself with numbers taken
   from the tree (``runner.py`` line count, function count, function-level
   lazy imports).  When the code moves and the RFC does not, the document
   argues from evidence that no longer exists.  ``RFC-001`` was 43% wrong on
   the line count before this check existed.

The check EXITS NON-ZERO on any finding (issue #286 shipped a script that
printed nothing and always exited 0 — a gate that could never fail).  It is
wired into pre-commit as ``check-rfc-aging``.

WHAT IS DELIBERATELY NOT CHECKED: the recorded *caller* count.  "47 callers"
has no single derivation — imports, call sites, lazy re-exports and test
references all give different numbers — so gating it would mean inventing a
definition and then enforcing it.  The metrics below each have exactly one
answer, derived the same way every run.

SIZE_OK: single-concept gate; splitting the extractors from the judgement
would scatter one contract across files for no gain.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RFC_GLOB = "deep-module-rfc-*.md"
PROPOSED_MAX_AGE_DAYS = 90
_RUNNER_TO_ADJUST = "src/automedia/pipelines/runner.py"

# A metric may drift within this band before it is reported.  Prose rounds
# ("~1,600 lines" when the file has 1,617) must not go red; a real refactor
# that moves a number by 20%+ does.  Absolute floors keep small numbers from
# being gated on a single unit.
_RELATIVE_TOLERANCE = 0.2
_MIN_ABSOLUTE_TOLERANCE = 5

# Each recorded metric -> the phrase that introduces it in the RFC prose.
# Ordered: the line count is also the fallback when no phrase matches.
_METRIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "lines",
        re.compile(r"(\d[\d,]*)\s*lines[^\n]{0,40}runner\.py"),
    ),
    (
        "lines",
        re.compile(r"runner\.py[^\n]{0,40}?(\d[\d,]*)\s*lines"),
    ),
    (
        "functions",
        re.compile(r"(\d[\d,]*)\s*functions[^\n]{0,40}runner\.py"),
    ),
    (
        "functions",
        re.compile(r"runner\.py[^\n]{0,40}?(\d[\d,]*)\s*functions"),
    ),
    (
        "lazy_imports",
        # Accepts "13 function-level lazy imports", "44 function-level (lazy)
        # import sites" and "44 function-level lazy-import sites": the RFC is
        # prose, and pinning one exact phrasing would let a reworded sentence
        # silently opt out of the gate.
        re.compile(
            r"(\d[\d,]*)\s*function-level\s*(?:\(\s*lazy\s*\)\s*)?"
            r"(?:lazy[-\s]+)?import(?:s|\s+sites)"
        ),
    ),
)


def _parse_status(text: str) -> str | None:
    match = re.search(r"^\*\*Status:\*\*\s*(\S+)", text, re.MULTILINE)
    return match.group(1) if match else None


def _parse_date(text: str) -> datetime | None:
    match = re.search(r"^\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_recorded_metric(text: str, metric: str) -> int | None:
    for name, pattern in _METRIC_PATTERNS:
        if name != metric:
            continue
        match = pattern.search(text)
        if match is None:
            continue
        digits = match.group(1).replace(",", "")
        if digits.isdigit():
            return int(digits)
    return None


def _runner_metrics(root: Path | None = None) -> dict[str, int]:
    """Derive every metric the RFC may record, from the real ``runner.py``.

    Parsed with ``ast`` rather than grepped: ``lines`` is the physical line
    count, ``functions`` counts only TOP-LEVEL definitions (nested helpers are
    implementation detail, not public surface), and ``lazy_imports`` counts
    import statements INSIDE a function body — the import-cycle web the RFC
    is about.  One derivation each, so the number has exactly one meaning.
    """
    path = (REPO_ROOT if root is None else root) / _RUNNER_TO_ADJUST
    source = path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source)
    functions = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)
    lazy_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if inner is node:
                continue
            if isinstance(inner, (ast.Import, ast.ImportFrom)):
                lazy_lines.add(inner.lineno)
    return {
        "lines": len(source.splitlines()),
        "functions": functions,
        "lazy_imports": len(lazy_lines),
    }


def _is_stale(recorded: int, actual: int) -> bool:
    tolerance = max(_RELATIVE_TOLERANCE * actual, _MIN_ABSOLUTE_TOLERANCE)
    return abs(recorded - actual) > tolerance


def propose_aging_findings(
    proposed_max_age_days: int = PROPOSED_MAX_AGE_DAYS,
    root: Path | None = None,
) -> list[str]:
    """Every reason a ``Proposed`` RFC is no longer current, as human sentences."""
    findings: list[str] = []
    now = datetime.now(UTC)
    base = REPO_ROOT if root is None else root
    actual = _runner_metrics(base)
    for rfc in sorted(base.glob(f"docs/dev/{RFC_GLOB}")):
        text = rfc.read_text(encoding="utf-8", errors="ignore")
        status = _parse_status(text)
        if status is None:
            findings.append(f"{rfc.name}: missing **Status:** header")
            continue
        if status != "Proposed":
            continue
        for metric, actual_value in actual.items():
            recorded = _parse_recorded_metric(text, metric)
            if recorded is None:
                continue
            if _is_stale(recorded, actual_value):
                findings.append(
                    f"{rfc.name}: recorded runner.py {metric} {recorded} vs actual "
                    f"{actual_value} — update the RFC's metrics or move it out of Proposed"
                )
        date = _parse_date(text)
        if date is None:
            findings.append(f"{rfc.name}: missing or unparseable **Date:** header")
            continue
        age_days = (now - date).days
        if age_days > proposed_max_age_days:
            findings.append(
                f"{rfc.name}: Proposed for {age_days} days (>{proposed_max_age_days}) — "
                "adopt it, supersede it, or convert the findings into issues"
            )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Print every finding and return 1 when any exists, 0 when clean."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=PROPOSED_MAX_AGE_DAYS,
        help=f"Age at which a Proposed RFC is overdue (default {PROPOSED_MAX_AGE_DAYS}).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    findings = propose_aging_findings(proposed_max_age_days=args.max_age_days)
    for finding in findings:
        print(f"RFC-AGING: {finding}")
    if findings:
        print(
            f"\nFAIL: {len(findings)} RFC aging finding(s) — a Proposed RFC must stay "
            "current, and a gate that never fails is not a gate"
        )
        return 1
    print("OK: no RFC aging findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
