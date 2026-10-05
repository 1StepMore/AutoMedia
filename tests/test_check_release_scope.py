"""Contract tests for ``scripts/check_release_scope.py``.

release-please decides user-visibility from the conventional-commit TYPE only,
so internal-only maintenance typed as a visible commit (``fix(...)``) forces a
public release whose only observable difference is the version number.  The
script is the preventive gate: it judges a PR's title type against the release
scope of its changed paths.

The decision logic is a pure function, :func:`assess_release_scope`, so these
tests call it directly; a couple of CLI cases pin the exit codes.

Loader note: ``scripts/`` has no ``__init__.py``, so the module is loaded via
``importlib.util.spec_from_file_location``.  All paths are synthetic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_release_scope.py"


@pytest.fixture(scope="session")
def scope() -> ModuleType:
    """Load the real ``scripts/check_release_scope.py`` module (once)."""
    if "check_release_scope" in sys.modules:
        return sys.modules["check_release_scope"]
    if not SCRIPT.is_file():
        pytest.fail(f"script missing: {SCRIPT}")
    spec = importlib.util.spec_from_file_location("check_release_scope", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---------------------------------------------------------------------------
# is_internal_path — classification, incl. the dot-prefixed exact entries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".github/release-please-config.json",
        ".github/workflows/ci.yml",
        "tests/test_x.py",
        "scripts/check_release_scope.py",
        "docs/dev/agent-reference.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "Makefile",
        ".pre-commit-config.yaml",
        ".editorconfig",
        ".gitignore",
    ],
)
def test_internal_paths(scope: ModuleType, path: str) -> None:
    assert scope.is_internal_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/automedia/x.py",
        "docs/index.md",
        "docs/guide.md",
        "README.md",
        "pyproject.toml",
        "uv.lock",
        "Dockerfile",
        "Dockerfile.dev",
        "docker-compose.yml",
        "deploy/k8s.yaml",
        "scenarios/baseline/x.yaml",
        "CHANGELOG.md",
        "NEWFILE.xyz",
    ],
)
def test_user_visible_paths(scope: ModuleType, path: str) -> None:
    assert scope.is_internal_path(path) is False


# ---------------------------------------------------------------------------
# The four-row table
# ---------------------------------------------------------------------------


def test_all_internal_visible_fails(scope: ModuleType) -> None:
    result = scope.assess_release_scope([".github/workflows/ci.yml"], "fix", [])
    assert result.passed is False
    assert "release:user-visible" in result.remediation


def test_all_internal_visible_with_override_passes(scope: ModuleType) -> None:
    result = scope.assess_release_scope(
        [".github/workflows/ci.yml"], "fix", ["release:user-visible"]
    )
    assert result.passed is True


def test_all_internal_hidden_passes(scope: ModuleType) -> None:
    result = scope.assess_release_scope(
        ["tests/test_x.py", ".github/workflows/ci.yml"], "chore", []
    )
    assert result.passed is True


def test_user_visible_hidden_fails(scope: ModuleType) -> None:
    result = scope.assess_release_scope(["src/automedia/x.py"], "chore", [])
    assert result.passed is False
    assert "release:skip" in result.remediation


def test_user_visible_hidden_with_override_passes(scope: ModuleType) -> None:
    result = scope.assess_release_scope(["src/automedia/x.py"], "chore", ["release:skip"])
    assert result.passed is True


def test_user_visible_visible_passes(scope: ModuleType) -> None:
    result = scope.assess_release_scope(["src/automedia/x.py"], "feat", [])
    assert result.passed is True


@pytest.mark.parametrize("title_type", ["feat", "fix", "perf", "docs", "revert"])
def test_all_visible_types_are_visible(scope: ModuleType, title_type: str) -> None:
    assert scope.assess_release_scope(["src/a.py"], title_type, []).passed is True
    assert scope.assess_release_scope([".github/x.yml"], title_type, []).passed is False


@pytest.mark.parametrize("title_type", ["chore", "ci", "test", "refactor", "build", "style"])
def test_all_hidden_types_are_hidden(scope: ModuleType, title_type: str) -> None:
    assert scope.assess_release_scope([".github/x.yml"], title_type, []).passed is True
    assert scope.assess_release_scope(["src/a.py"], title_type, []).passed is False


# ---------------------------------------------------------------------------
# Regressions / edge cases
# ---------------------------------------------------------------------------


def test_historical_false_case(scope: ModuleType) -> None:
    """The #118 PR: an internal release-config fix forced release 1.8.1."""
    title = "fix(release): parse changelog-sections as the array release-please requires (#118)"
    result = scope.assess_release_scope([".github/release-please-config.json"], "fix", [])
    assert result.passed is False
    assert "release:user-visible" in result.remediation
    assert ".github/release-please-config.json" in result.reason
    assert scope.parse_title_type(title) == "fix"


