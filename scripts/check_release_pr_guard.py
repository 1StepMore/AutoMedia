#!/usr/bin/env python3
"""Freeze release-please proposals that contain only internal maintenance.

release-please decides *is this commit user-facing?* purely from the
conventional-commit TYPE.  Internal maintenance typed as a visible commit forces
a public release whose only observable difference is the version number
(#110, #115, #119).  ``scripts/check_release_scope.py`` is the preventive lever
that fails such PRs before they land; this script is the backstop for the PRs
that slip through.

A release PR created by release-please carries exactly ONE commit
(``chore(main): release <comp> <ver>``) touching only the plumbing files
(``CHANGELOG.md``, ``src/automedia/_version.py``,
``.github/.release-please-manifest.json``).  The commits a release is actually
"about" are already on main, so inspecting the release PR's own commit list
would freeze *every* release.  This guard therefore judges the candidate
release by the non-plumbing diff between the last release tag and ``main`` --
the set of changes the proposed version would actually publish.

The path taxonomy is REUSED from ``scripts/check_release_scope.py`` (loaded by
path below); it is never copied, so the two gates can never drift apart.

Both decisions are pure and unit-testable: :func:`should_act` is the security
gate (only release-please's own PRs are ever touched) and
:func:`assess_candidate` is the scope decision.  :func:`main` is a thin,
stdlib-only CLI wrapper.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

# Reuse the canonical taxonomy instead of duplicating the path lists.
_spec = importlib.util.spec_from_file_location(
    "check_release_scope", Path(__file__).with_name("check_release_scope.py")
)
scope = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scope)

is_internal_path = scope.is_internal_path

# Files that release-please rewrites on the release PR itself.  They carry no
# information about what is being released, so they are dropped before judging.
PLUMBING_PATHS = frozenset(
    {
        "CHANGELOG.md",
        "src/automedia/_version.py",
        ".github/.release-please-manifest.json",
        "changelog.json",
    }
)

RELEASE_HEAD_PREFIX = "release-please--"
RELEASE_TITLE_PREFIX = "chore(main): release "
# The author is NOT a usable signal here. release-please opens its PR with the
# repo's own credentials, so user.login is the account owner (measured on the
# real #137: "1StepMore"), not github-actions[bot] -- it changes with whichever
# token release-please runs under. An earlier TRUSTED_AUTHORS allowlist therefore
# never matched, which is why #129 recorded that this guard "never fired". Kept
# as documentation of the value that was wrong, not as a live check.
TRUSTED_AUTHORS = frozenset({"github-actions[bot]", "app/github-actions"})

MAX_LISTED_PATHS = 10


class Decision(NamedTuple):
    """Verdict for one release proposal: freeze it (``snooze``) or leave it."""

    snooze: bool
    reason: str


def _normalize(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _format_paths(paths: list[str]) -> str:
    shown = ", ".join(f"`{p}`" for p in paths[:MAX_LISTED_PATHS])
    remaining = len(paths) - MAX_LISTED_PATHS
    if remaining > 0:
        shown += f", … and {remaining} more"
    return shown


def assess_candidate(files: list[str]) -> Decision:
    """Judge the non-plumbing changed paths of a candidate release.

    Fail-safe direction: an empty set, or any path the taxonomy does not
    recognize as internal, means ``snooze=False`` -- the release is left alone.
    """
    candidate = [_normalize(p) for p in files if _normalize(p)]
    candidate = [p for p in candidate if p not in PLUMBING_PATHS]

    if not candidate:
        return Decision(
            False,
            "No non-plumbing changes; cannot judge, leaving it alone.",
        )

    internal = [p for p in candidate if is_internal_path(p)]
    if len(internal) == len(candidate):
        return Decision(
            True,
            f"All {len(internal)} non-plumbing changed path(s) are internal-only: "
            f"{_format_paths(internal)}.",
        )

    user_visible = [p for p in candidate if not is_internal_path(p)]
    return Decision(
        False,
        f"User-visible path(s) changed, so this release is left alone: "
        f"{_format_paths(user_visible)}.",
    )


def should_act(head_ref: str, author: str, title: str, state: str) -> tuple[bool, str]:
    """Security gate: true only for an open release-please proposal.

    Every condition must hold.  On any mismatch the release is left untouched.

    ``author`` is reported but not enforced.  It was once enforced against
    ``TRUSTED_AUTHORS``, which made this guard inert: release-please authenticates
    with the repo's own credentials, so the proposal's ``user.login`` is the
    account owner, never ``github-actions[bot]``.  Enforcing an identity that the
    real actor does not have is what let #119 / #126 / #133 be closed by hand
    while the machinery stood idle.  The stable signals are the branch and title
    prefixes; the caller additionally requires the release plumbing, so a spoof
    has to rewrite the changelog and version file rather than just rename a
    branch.
    """
    if state != "open":
        return False, f"PR state is '{state}', not 'open'; leaving it alone."
    if not head_ref.startswith(RELEASE_HEAD_PREFIX):
        return False, (f"Head ref '{head_ref}' is not a release-please branch; leaving it alone.")
    if not title.startswith(RELEASE_TITLE_PREFIX):
        return False, (f"Title '{title}' is not a release-please title; leaving it alone.")
    return True, f"Open release-please proposal (author '{author}')."


def decide(
    files: list[str],
    head_ref: str,
    author: str,
    title: str,
    state: str,
) -> Decision:
    """Combine the security gate with the scope assessment."""
    act, reason = should_act(head_ref, author, title, state)
    if not act:
        return Decision(False, reason)
    return assess_candidate(files)


def _read_files(files_file: str) -> list[str]:
    raw = sys.stdin.read() if files_file == "-" else Path(files_file).read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decide whether a release-please proposal should be frozen "
            "(snooze) or left alone (keep)."
        )
    )
    parser.add_argument(
        "--files-file",
        required=True,
        help="Newline-separated changed-file list, or '-' for stdin.",
    )
    parser.add_argument("--pr-title", required=True, help="The PR title.")
    parser.add_argument("--pr-author", required=True, help="The PR author login.")
    parser.add_argument("--head-ref", required=True, help="The PR head branch.")
    parser.add_argument("--pr-state", required=True, help="The PR state.")
    parser.add_argument(
        "--github-output",
        default=None,
        help="Append the 'snooze=...' output here (e.g. $GITHUB_OUTPUT).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        files = _read_files(args.files_file)
    except OSError as exc:
        parser.error(f"cannot read --files-file: {exc}")

    decision = decide(files, args.head_ref, args.pr_author, args.pr_title, args.pr_state)

    print(f"verdict: {'snooze' if decision.snooze else 'keep'}")
    print(decision.reason)

    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as handle:
            handle.write(f"snooze={'true' if decision.snooze else 'false'}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
