#!/usr/bin/env python3
"""Push a local branch to GitHub through the Git Data API (api.github.com).

When ``github.com:443`` (git over HTTPS) and ``ssh:22`` are unreachable while
``api.github.com`` still answers, plain ``git push`` cannot run.  This script
rebuilds the branch commit-by-commit through the REST API so the remote branch
ends up byte-identical to the local one.  Every created object is verified
against the local SHA before the next step; any mismatch aborts the whole run
with a clear report — no partial push.

### 1. SHA determinism — when replication is bit-exact
A commit object is content-addressed over: tree SHA, parent SHAs, author line
(name/email/timestamp/tz offset), committer line, and the message bytes.  The
API calls pin every one of those fields from the local object, and each
created object is verified against the local SHA.  Replication is exact iff:

* the commit is **unsigned** — a GPG signature lives inside the object body
  and cannot be reproduced through the API, so a signed commit would get a
  different SHA; this script aborts on signed commits instead of pushing a
  silently different history;
* author/committer name, email, timestamp **and timezone offset** are
  preserved verbatim (they are copied from the local object, so nothing can
  drift);
* the tree contents are identical — blobs are uploaded base64-encoded and
  verified, trees are built with an explicit ``base_tree`` and verified.

### 2. Ref semantics
The branch ref is created when absent.  When it already exists the script
PATCHes it with ``force=false`` — the remote head must be an ancestor, i.e.
the push must be a fast-forward (this is also what makes re-running the
script after a partial failure safe).  ``--force`` exists for history
rewrites (DCO rebase, amended ops branches) and moves the ref without that
check; the per-commit SHA verification still applies.

### 3. Token requirements
``gh auth token`` must resolve to a token with the classic ``repo`` scope
(the gh OAuth token qualifies); a fine-grained PAT needs **Contents:
read/write** on the target repository.  The token is held in memory only —
it is never printed, logged, or written anywhere.

Usage::

    python push_via_api.py <repo_root> --branch <branch> [--base main]
                           [--owner <o> --repo <r>] [--force]

``--owner``/``--repo`` default to the ``origin`` remote of *repo_root*.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

LOG_FORMAT = "%H|%T|%P|%an|%ae|%aI|%cn|%ce|%cI"
DELETION_MODE = "000000"
SUBMODULE_MODE = "160000"
SIGNED_HEADER = "\ngpgsig "


@dataclass(frozen=True)
class CommitMeta:
    sha: str
    tree: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    author_date: str
    committer_name: str
    committer_email: str
    committer_date: str


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    path: str
    sha: str  # blob sha, or the gitlink commit sha for submodules


def parse_commit_log(text: str) -> list[CommitMeta]:
    """Parse ``git log --format=<LOG_FORMAT>`` output into commit metadata."""
    commits: list[CommitMeta] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        (sha, tree, parents, an, ae, ad, cn, ce, cd) = line.split("|", 8)
        commits.append(
            CommitMeta(
                sha=sha,
                tree=tree,
                parents=tuple(parents.split()),
                author_name=an,
                author_email=ae,
                author_date=ad,
                committer_name=cn,
                committer_email=ce,
                committer_date=cd,
            )
        )
    return commits


def parse_diff_tree(text: str) -> list[TreeEntry]:
    """Parse ``git diff-tree -r -z`` output into (mode, path, sha) entries.

    With ``-z`` the records are NUL-separated as ``meta\\0path\\0`` pairs;
    ``meta`` is ``:<old_mode> <new_mode> <old_sha> <new_sha> <status>``.
    A deletion (status ``D``) is reported with the sentinel mode 000000.
    """
    fields = text.split("\0")
    entries: list[TreeEntry] = []
    for i in range(0, len(fields) - 1, 2):
        meta, path = fields[i], fields[i + 1]
        if not meta.strip():
            continue
        meta = meta.lstrip(":")
        _old_mode, new_mode, _old_sha, new_sha, _status = meta.split()
        if new_mode == DELETION_MODE:
            entries.append(TreeEntry(mode=DELETION_MODE, path=path, sha=""))
        else:
            entries.append(TreeEntry(mode=new_mode, path=path, sha=new_sha))
    return entries


def build_tree_payload(entries: list[TreeEntry]) -> list[dict]:
    """Translate diff-tree entries into a Git Data API tree payload."""
    tree: list[dict] = []
    for entry in entries:
        if entry.mode == DELETION_MODE:
            tree.append({"path": entry.path, "mode": "100644", "sha": None})
        elif entry.mode == SUBMODULE_MODE:
            tree.append(
                {"path": entry.path, "mode": entry.mode, "type": "commit", "sha": entry.sha}
            )
        else:
            tree.append({"path": entry.path, "mode": entry.mode, "type": "blob", "sha": entry.sha})
    return tree


class ApiError(Exception):
    """A failed API step — aborts the whole push (no partial push)."""


class ApiClient:
    """Thin JSON wrapper over api.github.com with an in-memory gh token."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url
        self._token: str | None = None

    @property
    def token(self) -> str:
        if self._token is None:
            proc = subprocess.run(
                ["gh", "auth", "token"],  # noqa: S607 — bare `gh` via PATH is intended
                capture_output=True,
                text=True,
                check=True,
            )
            self._token = proc.stdout.strip()
            if not self._token:
                raise ApiError("gh auth token returned an empty token")
        return self._token

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        req = urllib.request.Request(  # noqa: S310 — scheme fixed https://api.github.com
            f"{self._base}{path}",
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "automedia-push-via-api",
            },
            method=method,
        )
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(  # noqa: S310 — scheme fixed https://api.github.com
                    req, timeout=60
                ) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
                raise ApiError(f"API {method} {path} -> HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, OSError) as exc:
                # Connection-level flake (DNS/getaddrinfo, reset) — this tool
                # runs on partitioned networks, so retry with backoff. HTTP
                # errors are verdicts, not flakes, and are never retried.
                last_exc = exc
                time.sleep(2 * (attempt + 1))
        raise ApiError(f"API {method} {path} unreachable after retries: {last_exc}")


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def git(self, *args: str) -> str:
        proc = subprocess.run(  # noqa: S603 — argv built from literals, no shell
            ["git", *args],  # noqa: S607 — bare `git` via PATH is intended
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout

    def git_bytes(self, *args: str) -> bytes:
        proc = subprocess.run(  # noqa: S603 — argv built from literals, no shell
            ["git", *args],  # noqa: S607 — bare `git` via PATH is intended
            cwd=self.root,
            capture_output=True,
            check=True,
        )
        return proc.stdout


def push_branch(
    repo: Repo, api: ApiClient, owner: str, name: str, branch: str, base: str, force: bool
) -> None:
    api_base = f"/repos/{owner}/{name}"  # relative: ApiClient owns the host

    log_text = repo.git("log", "--reverse", "--format=" + LOG_FORMAT, f"{base}..{branch}")
    commits = parse_commit_log(log_text)
    local_head = repo.git("rev-parse", branch).strip()

    if not commits:
        # Nothing to replicate: the branch points at (or behind) base. Make
        # sure the remote ref exists at the local head — but only when the
        # local head IS the base head; a divergent/behind head is refused.
        remote_base = api.call("GET", f"{api_base}/commits/{base}")["sha"]
        if local_head != remote_base:
            raise ApiError(
                f"branch {branch} has no commits ahead of {base} but its head "
                f"({local_head[:10]}) != {base} ({remote_base[:10]}); refusing "
                "to move the ref"
            )
        _upsert_ref(api, api_base, branch, remote_base, force)
        print(f"no commits ahead of {base}; ref ensured at {remote_base[:10]}")
        return

    for meta in commits:
        raw = repo.git("cat-file", "commit", meta.sha)
        if SIGNED_HEADER in raw or raw.startswith("gpgsig "):
            raise ApiError(
                f"{meta.sha} is a signed commit; signatures live inside the "
                "object and cannot be reproduced through the API — push it "
                "over git when the network allows"
            )
        if len(meta.parents) > 1:
            raise ApiError(
                f"{meta.sha} is a merge commit; this tool replicates linear history only"
            )

    # Blobs already on the remote (reachable from base) need no upload.
    remote_blobs: set[str] = set()
    base_tree_data = api.call("GET", f"{api_base}/git/trees/{base}?recursive=1")
    for entry in base_tree_data.get("tree", []):
        if entry.get("type") == "blob":
            remote_blobs.add(entry["sha"])
    print(
        f"local commits to replicate: {len(commits)}; "
        f"remote blobs known from {base}: {len(remote_blobs)}"
    )

    remote_base = api.call("GET", f"{api_base}/commits/{base}")["sha"]
    first_local_parent = commits[0].parents[0] if commits[0].parents else ""
    if remote_base != first_local_parent:
        raise ApiError(
            f"remote {base} moved: {remote_base[:10]} != local baseline "
            f"{first_local_parent[:10]}; rebase the branch and retry"
        )

    parent_sha = remote_base
    prev_tree_remote = api.call("GET", f"{api_base}/git/commits/{remote_base}")["tree"]["sha"]

    for meta in commits:
        if meta.parents:
            diff = repo.git(
                "diff-tree",
                "-r",
                "-z",
                "--no-commit-id",
                meta.parents[0],
                meta.sha,
            )
        else:
            diff = repo.git(
                "diff-tree",
                "-r",
                "-z",
                "--no-commit-id",
                "--root",
                meta.sha,
            )
        entries = parse_diff_tree(diff)

        for entry in entries:
            if entry.mode in (DELETION_MODE, SUBMODULE_MODE):
                continue
            if entry.sha in remote_blobs:
                continue
            content = repo.git_bytes("cat-file", "blob", entry.sha)
            created = api.call(
                "POST",
                f"{api_base}/git/blobs",
                {
                    "content": base64.b64encode(content).decode("ascii"),
                    "encoding": "base64",
                },
            )
            if created["sha"] != entry.sha:
                raise ApiError(
                    f"blob sha mismatch for {entry.path}: {created['sha']} != {entry.sha}"
                )
            remote_blobs.add(entry.sha)

        tree = api.call(
            "POST",
            f"{api_base}/git/trees",
            {
                "base_tree": prev_tree_remote,
                "tree": build_tree_payload(entries),
            },
        )
        if tree["sha"] != meta.tree:
            raise ApiError(
                f"tree sha mismatch at {meta.sha}: remote {tree['sha']} != local {meta.tree}"
            )

        commit = api.call(
            "POST",
            f"{api_base}/git/commits",
            {
                "message": repo.git("cat-file", "commit", meta.sha).split("\n\n", 1)[1],
                "tree": tree["sha"],
                "parents": [parent_sha],
                "author": {
                    "name": meta.author_name,
                    "email": meta.author_email,
                    "date": meta.author_date,
                },
                "committer": {
                    "name": meta.committer_name,
                    "email": meta.committer_email,
                    "date": meta.committer_date,
                },
            },
        )
        if commit["sha"] != meta.sha:
            raise ApiError(
                f"commit sha mismatch: remote {commit['sha']} != local "
                f"{meta.sha} (author/committer/dates/tree must reproduce the "
                "object byte-for-byte)"
            )
        parent_sha = commit["sha"]
        prev_tree_remote = tree["sha"]
        subject = repo.git("log", "-1", "--format=%s", meta.sha).strip()[:60]
        print(f"OK {meta.sha[:10]} {subject}")

    _upsert_ref(api, api_base, branch, parent_sha, force)
    if parent_sha != local_head:
        raise ApiError(f"head mismatch: remote {parent_sha} != local {local_head}")
    print(f"BRANCH PUSHED via API: {branch} @ {parent_sha[:10]} (== local head)")


def _upsert_ref(api: ApiClient, api_base: str, branch: str, sha: str, force: bool) -> None:
    try:
        api.call("POST", f"{api_base}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})
        return
    except ApiError as exc:
        if "HTTP 422" not in str(exc):
            raise
        # Ref exists: fast-forward unless --force.
        api.call("PATCH", f"{api_base}/git/refs/heads/{branch}", {"sha": sha, "force": force})
        print(f"ref updated (force={force}): {branch} -> {sha[:10]}")


def parse_origin_remote(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from an origin remote URL."""
    for prefix in (
        "git@github.com:",
        "ssh://git@github.com/",
        "https://github.com/",
        "git://github.com/",
    ):
        if url.startswith(prefix):
            tail = url[len(prefix) :]
            if tail.endswith(".git"):
                tail = tail[:-4]
            if "/" in tail:
                owner, _, name = tail.partition("/")
                return owner, name
    raise SystemExit(f"cannot parse owner/repo from origin URL: {url}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Push a branch to GitHub via the Git Data API (network-partition channel)."
    )
    parser.add_argument("repo_root", type=Path, help="local git repository root")
    parser.add_argument("--branch", required=True, help="branch to push")
    parser.add_argument("--base", default="main", help="base ref the branch builds on")
    parser.add_argument("--owner", default=None, help="target owner (default: origin remote)")
    parser.add_argument("--repo", default=None, help="target repo (default: origin remote)")
    parser.add_argument(
        "--force", action="store_true", help="allow moving an existing ref (history rewrites)"
    )
    args = parser.parse_args()

    repo = Repo(args.repo_root.resolve())
    remote_url = repo.git("remote", "get-url", "origin").strip()
    owner, name = parse_origin_remote(remote_url)
    if args.owner:
        owner = args.owner
    if args.repo:
        name = args.repo

    push_branch(
        repo,
        ApiClient("https://api.github.com"),
        owner,
        name,
        args.branch,
        args.base,
        args.force,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