def test_unknown_path_defaults_user_visible(scope: ModuleType) -> None:
    result = scope.assess_release_scope(["NEWFILE.xyz"], "chore", [])
    assert result.passed is False
    assert "release:skip" in result.remediation


def test_empty_paths_pass(scope: ModuleType) -> None:
    result = scope.assess_release_scope([], "fix", [])
    assert result.passed is True
    assert result.reason


def test_non_conventional_title_cannot_be_judged(scope: ModuleType) -> None:
    result = scope.assess_release_scope(["src/automedia/x.py"], None, [])
    assert result.passed is True
    assert "could not be judged" in result.reason


def test_mixed_paths_treated_as_user_visible(scope: ModuleType) -> None:
    paths = ["src/a.py", ".github/x.yml"]
    assert scope.assess_release_scope(paths, "feat", []).passed is True
    assert scope.assess_release_scope(paths, "chore", []).passed is False


def test_offending_path_list_is_capped(scope: ModuleType) -> None:
    paths = [f"src/pkg/file_{i}.py" for i in range(25)]
    result = scope.assess_release_scope(paths, "chore", [])
    assert result.passed is False
    assert "… and 15 more" in result.reason


# ---------------------------------------------------------------------------
# parse_title_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("fix(release): parse changelog-sections (#118)", "fix"),
        ("FIX: shouty", "fix"),
        ("chore(deps)!: bump", "chore"),
        ("feat: add a thing", "feat"),
        ("Update the docs", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_title_type(scope: ModuleType, title: str | None, expected: str | None) -> None:
    assert scope.parse_title_type(title) == expected


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


def test_cli_exit_codes(scope: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO(".github/release-please-config.json\n"))
    assert (
        scope.main(
            [
                "--files",
                "-",
                "--title",
                "fix(release): parse changelog-sections (#118)",
                "--labels",
                "",
            ]
        )
        == 1
    )

    monkeypatch.setattr(sys, "stdin", io.StringIO("src/automedia/x.py\n"))
    assert scope.main(["--files", "-", "--title", "fix: correct a bug", "--labels", ""]) == 0

    with pytest.raises(SystemExit) as excinfo:
        scope.main(["--title", "fix: x"])
    assert excinfo.value.code == 2


# --- Regression: agent-client config is internal (issue: #126 slipped through) ---
#
# PR #127/#128 changed only .claude/ .codex/ and .opencode/ skill files. Those
# directories ship in the repo but never enter the wheel, and they were not in
# INTERNAL_PREFIXES, so a release proposal whose only real diff was agent config
# read as user-visible and was left alone instead of frozen.


@pytest.mark.parametrize(
    "path",
    [
        ".claude/skills/README.md",
        ".claude/rules.md",
        ".claude/settings.json",
        ".codex/skills/deep-modules.md",
        ".opencode/skills/validation-runner.md",
        ".cursor/mcp.json",
    ],
)
def test_agent_config_paths_are_internal(scope: ModuleType, path: str) -> None:
    assert scope.is_internal_path(path) is True


def test_agent_config_only_diff_is_internal(scope: ModuleType) -> None:
    result = scope.assess_release_scope(
        [".claude/skills/README.md", ".opencode/skills/README.md"], "chore", []
    )
    assert result.passed is True


def test_source_paths_stay_user_visible(scope: ModuleType) -> None:
    """The new prefixes must not swallow real package code."""
    for path in ("src/automedia/core/project.py", "docs/index.md", "README.md"):
        assert scope.is_internal_path(path) is False


# --- Regression: the guard's freeze label must satisfy this gate ---
#
# release-pr-guard.yml freezes a release proposal by applying the
# "autorelease: snooze" label, but this gate only recognised "release:skip",
# so an automatic freeze left release-scope red.


def test_guard_freeze_label_passes_scope(scope: ModuleType) -> None:
    result = scope.assess_release_scope(["src/automedia/x.py"], "chore", ["autorelease: snooze"])
    assert result.passed is True
    assert "autorelease: snooze" in result.reason


def test_both_skip_labels_are_accepted(scope: ModuleType) -> None:
    expected = frozenset({"release:skip", "autorelease: snooze"})
    assert expected == scope.SKIP_LABELS
    assert scope.SKIP_LABEL in scope.SKIP_LABELS


def test_unrelated_label_does_not_pass(scope: ModuleType) -> None:
    result = scope.assess_release_scope(["src/automedia/x.py"], "chore", ["bug"])
    assert result.passed is False


# ---------------------------------------------------------------------------
# release-please proposals are exempt from the type-vs-scope rule (issue #134)
# ---------------------------------------------------------------------------
#
# A release-please proposal's title type is fixed by the bot (``chore(main):
# release <version>``) and its diff is by construction every path since the last
# tag. So whenever a release interval contains any ``src/**`` change, the
# "hidden type + user-visible path" row rejected the proposal with no way out:
# the type cannot be retyped and the diff cannot be narrowed. That froze #133
# (and #119/#126 were closed by hand for the same reason).
#
# Exempting proposals is safe because the "internal-only changes must not force
# a public release" protection is not this gate's job for a proposal -- it is
# release-pr-guard's (scripts/check_release_pr_guard.py, issue #122), which
# auto-freezes internal-only proposals. Measured on the real #133 paths:
# internal-only -> freeze=True; with a src/ change -> freeze=False (left alone
# deliberately). Every condition must match, mirroring that guard's
# ``should_act``; a human PR must never be exempt.

RELEASE_BRANCH = "release-please--branches--main--components--automedia"
RELEASE_TITLE = "chore(main): release automedia 1.8.1"
USER_VISIBLE_PATH = "src/automedia/hitl/constants.py"


def test_exemption_requires_plumbing_not_just_identity(scope: ModuleType) -> None:
    """Superseded the author-keyed test; kept as its regression lock.

    This shape -- release branch, release title, but only a src/ path -- used to
    pass because the author matched. It must now be judged normally, which is
    precisely what makes the exemption content-based.
    """
    result = scope.assess_release_scope(
        [USER_VISIBLE_PATH],
        scope.parse_title_type(RELEASE_TITLE),
        [],
        author="github-actions[bot]",
        head_ref=RELEASE_BRANCH,
        title=RELEASE_TITLE,
    )
    assert result.passed is False
    assert "release-please" not in result.reason.lower()
    assert result.remediation


def test_human_pr_with_release_shaped_title_is_not_exempt(scope: ModuleType) -> None:
    """A human must not buy the exemption by copying the title."""
    result = scope.assess_release_scope(
        [USER_VISIBLE_PATH],
        scope.parse_title_type(RELEASE_TITLE),
        [],
        author="1StepMore",
        head_ref=RELEASE_BRANCH,
        title=RELEASE_TITLE,
    )
    assert result.passed is False
    assert "release-please" not in result.reason.lower()


def test_untrusted_bot_author_is_not_exempt(scope: ModuleType) -> None:
    """Kept from the author-keyed era. The author is no longer a lever at all --
    this passes because the path list carries no release plumbing, not because
    the author was rejected."""
    result = scope.assess_release_scope(
        [USER_VISIBLE_PATH],
        scope.parse_title_type(RELEASE_TITLE),
        [],
        author="dependabot[bot]",
        head_ref=RELEASE_BRANCH,
        title=RELEASE_TITLE,
    )
    assert result.passed is False


def test_non_release_head_ref_is_not_exempt(scope: ModuleType) -> None:
    """Author and title match but the branch is not release-please's."""
    result = scope.assess_release_scope(
        [USER_VISIBLE_PATH],
        scope.parse_title_type(RELEASE_TITLE),
        [],
        author="github-actions[bot]",
        head_ref="fix/ci-coverage-swallowed",
        title=RELEASE_TITLE,
    )
    assert result.passed is False


def test_non_release_title_is_not_exempt(scope: ModuleType) -> None:
    """Author and branch match but the title is not a release proposal."""
    result = scope.assess_release_scope(
        [USER_VISIBLE_PATH],
        scope.parse_title_type("chore(main): internal-only tidy-up"),
        [],
        author="github-actions[bot]",
        head_ref=RELEASE_BRANCH,
        title="chore(main): internal-only tidy-up",
    )
    assert result.passed is False


def test_absent_author_keeps_the_strict_pre_exemption_verdict(scope: ModuleType) -> None:
    """Fail-safe default: no author supplied -> no exemption, pre-existing behaviour."""
    result = scope.assess_release_scope(
        [USER_VISIBLE_PATH], scope.parse_title_type(RELEASE_TITLE), []
    )
    assert result.passed is False


def test_exemption_does_not_mask_the_all_internal_visible_type_row(scope: ModuleType) -> None:
    """A proposal is exempt, but the gate's original rows keep working for humans."""
    human = scope.assess_release_scope(
        [".github/workflows/ci.yml"], scope.parse_title_type("fix: a bug"), []
    )
    assert human.passed is False

    # ...and the visible-type + user-visible row is untouched by the exemption.
    ok = scope.assess_release_scope(
        [USER_VISIBLE_PATH], scope.parse_title_type("fix: a real bug"), []
    )
    assert ok.passed is True


def test_is_release_proposal_needs_branch_title_and_plumbing(scope: ModuleType) -> None:
    """Superseded the author-keyed predicate; author is no longer a parameter."""
    assert scope.is_release_proposal(RELEASE_BRANCH, RELEASE_TITLE, PLUMBING)
    assert not scope.is_release_proposal(RELEASE_BRANCH, RELEASE_TITLE, [USER_VISIBLE_PATH])
    assert not scope.is_release_proposal(RELEASE_BRANCH, RELEASE_TITLE, [PLUMBING[0]])
    assert not scope.is_release_proposal("main", RELEASE_TITLE, PLUMBING)
    assert not scope.is_release_proposal(RELEASE_BRANCH, "chore(main): x", PLUMBING)
    assert not scope.is_release_proposal("", "", [])


def test_cli_accepts_author_and_head_ref(
    scope: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    # A real proposal: the path list carries the release plumbing, and the author
    # is the repo owner (release-please uses the repo's credentials).
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(REAL_PROPOSAL_PATHS) + "\n"))
    assert (
        scope.main(
            [
                "--files",
                "-",
                "--title",
                RELEASE_TITLE,
                "--labels",
                "",
                "--pr-author",
                "1StepMore",
                "--head-ref",
                RELEASE_BRANCH,
            ]
        )
        == 0
    )
    # Without the release branch the same paths are judged normally (fail-safe).
    # stdin is a one-shot StringIO, so it must be re-armed before the second call.
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(REAL_PROPOSAL_PATHS) + "\n"))
    assert scope.main(["--files", "-", "--title", RELEASE_TITLE, "--labels", ""]) == 1


