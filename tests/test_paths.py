"""Tests for automedia.core.paths — user config directory resolution."""

from __future__ import annotations

import os
from pathlib import Path

from automedia.core.paths import get_user_config_dir


class TestGetUserConfigDir:
    """get_user_config_dir() must respect AUTOMEDIA_CONFIG_DIR when set."""

    def test_default_returns_home_dot_automedia(self) -> None:
        """When AUTOMEDIA_CONFIG_DIR is not set, returns ~/.automedia."""
        os.environ.pop("AUTOMEDIA_CONFIG_DIR", None)
        result = get_user_config_dir()
        assert result == Path.home() / ".automedia"

    def test_env_var_override(self) -> None:
        """AUTOMEDIA_CONFIG_DIR redirects the config directory."""
        os.environ["AUTOMEDIA_CONFIG_DIR"] = "/tmp/test-automedia-config"
        try:
            result = get_user_config_dir()
            assert result == Path("/tmp/test-automedia-config").resolve()
        finally:
            os.environ.pop("AUTOMEDIA_CONFIG_DIR", None)

    def test_env_var_with_tilde(self) -> None:
        """Tilde in AUTOMEDIA_CONFIG_DIR is expanded."""
        os.environ["AUTOMEDIA_CONFIG_DIR"] = "~/.test-automedia-config"
        try:
            result = get_user_config_dir()
            assert result == Path("~/.test-automedia-config").expanduser().resolve()
        finally:
            os.environ.pop("AUTOMEDIA_CONFIG_DIR", None)

    def test_env_var_trailing_slash(self) -> None:
        """Trailing slash in AUTOMEDIA_CONFIG_DIR is normalised."""
        os.environ["AUTOMEDIA_CONFIG_DIR"] = "/tmp/test-automedia-trailing//"
        try:
            result = get_user_config_dir()
            assert result == Path("/tmp/test-automedia-trailing").resolve()
        finally:
            os.environ.pop("AUTOMEDIA_CONFIG_DIR", None)
