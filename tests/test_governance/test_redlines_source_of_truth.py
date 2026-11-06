"""Red lines must come from one place. See governance-remediation-plan.md §B1."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from automedia.mcp.tools.redlines import get_redlines

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "src" / "automedia" / "governance" / "redlines.yaml"


def test_get_redlines_matches_yaml_exactly() -> None:
    """Tool output must be the YAML, verbatim — no independent copy."""
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    expected = {r["id"]: r["text"] for r in doc["redlines"]}
    actual = {r["id"]: r["text"] for r in get_redlines()["redlines"]}
    assert actual == expected


def test_redline_ids_are_unique() -> None:
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    ids = [r["id"] for r in doc["redlines"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("entry", ["AGENTS.md", ".claude/rules.md"])
def test_every_entry_references_only_known_ids(entry: str) -> None:
    """Entry files may not invent IDs that the YAML does not define."""
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    known = {r["id"] for r in doc["redlines"]}
    text = (REPO_ROOT / entry).read_text(encoding="utf-8")
    cited = set(re.findall(r"RL-[A-Z-]+", text))
    assert cited <= known, f"{entry} cites unknown ids: {cited - known}"