# ---------------------------------------------------------------------------
# Content-based proposal detection (issue #134 follow-up: the author is not a
# usable signal)
# ---------------------------------------------------------------------------
#
# #135 keyed the exemption on `author in {github-actions[bot],
# app/github-actions}`, copied from check_release_pr_guard.py. Measured against
# the real #137 proposal that never fires: release-please runs with the repo's
# own credentials, so `github.event.pull_request.user.login` is the account
# owner (`1StepMore`), not a bot. The exemption was therefore inert, and -- worse
# -- the internal-only backstop it claimed to rely on (#122's auto-freeze) was
# inert for the same reason, so nothing was stopping an internal-only proposal
# from releasing.
#
# The author is not a usable discriminator at all: it changes with whichever
# token release-please runs under. The stable, documented signals are the branch
# prefix, the title prefix, and the release plumbing a real proposal rewrites.
# Because a false positive here UNBLOCKS a release, the criterion is deliberately
# stricter than the author check it replaces: a spoof must also edit CHANGELOG.md
# and the version file, which is conspicuous and self-incriminating.

RELEASE_BRANCH = "release-please--branches--main--components--automedia"
RELEASE_TITLE = "chore(main): release automedia 1.8.1"
PLUMBING = ["CHANGELOG.md", "src/automedia/_version.py"]
# What #137 actually carries: 38 paths, of which these are the release plumbing.
REAL_PROPOSAL_PATHS = [
    *PLUMBING,
    ".github/.release-please-manifest.json",
    "src/automedia/hitl/constants.py",
    "docs/doc-inventory.md",
]


