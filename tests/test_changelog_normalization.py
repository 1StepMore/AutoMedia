"""Regression invariants for ``CHANGELOG.md`` normalization.

These tests lock the normalization performed when the project's canonical
repository moved from the ``renanzai40/AutoMedia_BackUp`` mirror to
``1StepMore/AutoMedia``, and the release sections were cleaned of merge-commit
duplicate bullets.

Invariants (released ``## [x.y.z]`` sections only — the ``[Unreleased]`` draft
blocks are intentionally skipped and, in fact, removed by the change this test
guards):

1. No ``renanzai40/AutoMedia_BackUp`` URL survives in a released section.
2. No two bullets in the same released section share a normalized key.
   Normalization replaces ``[text](url)`` with ``text``, strips the
   parenthesised short SHA ``([0-9a-f]{7,40})`` and the issue reference
   ``(#N)``, then collapses whitespace.
3. Every ``commit/<40-hex>`` reference resolves to a commit in git history.
   Skipped cleanly when git is unavailable or the tree is not a git repo.
4. Duplicate groups never mix a merge-commit bullet with a normal one.  The
   defect this guards against is release-please listing both the merge wrapper
   of a unit of work and the squashed/real commit behind it under the same
   normalized key; the retained entry must be the real fix, never the merge
   wrapper.  (After normalization there are no duplicate groups left, so this
   assertion passes vacuously — it re-arms if a future release reintroduces
   the pair.)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

BACKUP_REPO = "renanzai40/AutoMedia_BackUp"

SECTION_RE = re.compile(r"^## \[(?P<version>[^\]]+)\]", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*[*-]\s+(?P<text>.+)$", re.MULTILINE)
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
SHA_PAREN_RE = re.compile(r"\([0-9a-f]{7,40}\)")
ISSUE_PAREN_RE = re.compile(r"\(#\d+\)")
COMMIT_SHA_RE = re.compile(r"commit/([0-9a-f]{40})")


def _read() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def released_sections(text: str) -> dict[str, str]:
    """Map each released version to its section body (Unreleased skipped)."""
    matches = list(SECTION_RE.finditer(text))
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        version = match.group("version")
        if version.strip().lower() == "unreleased":
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[version] = text[match.end() : end]
    return out


def iter_bullets(section_body: str) -> list[str]:
    return [m.group("text") for m in BULLET_RE.finditer(section_body)]


def normalize_bullet(bullet: str) -> str:
    """Canonical identity of a bullet, ignoring its URL/SHA/issue decoration."""
    text = LINK_RE.sub(r"\1", bullet)
    text = SHA_PAREN_RE.sub("", text)
    text = ISSUE_PAREN_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def duplicate_groups(section_body: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for bullet in iter_bullets(section_body):
        groups[normalize_bullet(bullet)].append(bullet)
    return {key: group for key, group in groups.items() if len(group) > 1}


def _sha_of(bullet: str) -> str | None:
    match = re.search(r"commit/([0-9a-f]{7,40})", bullet)
    return match.group(1) if match else None


def _git_available() -> bool:
    if shutil.which("git") is None:
        return False
    probe = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def _commit_exists(sha: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _parent_count(sha: str) -> int | None:
    result = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", sha],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return len(result.stdout.split()) - 1


def test_released_sections_have_no_backup_repo_urls() -> None:
    text = _read()
    offenders = {
        version: body.count(BACKUP_REPO)
        for version, body in released_sections(text).items()
        if BACKUP_REPO in body
    }
    assert not offenders, f"{BACKUP_REPO} still referenced in released sections: {offenders}"


def test_released_sections_have_no_duplicate_bullets() -> None:
    text = _read()
    offenders: dict[str, object] = {}
    for version, body in released_sections(text).items():
        groups = duplicate_groups(body)
        if groups:
            offenders[version] = {key: [b[:100] for b in group] for key, group in groups.items()}
    assert not offenders, (
        f"released sections contain bullets with identical normalized keys:\n{offenders}"
    )


def test_commit_references_resolve() -> None:
    if not _git_available():
        pytest.skip("git is unavailable or this is not a git repository")
    text = _read()
    shas = sorted(set(COMMIT_SHA_RE.findall(text)))
    unresolved = [sha for sha in shas if not _commit_exists(sha)]
    assert not unresolved, f"commit references that do not resolve: {unresolved}"


def test_duplicate_groups_do_not_mix_merge_and_normal_commits() -> None:
    if not _git_available():
        pytest.skip("git is unavailable or this is not a git repository")
    text = _read()
    violations: dict[str, object] = {}
    for version, body in released_sections(text).items():
        for key, group in duplicate_groups(body).items():
            kinds = []
            for bullet in group:
                sha = _sha_of(bullet)
                kinds.append(_parent_count(sha) if sha else None)
            has_normal = any(kind == 1 for kind in kinds)
            has_merge = any(kind is not None and kind >= 2 for kind in kinds)
            if has_normal and has_merge:
                violations.setdefault(version, {})[key] = kinds
    assert not violations, (
        "duplicate groups mix merge-wrapper commits with the real fix commit "
        "(the retained entry must be the non-merge commit):\n"
        f"{violations}"
    )
