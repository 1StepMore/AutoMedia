"""RFC aging checks: Proposed RFCs must stay current (issue #286)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RFC_GLOB = "deep-module-rfc-*.md"
PROPOSED_MAX_AGE_DAYS = 90
_RUNNER_TO_ADJUST = "src/automedia/pipelines/runner.py"


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


def _parse_recorded_runner_lines(text: str) -> int | None:
    match = re.search(r"(\d[\d,]*)\s*lines.*runner\.py", text)
    if match is None:
        match = re.search(r"runner\.py.*?(\d[\d,]*)\s*lines", text, re.DOTALL)
    if match is None:
        return None
    return int(match.group(1).replace(",", ""))


def _actual_runner_lines() -> int:
    path = REPO_ROOT / _RUNNER_TO_ADJUST
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def propose_aging_findings(proposed_max_age_days: int = PROPOSED_MAX_AGE_DAYS) -> list[str]:
    findings: list[str] = []
    now = datetime.now(UTC)
    actual_lines = _actual_runner_lines()
    for rfc in sorted(REPO_ROOT.glob(f"docs/dev/{RFC_GLOB}")):
        text = rfc.read_text(encoding="utf-8", errors="ignore")
        status = _parse_status(text)
        if status is None:
            findings.append(f"{rfc.name}: missing **Status:** header")
            continue
        if status != "Proposed":
            continue
        recorded = _parse_recorded_runner_lines(text)
        if recorded is not None and abs(recorded - actual_lines) > max(0.2 * actual_lines, 50):
            findings.append(
                f"{rfc.name}: recorded runner.py {recorded} lines vs actual {actual_lines} — "
                "update the RFC's metrics or move it out of Proposed"
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