def test_real_proposal_passes_with_the_repo_owner_as_author(scope: ModuleType) -> None:
    """The #137 shape. Author is the owner, and the diff carries the plumbing."""
    result = scope.assess_release_scope(
        REAL_PROPOSAL_PATHS,
        scope.parse_title_type(RELEASE_TITLE),
        ["ci", "core"],
        author="1StepMore",
        head_ref=RELEASE_BRANCH,
        title=RELEASE_TITLE,
    )
    assert result.passed is True
    assert "release-please" in result.reason.lower()


def test_release_shaped_branch_and_title_without_plumbing_is_still_judged(
    scope: ModuleType,
) -> None:
    """Anti-spoof: the branch+title prefix alone must not buy the exemption."""
    result = scope.assess_release_scope(
        ["src/automedia/hitl/constants.py"],
        scope.parse_title_type(RELEASE_TITLE),
        [],
        author="1StepMore",
        head_ref=RELEASE_BRANCH,
        title=RELEASE_TITLE,
    )
    assert result.passed is False
    assert "release-please" not in result.reason.lower()


def test_plumbing_without_the_branch_and_title_is_still_judged(scope: ModuleType) -> None:
    """A human PR that happens to touch the changelog gets no exemption."""
    result = scope.assess_release_scope(
        [*PLUMBING, "src/automedia/hitl/constants.py"],
        scope.parse_title_type(RELEASE_TITLE),
        [],
        author="1StepMore",
        head_ref="fix/ci-something",
        title=RELEASE_TITLE,
    )
    assert result.passed is False


