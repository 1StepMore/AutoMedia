"""T-14/Tr-08: AGENTS stays small, llms.txt resolves, one schema authority.

RED before the alignment: AGENTS.md was 326 lines; no llms.txt existed; and
``docs/agent-tester-validation-guide.md`` was cited as the authority while
being orphaned from the docs index, giving a circular authority chain.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS = REPO_ROOT / "AGENTS.md"
README = REPO_ROOT / "README.md"
LLMS = REPO_ROOT / "llms.txt"
INDEX = REPO_ROOT / "docs" / "index.md"
STANDARDS = REPO_ROOT / "scenarios" / "STANDARDS.md"
LIVE_GUIDE = REPO_ROOT / "docs" / "agent-tester-validation-guide.md"
ARCHIVED_GUIDE = REPO_ROOT / "docs" / "archived" / "agent-tester-validation-guide.md"
_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_agents_is_at_most_200_lines() -> None:
    assert len(AGENTS.read_text(encoding="utf-8").splitlines()) <= 200


def test_llms_txt_links_resolve() -> None:
    targets = _LINK_RE.findall(LLMS.read_text(encoding="utf-8"))
    assert targets
    for target in targets:
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (REPO_ROOT / target).exists(), f"llms.txt link target missing: {target}"


def test_single_schema_authority_is_named_and_reachable() -> None:
    assert STANDARDS.is_file()
    assert ARCHIVED_GUIDE.is_file()
    assert not LIVE_GUIDE.exists()
    assert "scenarios/STANDARDS.md" in INDEX.read_text(encoding="utf-8")


def test_no_live_doc_names_the_demoted_guide() -> None:
    offenders: list[str] = []
    live_docs = [*sorted((REPO_ROOT / "docs").rglob("*.md")), AGENTS, README]
    for path in live_docs:
        if "docs/archived" in path.as_posix():
            continue
        if "agent-tester-validation-guide" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []
