"""Contract tests for ``scripts/check_release_pr_guard.py``.

This is the backstop to ``scripts/check_release_scope.py``: when a release
proposal (whose own PR only carries the plumbing commit) would publish nothing
but internal maintenance, it is frozen with ``autorelease: snooze``.

The decisions are pure functions, :func:`should_act` (security gate) and
:func:`assess_candidate` (scope), so these tests call them directly; a couple
of CLI cases pin the output/exit behaviour.

Loader note: ``scripts/`` has no ``__init__.py``, so both modules are loaded
via ``importlib.util.spec_from_file_location``.  All paths are synthetic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_SCRIPT = REPO_ROOT / "scripts" / "check_release_pr_guard.py"
SCOPE_SCRIPT = REPO_ROOT / "scripts" / "check_release_scope.py"

# The five paths measured on this repo from `automedia-v1.8.0..main`.
REAL_PATHS = [
    ".github/release-please-config.json",
    ".github/workflows/conventional-commits.yml",
    ".github/workflows/publish.yml",
    "scripts/check_release_scope.py",
    "tests/test_check_release_scope.py",
]

ACT_TITLE = "chore(main): release automedia 1.8.1"
ACT_HEAD_REF = "release-please--branches--main--components--automedia"
ACT_AUTHOR = "github-actions[bot]"


def _load(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    if not path.is_file():
        pytest.fail(f"script missing: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def guard() -> ModuleType:
    """Load the real ``scripts/check_release_pr_guard.py`` module (once)."""
    return _load("check_release_pr_guard", GUARD_SCRIPT)


@pytest.fixture(scope="session")
def scope() -> ModuleType:
    """Load the real ``scripts/check_release_scope.py`` module (once)."""
    return _load("check_release_scope", SCOPE_SCRIPT)


# ---------------------------------------------------------------------------
# assess_candidate — the scope decision
# ---------------------------------------------------------------------------


def test_real_data_replay_is_frozen(guard: ModuleType) -> None:
    """The 1.8.0..main window contained only internal maintenance."""
    decision = guard.assess_candidate(REAL_PATHS)
    assert decision.snooze is True
    assert "internal-only" in decision.reason


def test_negative_control_is_left_alone(guard: ModuleType) -> None:
    decision = guard.assess_candidate([*REAL_PATHS, "src/automedia/x.py"])
    assert decision.snooze is False
    assert "src/automedia/x.py" in decision.reason


def test_plumbing_only_is_left_alone(guard: ModuleType) -> None:
    decision = guard.assess_candidate(
        ["CHANGELOG.md", "src/automedia/_version.py", ".github/.release-please-manifest.json"]
    )
    assert decision.snooze is False
    assert "non-plumbing" in decision.reason


def test_unknown_path_is_left_alone(guard: ModuleType) -> None:
    decision = guard.assess_candidate(["NEWFILE.xyz"])
    assert decision.snooze is False


def test_empty_list_is_left_alone(guard: ModuleType) -> None:
    decision = guard.assess_candidate([])
    assert decision.snooze is False
    assert decision.reason


def test_plumbing_is_dropped_before_judging(guard: ModuleType) -> None:
    decision = guard.assess_candidate(
        ["CHANGELOG.md", ".github/workflows/ci.yml", "changelog.json"]
    )
    assert decision.snooze is True


def test_user_visible_listing_is_capped(guard: ModuleType) -> None:
    paths = [f"src/pkg/file_{i}.py" for i in range(25)]
    decision = guard.assess_candidate(paths)
    assert decision.snooze is False
    assert "… and 15 more" in decision.reason


# ---------------------------------------------------------------------------
# should_act — the security gate
# ---------------------------------------------------------------------------


def test_gate_accepts_a_real_release_pr(guard: ModuleType) -> None:
    act, reason = guard.should_act(ACT_HEAD_REF, ACT_AUTHOR, ACT_TITLE, "open")
    assert act is True
    assert reason


def test_gate_rejects_foreign_author(guard: ModuleType) -> None:
    act, _ = guard.should_act(ACT_HEAD_REF, "1StepMore", ACT_TITLE, "open")
    assert act is False


def test_gate_rejects_non_release_branch(guard: ModuleType) -> None:
    act, _ = guard.should_act("fix/whatever", ACT_AUTHOR, ACT_TITLE, "open")
    assert act is False


def test_gate_rejects_non_release_title(guard: ModuleType) -> None:
    act, _ = guard.should_act(ACT_HEAD_REF, ACT_AUTHOR, "feat: x", "open")
    assert act is False


def test_gate_rejects_closed_pr(guard: ModuleType) -> None:
    act, _ = guard.should_act(ACT_HEAD_REF, ACT_AUTHOR, ACT_TITLE, "closed")
    assert act is False


def test_gate_accepts_app_author(guard: ModuleType) -> None:
    act, _ = guard.should_act(ACT_HEAD_REF, "app/github-actions", ACT_TITLE, "open")
    assert act is True


# ---------------------------------------------------------------------------
# decide — gate + scope
# ---------------------------------------------------------------------------


def test_decide_gate_failure_never_snoozes(guard: ModuleType) -> None:
    decision = guard.decide(REAL_PATHS, ACT_HEAD_REF, "1StepMore", ACT_TITLE, "open")
    assert decision.snooze is False


def test_decide_freezes_internal_release(guard: ModuleType) -> None:
    decision = guard.decide(REAL_PATHS, ACT_HEAD_REF, ACT_AUTHOR, ACT_TITLE, "open")
    assert decision.snooze is True


# ---------------------------------------------------------------------------
# Taxonomy reuse, not duplication
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [".github/x.yml", "src/x.py", "docs/x.md"])
def test_taxonomy_matches_sibling(guard: ModuleType, scope: ModuleType, path: str) -> None:
    assert guard.is_internal_path(path) is scope.is_internal_path(path)


def test_guard_does_not_define_its_own_prefixes(guard: ModuleType) -> None:
    assert not hasattr(guard, "INTERNAL_PREFIXES")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_snooze_and_github_output(
    guard: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = tmp_path / "files.txt"
    files.write_text("\n".join(REAL_PATHS) + "\n", encoding="utf-8")
    output = tmp_path / "github_output.txt"
    output.write_text("other=kept\n", encoding="utf-8")

    code = guard.main(
        [
            "--files-file",
            str(files),
            "--pr-title",
            ACT_TITLE,
            "--pr-author",
            ACT_AUTHOR,
            "--head-ref",
            ACT_HEAD_REF,
            "--pr-state",
            "open",
            "--github-output",
            str(output),
        ]
    )

    assert code == 0
    captured = capsys.readouterr()
    assert "verdict: snooze" in captured.out
    assert output.read_text(encoding="utf-8") == "other=kept\nsnooze=true\n"


def test_cli_keep_for_user_visible(
    guard: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = tmp_path / "files.txt"
    files.write_text("src/automedia/x.py\n", encoding="utf-8")

    code = guard.main(
        [
            "--files-file",
            str(files),
            "--pr-title",
            ACT_TITLE,
            "--pr-author",
            ACT_AUTHOR,
            "--head-ref",
            ACT_HEAD_REF,
            "--pr-state",
            "open",
        ]
    )

    assert code == 0
    captured = capsys.readouterr()
    assert "verdict: keep" in captured.out
    assert "src/automedia/x.py" in captured.out


def test_cli_usage_error_exits_2(guard: ModuleType) -> None:
    with pytest.raises(SystemExit) as excinfo:
        guard.main(["--files-file", "/dev/null"])
    assert excinfo.value.code == 2


def test_cli_reads_stdin(
    guard: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(REAL_PATHS) + "\n"))
    code = guard.main(
        [
            "--files-file",
            "-",
            "--pr-title",
            ACT_TITLE,
            "--pr-author",
            ACT_AUTHOR,
            "--head-ref",
            ACT_HEAD_REF,
            "--pr-state",
            "open",
        ]
    )
    assert code == 0
    assert "verdict: snooze" in capsys.readouterr().out


# --- Regression: an agent-config-only release diff must be frozen (issue #126) ---
#
# PRs #127 and #128 changed only skill READMEs under .claude/ .codex/ and
# .opencode/. Those directories ship in the repo but never enter the wheel, and
# they were missing from INTERNAL_PREFIXES, so the guard read the candidate
# release as user-visible and left it alone. Release proposal #126 (1.8.1, whose
# only real diff was the version string) slipped through on exactly that path.
# Reproduce the measured `automedia-v1.8.0..main` set that defeated the guard.

REAL_PATHS_WITH_AGENT_CONFIG = [
    *REAL_PATHS,
    ".claude/skills/README.md",
    ".claude/skills/issue-triage.md",
    ".claude/skills/pr-review-merge.md",
    ".codex/skills/README.md",
    ".codex/skills/issue-triage.md",
    ".codex/skills/pr-review-merge.md",
    ".opencode/skills/README.md",
]


def test_agent_config_release_diff_is_frozen(guard: ModuleType) -> None:
    decision = guard.assess_candidate(REAL_PATHS_WITH_AGENT_CONFIG)
    assert decision.snooze is True, decision.reason


def test_real_source_change_still_blocks_the_freeze(guard: ModuleType) -> None:
    """Widening the internal prefixes must not start freezing real releases."""
    decision = guard.assess_candidate([*REAL_PATHS_WITH_AGENT_CONFIG, "src/automedia/x.py"])
    assert decision.snooze is False
    assert "src/automedia/x.py" in decision.reason