def test_is_release_proposal_uses_content_not_author(scope: ModuleType) -> None:
    assert scope.is_release_proposal(RELEASE_BRANCH, RELEASE_TITLE, REAL_PROPOSAL_PATHS)
    # author is deliberately not a parameter any more
    assert not scope.is_release_proposal(RELEASE_BRANCH, RELEASE_TITLE, ["src/a.py"])
    assert not scope.is_release_proposal("main", RELEASE_TITLE, REAL_PROPOSAL_PATHS)
    assert not scope.is_release_proposal(RELEASE_BRANCH, "chore(main): x", REAL_PROPOSAL_PATHS)
    assert not scope.is_release_proposal("", "", [])


def test_author_alone_never_exempts(scope: ModuleType) -> None:
    """Regression lock for the #135 bug: a trusted bot name is not enough."""
    result = scope.assess_release_scope(
        ["src/automedia/hitl/constants.py"],
        scope.parse_title_type(RELEASE_TITLE),
        [],
        author="github-actions[bot]",
        head_ref=RELEASE_BRANCH,
        title=RELEASE_TITLE,
    )
    assert result.passed is False


# ---------------------------------------------------------------------------
# Source-generated artifacts are not user-visible content (issue #120, option B)
# ---------------------------------------------------------------------------
#
# `docs/doc-inventory.md` is produced by scripts/doc_inventory.py and CI gates it
# byte-for-byte (ci.yml "Doc inventory drift check (T-13)"), and ADR-005 requires
# it to land in the same commit as whatever made it stale. So ANY change that adds
# a doc drags this generated index into the diff -- and because it sits under
# `docs/` but not `docs/dev/`, it read as user-visible, forcing a `release:skip`
# label on internal-only work. That label means "skip the release", which is not
# what such a PR is trying to say.
#
# Admission criterion for GENERATED_ARTIFACTS, all three required:
#   1. produced by a checked-in generator,
#   2. byte-diff-gated in CI so it cannot drift from that generator,
#   3. contains no human-authored prose.
# Hand-written docs (docs/user/**, README.md) stay user-visible.


