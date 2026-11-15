"""Issue #542: ``.env`` resolution diagnostics when ``$HOME`` is rewritten."""

from __future__ import annotations

import logging
import sys

import pytest

from automedia.core import env_overlay


@pytest.fixture(autouse=True)
def _reset_overlay() -> None:
    env_overlay.reset_dotenv_overlay_cache()
    yield
    env_overlay.reset_dotenv_overlay_cache()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="pwd-based account home is POSIX-only; on Windows Path.home() ignores $HOME",
)
def test_home_mismatch_missing_file_warns_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    fake_home = tmp_path / "fakehome"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("AUTOMEDIA_DOTENV_PATH", raising=False)
    monkeypatch.delenv("AUTOMEDIA_CONFIG_DIR", raising=False)
    monkeypatch.delenv("SOME_UNSET_KEY_542", raising=False)
    env_overlay.reset_dotenv_overlay_cache()

    with caplog.at_level(logging.WARNING):
        env_overlay.env_lookup("SOME_UNSET_KEY_542")
        info = env_overlay.describe_dotenv_source()
        env_overlay.env_lookup("SOME_UNSET_KEY_542")

    expected_mismatch = (
        info["home"] is not None
        and info["account_home"] is not None
        and info["home"] != info["account_home"]
    )
    assert info["exists"] is False
    assert info["home_mismatch"] is expected_mismatch
    assert str(fake_home) in info["path"]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == (1 if expected_mismatch else 0)
    if warnings:
        assert info["path"] in warnings[0].getMessage()


def test_explicit_dotenv_path_is_used_without_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO_542=bar\n", encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_DOTENV_PATH", str(env_file))
    monkeypatch.delenv("FOO_542", raising=False)
    env_overlay.reset_dotenv_overlay_cache()

    with caplog.at_level(logging.WARNING):
        assert env_overlay.env_lookup("FOO_542") == "bar"
        info = env_overlay.describe_dotenv_source()

    assert info["source"] == "AUTOMEDIA_DOTENV_PATH"
    assert info["exists"] is True
    assert info["path"] == str(env_file)
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_real_environment_still_wins(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO_542=from_file\n", encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_DOTENV_PATH", str(env_file))
    monkeypatch.setenv("FOO_542", "from_env")
    env_overlay.reset_dotenv_overlay_cache()

    assert env_overlay.env_lookup("FOO_542") == "from_env"
