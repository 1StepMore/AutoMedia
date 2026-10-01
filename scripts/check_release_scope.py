#!/usr/bin/env python3
"""Gate a PR's conventional-commit type against its changed paths' release scope.

release-please decides whether a commit is user-facing purely from the
conventional-commit TYPE.  Scope (``fix(ci):``) does not participate, so
internal-only maintenance work typed as a visible commit (``fix``/``feat``/
``perf``/``docs``/``revert``) always forces a public release whose only
observable difference is the version number.  This script is the preventive
lever: it FAILS such a PR unless the type reflects reality, with two explicit
escape hatches (``release:user-visible`` and ``release:skip``) for the rare
genuine exception.

The decision logic lives in the pure :func:`assess_release_scope`, which the
unit tests call directly; :func:`main` is a thin, stdlib-only CLI wrapper.

RELEASE-PROPOSAL EXEMPTION (issue #134)
---------------------------------------
A release-please proposal is exempt from the type-vs-scope table, because that
table's premise does not hold for it: the bot fixes the title type at
``chore(main): release <version>`` and the diff is by construction every path
since the last tag. So any ``src/**`` change in a release interval made the
"hidden type + user-visible path" row reject the proposal with no way out --
the type cannot be retyped and the diff cannot be narrowed. That is what froze
#133; #119 and #126 had been closed by hand for the same reason.

The protection this gate exists to provide is NOT lost, because for a proposal
it belongs to ``scripts/check_release_pr_guard.py`` (issue #122), which
auto-freezes internal-only proposals.  That is only true because #122's guard
recognises proposals too, which it could not do until the author check was
replaced there as well.

IDENTITY IS NOT A SIGNAL (the #137 lesson)
-------------------------------------------
The first version of this exemption required ``author`` to be a release-please
bot, copied from #122's guard.  It never fired.  Measured on the real #137
proposal: release-please opens its PR with the repo's own credentials, so
``github.event.pull_request.user.login`` is the account owner (``1StepMore``),
not ``github-actions[bot]``.  The author changes with whichever token
release-please runs under, so no hard-coded allowlist can be correct.

The same wrong assumption made #122's auto-freeze inert, which is the real
reason behind #129's complaint that "the guard ... never fired".  Both gates now
key on content: the branch prefix, the title prefix, and the release plumbing a
genuine proposal rewrites.  Spoofing then requires editing ``CHANGELOG.md`` and
the version file, which is deliberate and obvious rather than a branch rename.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

VISIBLE_TYPES = frozenset({"feat", "fix", "perf", "docs", "revert"})
HIDDEN_TYPES = frozenset({"chore", "ci", "test", "refactor", "build", "style"})

USER_VISIBLE_LABEL = "release:user-visible"
SKIP_LABEL = "release:skip"

RELEASE_HEAD_PREFIX = "release-please--"
RELEASE_TITLE_PREFIX = "chore(main): release "
# A real release-please proposal always rewrites the changelog and the version
# file. Requiring both is what makes the exemption content-based rather than
# identity-based; see is_release_proposal.
REQUIRED_RELEASE_PLUMBING = ("CHANGELOG.md", "src/automedia/_version.py")
# The freeze in release-pr-guard.yml applies the release-please snooze label, not
# SKIP_LABEL. Accepting both keeps the two gates satisfiable by the same action: a
# guard-driven freeze must not leave this gate red. See issue #122.
SKIP_LABELS = frozenset({SKIP_LABEL, "autorelease: snooze"})

INTERNAL_PREFIXES = (
    ".github/",
    "tests/",
    "scripts/",
    "docs/dev/",
    # Agent-client configuration ships in the repo but never enters the wheel.
    # Without these, a PR that only touches agent config reads as user-visible and
    # forces a public release whose only real change is the version string.
    ".claude/",
    ".codex/",
    ".opencode/",
    ".cursor/",
    ".trae/",
)
INTERNAL_EXACT = frozenset(
    {
        "AGENTS.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "Makefile",
        ".pre-commit-config.yaml",
        ".editorconfig",
        ".gitignore",
    }
)

MAX_LISTED_PATHS = 10

# Source-generated files that are not user-visible content. Admission requires all
# three: produced by a checked-in generator, byte-diff-gated in CI so it cannot
# drift from that generator, and containing no human-authored prose.
#
# `docs/doc-inventory.md` qualifies: scripts/doc_inventory.py generates it, ci.yml
# gates it byte-for-byte ("Doc inventory drift check (T-13)"), and ADR-005 requires
# it to land in the same commit as whatever made it stale. Without this entry, any
# change that adds a doc drags the regenerated index into the diff and reads as
# user-visible, so internal-only work has to carry a `release:skip` label to say
# "I changed nothing a user would notice". Hand-written docs (docs/user/**,
# docs/index.md, README.md) are deliberately NOT listed.
GENERATED_ARTIFACTS = frozenset({"docs/doc-inventory.md"})


class Result(NamedTuple):
    """Verdict for one PR: ``passed`` plus a human ``reason``/``remediation``."""

    passed: bool
    reason: str
    remediation: str


def is_internal_path(path: str) -> bool:
    """True when ``path`` is internal-only (no user-visible release impact).

    Unknown/unmatched paths return False on purpose: a mis-classification must
    demand a release, never silently suppress one.
    """
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in INTERNAL_EXACT or normalized in GENERATED_ARTIFACTS:
        return True
    return normalized.startswith(INTERNAL_PREFIXES)


def parse_title_type(title: str | None) -> str | None:
    """Return the lowercased conventional-commit type of ``title``, or None.

    ``fix(release): ...`` -> ``fix``; a non-conventional title such as
    ``Update the docs`` -> None (the separate ``check-pr-title`` job owns
    title format, so an unparsable type is not judged here).
    """
    if not title or ":" not in title:
        return None
    head = title.split(":", 1)[0].strip()
    head = head.split("(", 1)[0].rstrip("!").strip().lower()
    return head or None


def _format_paths(paths: list[str]) -> str:
    shown = ", ".join(f"`{p}`" for p in paths[:MAX_LISTED_PATHS])
    remaining = len(paths) - MAX_LISTED_PATHS
    if remaining > 0:
        shown += f", … and {remaining} more"
    return shown


def is_release_proposal(head_ref: str, title: str, paths: list[str]) -> bool:
    """True only for a real release-please proposal: bot branch, bot title, real plumbing.

    The author is deliberately NOT a signal.  release-please creates its PR with
    the repo's own credentials, so ``user.login`` is the account owner
    (``1StepMore`` here), not ``github-actions[bot]``; it changes with whichever
    token release-please runs under.  An earlier version keyed on the author and
    therefore never fired -- see the module docstring.

    The three stable signals are the branch prefix, the title prefix, and the
    release plumbing.  Requiring the plumbing matters more here than in
    check_release_pr_guard.py: a false positive in THIS gate unblocks a release,
    so a spoof must also rewrite ``CHANGELOG.md`` and the version file, which is
    conspicuous and self-incriminating rather than a one-line branch rename.
    """
    if not head_ref.startswith(RELEASE_HEAD_PREFIX):
        return False
    if not title.startswith(RELEASE_TITLE_PREFIX):
        return False
    changed = set(paths)
    return all(p in changed for p in REQUIRED_RELEASE_PLUMBING)


def assess_release_scope(
    paths: list[str],
    title_type: str | None,
    labels: list[str],
    *,
    author: str = "",
    head_ref: str = "",
    title: str = "",
) -> Result:
    """Judge one PR against the four-row release-scope table.

    A release-please proposal short-circuits to a pass (issue #134): its type is
    fixed by the bot and its diff spans the whole release interval, so the table
    has no verdict to give.  See :func:`is_release_proposal` and the module
    docstring for why that does not weaken the internal-only protection.

    ``author`` is accepted but NOT used for the decision -- see
    :func:`is_release_proposal`.  It stays in the signature so existing callers
    and the workflow keep working.
    """
    label_set = {label.strip() for label in labels if label and label.strip()}

    if not paths:
        return Result(True, "No changed files to judge.", "")

    if is_release_proposal(head_ref, title, paths):
        return Result(
            True,
            f"release-please proposal (branch '{head_ref}'): its type is bot-fixed "
            "and its diff spans the whole release interval, so the type-vs-scope "
            "table does not apply. Internal-only proposals are auto-frozen by "
            "check_release_pr_guard.py (issue #122).",
            "",
        )

    known = VISIBLE_TYPES | HIDDEN_TYPES
    if title_type is None or title_type not in known:
        return Result(
            True,
            "PR title is not a recognized conventional-commit type, so the "
            "release scope could not be judged (check-pr-title owns title "
            "format).",
            "",
        )

    all_internal = all(is_internal_path(p) for p in paths)

    if all_internal and title_type in VISIBLE_TYPES:
        if USER_VISIBLE_LABEL in label_set:
            return Result(
                True,
                f"All changed paths are internal-only, but the "
                f"'{USER_VISIBLE_LABEL}' label confirms this is meant to be "
                f"user-visible.",
                "",
            )
        return Result(
            False,
            f"All {len(paths)} changed path(s) are internal-only, yet the "
            f"'{title_type}' type is user-visible by convention, so "
            f"release-please would cut a public release with no user-facing "
            f"content: {_format_paths(paths)}.",
            f"Retype the PR with a hidden type (chore/ci/test/refactor/build/"
            f"style), or add the '{USER_VISIBLE_LABEL}' label if this change "
            f"really is user-visible.",
        )

    if not all_internal and title_type in HIDDEN_TYPES:
        applied = sorted(label_set & SKIP_LABELS)
        if applied:
            return Result(
                True,
                f"User-visible paths changed under a hidden '{title_type}' "
                f"type, but the '{applied[0]}' label confirms the release "
                f"should be skipped.",
                "",
            )
        offenders = [p for p in paths if not is_internal_path(p)]
        return Result(
            False,
            f"The '{title_type}' type is hidden and would be omitted from the "
            f"changelog, but the PR changes user-visible path(s): "
            f"{_format_paths(offenders)}.",
            f"Retype the PR with a visible type (feat/fix/perf/docs/revert), "
            f"or add the '{SKIP_LABEL}' label to confirm the release should be "
            f"skipped.",
        )

    return Result(
        True,
        f"Changed paths and the '{title_type}' type agree on release scope.",
        "",
    )


def _read_paths(args: argparse.Namespace) -> list[str]:
    if args.files is not None:
        if args.files == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(args.files).read_text(encoding="utf-8")
    else:
        raw = Path(args.files_file).read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _parse_labels(raw: str) -> list[str]:
    return [label.strip() for label in raw.split(",") if label.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail when a PR's conventional-commit type does not match the "
            "release scope of its changed paths."
        )
    )
    parser.add_argument(
        "--files",
        help="Path to a newline-separated changed-file list, or '-' for stdin.",
    )
    parser.add_argument(
        "--files-file",
        help="Path to a newline-separated changed-file list.",
    )
    parser.add_argument("--title", default="", help="The PR title.")
    parser.add_argument(
        "--labels",
        default="",
        help="Comma-separated PR label names (may be empty).",
    )
    parser.add_argument(
        "--pr-author",
        default="",
        help=(
            "PR author login. Omitted means no release-proposal exemption "
            "applies, preserving the strict verdict (issue #134)."
        ),
    )
    parser.add_argument(
        "--head-ref",
        default="",
        help=(
            "PR head branch. Together with --pr-author and the title prefix "
            "this identifies a release-please proposal (issue #134)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.files is None and args.files_file is None:
        parser.error("one of --files or --files-file is required")
    if args.files is not None and args.files_file is not None:
        parser.error("--files and --files-file are mutually exclusive")

    paths = _read_paths(args)
    title_type = parse_title_type(args.title)
    result = assess_release_scope(
        paths,
        title_type,
        _parse_labels(args.labels),
        author=args.pr_author,
        head_ref=args.head_ref,
        title=args.title,
    )

    stream = sys.stdout if result.passed else sys.stderr
    print(result.reason, file=stream)
    if not result.passed and result.remediation:
        print(f"Fix: {result.remediation}", file=stream)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