def test_generated_doc_inventory_is_internal(scope: ModuleType) -> None:
    assert scope.is_internal_path("docs/doc-inventory.md") is True


def test_handwritten_docs_stay_user_visible(scope: ModuleType) -> None:
    assert scope.is_internal_path("docs/user/hitl-framework.md") is False
    assert scope.is_internal_path("docs/dev/plans/NIGHTLY.md") is True
    assert scope.is_internal_path("docs/index.md") is False


def test_internal_doc_addition_passes_without_a_skip_label(scope: ModuleType) -> None:
    """The #136 shape: an internal doc plus the index it forces us to regenerate."""
    result = scope.assess_release_scope(
        ["docs/dev/plans/NEW.md", "docs/doc-inventory.md"],
        scope.parse_title_type("chore(docs): add an internal plan"),
        [],
    )
    assert result.passed is True
    assert result.remediation == ""


def test_generated_artifact_set_is_pinned(scope: ModuleType) -> None:
    """Pinned so widening the exemption is always a visible diff, never a drive-by."""
    assert frozenset({"docs/doc-inventory.md"}) == scope.GENERATED_ARTIFACTS


# ---------------------------------------------------------------------------
# Dependabot lockfile refresh is exempt (issues #167-#170)
# ---------------------------------------------------------------------------
#
# Dependabot titles its pip PRs `chore(deps): bump X from A to B` -- a HIDDEN type
# it cannot retype -- and the uv manager's diff is `uv.lock` alone, which this
# gate must keep calling user-visible (pinned by test_user_visible_paths). The
# "hidden type + user-visible path" row therefore hard-failed with no way out,
# and `git log --author=dependabot` shows no pip bump has ever landed.
#
# The exemption is deliberately narrower than is_release_proposal: same-repo head
# (a structural fact, not a credential, so it bounds the fork spoof the #137
# lesson warns about), the `dependabot/` prefix rather than an ecosystem segment
# (both uv and pip are in live use), lockfile-and-nothing-else, and a hidden
# title type checked at the call site.

BASE_REPO = "1StepMore/AutoMedia"
DEPENDABOT_UV = "chore(deps): bump pyjwt from 2.13.0 to 2.15.0"
DEPENDABOT_PYPROJECT = "chore(deps-dev): update openai requirement"


def test_lockfile_only_dependabot_pr_passes(scope: ModuleType) -> None:
    """The #167/#168/#169/#170 shape: uv.lock alone, chore, uv manager."""
    result = scope.assess_release_scope(
        ["uv.lock"],
        scope.parse_title_type(DEPENDABOT_UV),
        ["dependencies"],
        head_ref="dependabot/uv/pyjwt-2.15.0",
        head_repo=BASE_REPO,
        base_repo=BASE_REPO,
    )
    assert result.passed is True
    assert "Dependabot lockfile refresh" in result.reason
    assert result.remediation == ""


