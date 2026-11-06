"""Consensus hash over the governance source set.

H is computed over git BLOBS, not worktree bytes: .gitattributes applies
eol=lf at clean time, so a Windows checkout (which may carry CRLF in the
worktree) and a Linux checkout yield the same oid. Hashing worktree bytes
would split the consensus in two -- see docs/dev/governance-remediation-plan.md.

Sources are an explicit list, never a glob: Windows is case-insensitive and
Linux is not, so the same glob can match different sets on the two platforms.

BOM is REJECTED, not stripped: a BOM is legal UTF-8 but shifts every
line-1 match, and silently removing it hides the committer's intent.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent / "consensus.lock"

# Explicit source set. Order here is irrelevant -- compute() sorts by path.
SOURCE_FILES: tuple[str, ...] = (
    "src/automedia/governance/redlines.yaml",
    "src/automedia/governance/entries.yaml",
    "AGENTS.md",
    ".claude/rules.md",
    ".github/CODEOWNERS",
    ".github/workflows/ci.yml",
)


class ConsensusError(RuntimeError):
    """Raised when the source set is empty or a source cannot be hashed."""


def _blob_oid(rel: str) -> str:
    """Blob oid of the CURRENT worktree content, after the clean filter."""
    path = REPO_ROOT / rel
    if not path.is_file():
        raise ConsensusError(f"consensus source missing: {rel}")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ConsensusError(f"BOM in consensus source: {rel}")
    result = subprocess.run(  # noqa: S603 — read-only hash-object over a local path
        ["git", "-C", str(REPO_ROOT), "hash-object", "--stdin", f"--path={rel}"],  # noqa: S607 — bare `git` resolved via PATH is intended
        input=raw,
        capture_output=True,
    )
    # check=True would leak CalledProcessError; the caller contract is
    # ConsensusError only.
    if result.returncode != 0:
        raise ConsensusError(
            f"git hash-object failed for {rel}: {result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout.decode().strip()


def compute(source_files: tuple[str, ...] | None = None) -> str:
    """Return the consensus hash. Empty source set is a hard failure."""
    files = SOURCE_FILES if source_files is None else source_files
    if not files:
        raise ConsensusError("consensus source set is empty")
    lines = [f"{rel}\0{_blob_oid(rel)}\n" for rel in sorted(files, key=lambda p: p.encode("utf-8"))]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def check() -> int:
    """CLI entry: compare against consensus.lock, exit 1 on mismatch."""
    if not LOCK.is_file():
        print(f"GOV301 consensus lock missing: {LOCK.name}")
        return 1
    expected = LOCK.read_text(encoding="utf-8").strip()
    actual = compute()
    if actual != expected:
        print(f"GOV301 consensus hash mismatch: lock={expected} computed={actual}")
        return 1
    print(f"OK: consensus {actual[:12]}")
    return 0


def write_lock() -> int:
    """Regenerate consensus.lock. Manual step -- commit the result."""
    actual = compute()
    LOCK.write_text(actual + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {LOCK.name}: {actual}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(write_lock() if "--update" in sys.argv[1:] else check())
