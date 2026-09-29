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