@pytest.mark.parametrize(
    "head_ref",
    [
        "dependabot/uv/pyjwt-2.15.0",
        "dependabot/pip/virtualenv-20.27.1",
    ],
)
def test_both_manager_segments_qualify(scope: ModuleType, head_ref: str) -> None:
    """The prefix is the signal, not an ecosystem segment: uv AND pip are live."""
    assert scope.is_lockfile_refresh(head_ref, BASE_REPO, BASE_REPO, ["uv.lock"]) is True


def test_pyproject_toml_bump_is_still_judged(scope: ModuleType) -> None:
    """The #172 lock-in. The manifest is the install contract and ships in the
    sdist, so a manifest bump must be retyped by a human, never exempted."""
    result = scope.assess_release_scope(
        ["pyproject.toml"],
        scope.parse_title_type(DEPENDABOT_PYPROJECT),
        [],
        head_ref="dependabot/pip/openai-2.45.0",
        head_repo=BASE_REPO,
        base_repo=BASE_REPO,
    )
    assert result.passed is False
    assert "release:skip" in result.remediation


def test_pyproject_toml_retyped_visible_passes(scope: ModuleType) -> None:
    """#172 with the human retyping it needs: visible type + user-visible path."""
    result = scope.assess_release_scope(
        ["pyproject.toml"],
        scope.parse_title_type("fix(deps): update the openai extra's upper bound"),
        [],
        head_ref="dependabot/pip/openai-2.45.0",
        head_repo=BASE_REPO,
        base_repo=BASE_REPO,
    )
    assert result.passed is True


def test_dependabot_pr_touching_source_is_judged(scope: ModuleType) -> None:
    """Lockfile INCLUDED is not lockfile ONLY: a src/** diff still fails."""
    result = scope.assess_release_scope(
        ["uv.lock", "src/automedia/core/project.py"],
        scope.parse_title_type(DEPENDABOT_UV),
        [],
        head_ref="dependabot/uv/pyjwt-2.15.0",
        head_repo=BASE_REPO,
        base_repo=BASE_REPO,
    )
    assert result.passed is False
    assert "release:skip" in result.remediation


def test_fork_named_dependabot_is_not_exempt(scope: ModuleType) -> None:
    """Anti-spoof: the branch name is cheap, the repo the ref lives in is not."""
    result = scope.assess_release_scope(
        ["uv.lock"],
        scope.parse_title_type(DEPENDABOT_UV),
        [],
        head_ref="dependabot/uv/pyjwt-2.15.0",
        head_repo="attacker/AutoMedia",
        base_repo=BASE_REPO,
    )
    assert result.passed is False
    assert "release:skip" in result.remediation


def test_human_branch_touching_only_the_lockfile_is_judged(scope: ModuleType) -> None:
    """No branch prefix, no exemption -- even in the base repo."""
    result = scope.assess_release_scope(
        ["uv.lock"],
        scope.parse_title_type(DEPENDABOT_UV),
        [],
        head_ref="fix/my-thing",
        head_repo=BASE_REPO,
        base_repo=BASE_REPO,
    )
    assert result.passed is False


def test_visible_type_still_goes_through_the_table(scope: ModuleType) -> None:
    """A lock-only PR typed fix(deps) passes -- user-visible path, visible type.

    It must reach that verdict through the normal table, NOT through the
    exemption: the exemption's reason text claims "a hidden type is correct",
    which would be false here. So the assertion is on the reason, not the
    verdict.
    """
    result = scope.assess_release_scope(
        ["uv.lock"],
        scope.parse_title_type("fix(deps): bump pyjwt from 2.13.0 to 2.15.0"),
        [],
        head_ref="dependabot/uv/pyjwt-2.15.0",
        head_repo=BASE_REPO,
        base_repo=BASE_REPO,
    )
    assert result.passed is True  # user-visible path + visible type agree
    assert "lockfile refresh" not in result.reason


