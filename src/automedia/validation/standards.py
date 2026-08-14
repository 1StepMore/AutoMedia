"""Standards registry for agent-tester validation (W1-T3).

Loads the known-standard keys from a Markdown handbook (the runtime
``scenarios/STANDARDS.md``, authored in W2-T1; W1 unit tests use fixture
handbooks under ``tests/fixtures/synth/standards/``).  Scenario steps cite
these keys via their ``standard:`` field; the loader (W1-T2) cross-checks
them with :meth:`StandardsRegistry.validate_standard` and fails the load on
unknown keys.  An absent or malformed handbook is a loud
:class:`StandardsError`, never an obscure crash (plan W1-T3, Momus
improvement 3).

Handbook format (PINNED for W2-T1 — author ``scenarios/STANDARDS.md`` to
this exact shape): a heading ``## Standards`` (alias ``## Standard Keys``)
followed by a Markdown table whose first column is ``Key``.  Any table under
the heading is parsed; keys are trimmed, deduped and non-empty.

    ## Standards

    | Key | Check type | Standard | Source doc | Clause |
    | --- | --- | --- | --- | --- |
    | founder-expectations.F01 | artifact_exists | F01 ever-green clause | … | §8.3 |
    | evaluation-matrix.dim1 | quality_spot_check | 8-dim matrix P0-P5 | … | §1 |
"""

from __future__ import annotations

import os
import re
from pathlib import Path

STANDARDS_HANDBOOK_NAME = "STANDARDS.md"
"""Handbook filename inside the scenarios directory."""

_SCENARIOS_DIR_ENV = "AUTOMEDIA_VALIDATION_SCENARIOS_DIR"
"""Env var overriding the scenarios directory (guide §3.5, plan W1-T2/T3)."""

_HEADING_RE: re.Pattern[str] = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_HEADING_NAMES: frozenset[str] = frozenset({"standards", "standard keys"})
_TABLE_ROW_RE: re.Pattern[str] = re.compile(r"^\s*\|")
_SEPARATOR_CELL_RE: re.Pattern[str] = re.compile(r"^:?-{3,}:?$")


class StandardsError(ValueError):
    """A standards handbook is absent, unreadable, or lacks a parseable
    standards table.  The message always names the handbook path."""


def _resolve_scenarios_dir() -> Path:
    """The scenarios directory: ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` if
    set, else the repo-root ``scenarios/`` (wheel-install-safe default)."""
    env = os.environ.get(_SCENARIOS_DIR_ENV)
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "scenarios"


def _split_table_row(line: str) -> list[str]:
    """Split one Markdown table row into its stripped cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    """True when every non-empty cell is a header separator like ``---``."""
    return bool(cells) and all(
        _SEPARATOR_CELL_RE.fullmatch(cell) is not None for cell in cells if cell != ""
    )


def _parse_handbook(text: str, path: Path) -> set[str]:
    """Extract the ``Key`` column of the first table under the standards
    heading; keys are trimmed, deduped and non-empty.  Raises
    ``StandardsError`` naming ``path`` when no heading or no table exists."""
    lines = text.splitlines()
    table_start: int | None = None
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match and match.group(1).strip().lower() in _HEADING_NAMES:
            table_start = index + 1
            break
    if table_start is None:
        raise StandardsError(
            f"{path}: no '## Standards' heading found; the handbook must contain a "
            "'## Standards' (or '## Standard Keys') section with a Markdown table"
        )
    keys: list[str] = []
    seen: set[str] = set()
    rows = 0
    for line in lines[table_start:]:
        if not _TABLE_ROW_RE.match(line):
            if rows:  # first table has ended
                break
            continue
        cells = _split_table_row(line)
        if not cells or _is_separator_row(cells):
            continue
        rows += 1
        if rows == 1:  # header row: Key | Check type | Standard | Source doc | Clause
            continue
        key = cells[0]
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    if not keys:
        raise StandardsError(
            f"{path}: no standards table found under the '## Standards' heading "
            "(expected a Markdown table with columns 'Key | Check type | Standard | "
            "Source doc | Clause')"
        )
    return set(keys)


class StandardsRegistry:
    """The known-standard keys of the agent-tester validation framework,
    loaded from the handbook's ``Key`` column (guide §2.4 + plan W1-T3)."""

    def __init__(self, handbook_path: Path | str | None = None) -> None:
        if handbook_path is None:
            raise StandardsError(
                "handbook_path is required; use StandardsRegistry.from_default() "
                "to resolve the default scenarios/STANDARDS.md path"
            )
        self._handbook_path = Path(handbook_path)
        if not self._handbook_path.is_file():
            raise StandardsError(
                f"standards handbook not found: {self._handbook_path} (expected a "
                f"{STANDARDS_HANDBOOK_NAME} file in the scenarios directory)"
            )
        try:
            text = self._handbook_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StandardsError(
                f"standards handbook unreadable: {self._handbook_path} ({exc})"
            ) from exc
        self._keys: set[str] = _parse_handbook(text, self._handbook_path)

    @classmethod
    def from_default(cls) -> StandardsRegistry:
        """Build the registry from the default handbook path:
        ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` if set, else repo-root
        ``scenarios/`` (guide §3.5)."""
        return cls(_resolve_scenarios_dir() / STANDARDS_HANDBOOK_NAME)

    def validate_standard(self, key: str) -> bool:
        """True when ``key`` is a known standard key from the handbook."""
        return key in self._keys

    def known_keys(self) -> set[str]:
        """All known standard keys (a fresh copy, safe to mutate)."""
        return set(self._keys)
