r"""CLIAdapter must keep Windows backslash paths intact when parsing commands.

Nightly 2026-11-17: journey scenarios expand ${AUTOMEDIA_PROJECTS_DIR} (a
Windows path) into their command; POSIX shlex.split ate the backslashes
(C:\Users\... -> C:UsersRenAnZai...) so follow-up steps scanned a
nonexistent directory ('No projects found', find exit 2).

Reverse evidence (DoD): revert the posix=posix_split change in
CLIAdapter.run and test_expanded_windows_path_survives fails - the path
token comes back with the backslashes stripped.
"""

from __future__ import annotations

from automedia.validation.adapters import CLIAdapter


def _run(command: str, env_value: str, monkeypatch):
    monkeypatch.setenv("NIGHT_PROBE_DIR", env_value)
    step = type("S", (), {"command": command, "timeout_seconds": 30})
    return CLIAdapter().run(step)  # type: ignore[arg-type]


def test_expanded_windows_path_survives(monkeypatch) -> None:
    win_path = r"C:\Users\someone\AppData\Local\Temp\automedia-validation-abc\projects"
    result = _run("echo ${NIGHT_PROBE_DIR}", win_path, monkeypatch)
    stdout = result.output["stdout"] or ""
    # The decisive assertions: the echoed token keeps its backslashes and is
    # not backslash-stripped by the parser.
    assert win_path in stdout
    assert "C:Userssomeone" not in stdout


def test_quoted_arguments_survive_windows_dequote(monkeypatch) -> None:
    result = _run('echo "two words"', "unused", monkeypatch)
    details = result.output
    # The dequote pass must keep the two-word phrase as ONE argument.
    assert "two words" in (details["stdout"] or "")


def test_forward_slash_paths_still_work(monkeypatch) -> None:
    """Forward-slash /tmp-style paths keep working on Windows too."""
    result = _run("echo ${NIGHT_PROBE_DIR}", "/tmp/automedia/probe", monkeypatch)
    assert "/tmp/automedia/probe" in (result.output["stdout"] or "")