def test_absent_head_repo_keeps_the_strict_pre_fix_verdict(scope: ModuleType) -> None:
    """Fail-safe default: flags omitted -> no exemption, pre-existing behaviour."""
    result = scope.assess_release_scope(
        ["uv.lock"],
        scope.parse_title_type(DEPENDABOT_UV),
        [],
        head_ref="dependabot/uv/pyjwt-2.15.0",
    )
    assert result.passed is False
    assert not scope.is_lockfile_refresh("dependabot/uv/x", "", BASE_REPO, ["uv.lock"])


def test_lock_only_path_set_is_pinned(scope: ModuleType) -> None:
    """Pinned so adding pyproject.toml here is always a visible, argued diff."""
    assert frozenset({"uv.lock"}) == scope.DEPENDABOT_LOCK_ONLY_PATHS


def test_github_actions_dependabot_pr_is_unaffected(scope: ModuleType) -> None:
    """The #171 control: .github/workflows/ci.yml is internal, so it passed
    before this change and must keep passing -- via the normal table, not the
    lockfile exemption, because it is not on the lock-only allowlist."""
    result = scope.assess_release_scope(
        [".github/workflows/ci.yml"],
        scope.parse_title_type("chore(deps): bump bridgecrewio/checkov-action"),
        ["dependencies"],
        head_ref="dependabot/github_actions/checkov-action-3.23.0",
        head_repo=BASE_REPO,
        base_repo=BASE_REPO,
    )
    assert result.passed is True
    assert "lockfile refresh" not in result.reason


def test_is_lockfile_refresh_requires_all_four_conditions(scope: ModuleType) -> None:
    assert scope.is_lockfile_refresh("dependabot/uv/x", BASE_REPO, BASE_REPO, ["uv.lock"])
    # not the base repo
    assert not scope.is_lockfile_refresh("dependabot/uv/x", "a/b", BASE_REPO, ["uv.lock"])
    # empty head repo (deleted fork, or the flag omitted)
    assert not scope.is_lockfile_refresh("dependabot/uv/x", "", BASE_REPO, ["uv.lock"])
    # not the dependabot prefix
    assert not scope.is_lockfile_refresh("fix/x", BASE_REPO, BASE_REPO, ["uv.lock"])
    # not lockfile-only
    assert not scope.is_lockfile_refresh(
        "dependabot/uv/x", BASE_REPO, BASE_REPO, ["uv.lock", "pyproject.toml"]
    )
    # nothing to exempt
    assert not scope.is_lockfile_refresh("dependabot/uv/x", BASE_REPO, BASE_REPO, [])


def test_lockfile_path_normalization_cannot_smuggle_a_second_path(scope: ModuleType) -> None:
    """`./uv.lock` normalizes, but it cannot smuggle a second, non-allowlisted path."""
    assert scope.is_lockfile_refresh("dependabot/uv/x", BASE_REPO, BASE_REPO, ["./uv.lock"])
    assert not scope.is_lockfile_refresh(
        "dependabot/uv/x", BASE_REPO, BASE_REPO, ["./uv.lock", "./pyproject.toml"]
    )


def test_cli_passes_head_and_base_repo(scope: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    def _call(extra: list[str]) -> int:
        monkeypatch.setattr(sys, "stdin", io.StringIO("uv.lock\n"))
        return scope.main(
            [
                "--files",
                "-",
                "--title",
                DEPENDABOT_UV,
                "--labels",
                "dependencies",
                "--head-ref",
                "dependabot/uv/pyjwt-2.15.0",
                *extra,
            ]
        )

    assert _call(["--head-repo", BASE_REPO, "--base-repo", BASE_REPO]) == 0
    # Omitting them keeps the strict verdict (fail-safe).
    assert _call([]) == 1
