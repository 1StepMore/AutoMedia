"""Tests for the ``get_config`` MCP config introspection tool.

Tests the ``get_config`` tool handler in ``automedia.mcp.tools``.
Uses ``@patch`` on ``load_config`` to avoid file-system dependencies.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from automedia.mcp.tools import get_config

# ---------------------------------------------------------------------------
# Shared test data — a realistic config blob with a mix of normal and
# secret-containing keys at various nesting levels.
# ---------------------------------------------------------------------------

MOCK_CONFIG: dict[str, Any] = {
    "project": {
        "name": "AutoMedia",
        "version": "1.0.0",
    },
    "paths": {
        "data_dir": "./data",
        "output_dir": "./output",
    },
    "llm": {
        "text_generation": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-real-secret-123",
            "temperature": 0.7,
            "max_tokens": 2048,
        },
    },
    "platforms": {
        "wechat": {
            "enabled": False,
            "adapter": "wechat",
            "app_secret": "wxb2233c55",
            "access_token": "token_abc123",
        },
    },
    "content": {
        "default_tone": "neutral",
        "default_language": "zh",
    },
    "pool": {
        "retention_days": 7,
        "redis_password": "hunter2",
    },
}


# ===================================================================
# Tests: get_config — no key (full config dump)
# ===================================================================


class TestGetConfigFull:
    """Tests for ``get_config()`` with no key (returns all config)."""

    @patch("automedia.core.config_loader.load_config")
    def test_returns_redacted_config(self, mock_load: MagicMock) -> None:
        """Full config return must redact secret keys."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config()

        assert "config" in result
        cfg = result["config"]

        # Normal values survive
        assert cfg["content"]["default_tone"] == "neutral"
        assert cfg["paths"]["output_dir"] == "./output"

        # Secret values are redacted
        assert cfg["llm"]["text_generation"]["api_key"] == "***REDACTED***"
        assert cfg["platforms"]["wechat"]["app_secret"] == "***REDACTED***"
        assert cfg["platforms"]["wechat"]["access_token"] == "***REDACTED***"
        assert cfg["pool"]["redis_password"] == "***REDACTED***"

        # Non-secret siblings survive
        assert cfg["llm"]["text_generation"]["model"] == "gpt-4o-mini"
        assert cfg["llm"]["text_generation"]["temperature"] == 0.7

    @patch("automedia.core.config_loader.load_config")
    def test_no_secret_keys_in_top_level(self, mock_load: MagicMock) -> None:
        """Config dict returned to the caller must not contain secret values."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config()
        cfg = result["config"]

        # Walk all leaves — none should contain a plaintext secret
        secrets = {"key", "secret", "password", "token"}

        def _check_leaves(obj: object, path: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _check_leaves(v, f"{path}.{k}" if path else k)
            elif any(kw in path.lower() for kw in secrets):
                # Paths ending with a keyword should be redacted
                last_seg = path.rsplit(".", 1)[-1] if "." in path else path
                if any(kw in last_seg.lower() for kw in secrets):
                    assert obj == "***REDACTED***", (
                        f"Leaf at '{path}' should be redacted, got {obj!r}"
                    )

        _check_leaves(cfg)

    @patch("automedia.core.config_loader.load_config")
    def test_no_key_preserves_structures(self, mock_load: MagicMock) -> None:
        """Non-secret nested dicts should remain intact."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config()

        assert result["config"]["paths"]["data_dir"] == "./data"
        assert result["config"]["content"]["default_language"] == "zh"


# ===================================================================
# Tests: get_config — specific key lookup
# ===================================================================


class TestGetConfigByKey:
    """Tests for ``get_config(key="...")`` with a specific key."""

    @patch("automedia.core.config_loader.load_config")
    def test_simple_key(self, mock_load: MagicMock) -> None:
        """A simple top-level key returns the expected value."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config(key="project")

        assert "value" in result
        assert result["value"]["name"] == "AutoMedia"
        assert result["value"]["version"] == "1.0.0"

    @patch("automedia.core.config_loader.load_config")
    def test_dot_notation(self, mock_load: MagicMock) -> None:
        """Dot-notation traversal resolves nested keys."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config(key="llm.text_generation.temperature")

        assert result["value"] == 0.7

    @patch("automedia.core.config_loader.load_config")
    def test_dot_notation_deep_string(self, mock_load: MagicMock) -> None:
        """Dot-notation returns string values too."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config(key="paths.output_dir")

        assert result["value"] == "./output"

    @patch("automedia.core.config_loader.load_config")
    def test_key_not_found(self, mock_load: MagicMock) -> None:
        """Missing key returns an error message."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config(key="nonexistent.setting")

        assert "error" in result
        assert "not found" in result["error"]

    @patch("automedia.core.config_loader.load_config")
    def test_partial_path_missing(self, mock_load: MagicMock) -> None:
        """Partial missing path also returns an error."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config(key="content.nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    @patch("automedia.core.config_loader.load_config")
    def test_secret_key_rejected(self, mock_load: MagicMock) -> None:
        """Requesting a secret key directly returns a specific error."""
        mock_load.return_value = MOCK_CONFIG

        result = get_config(key="llm.text_generation.api_key")

        assert "error" in result
        assert result["error"] == "secret key not exposed"

    @patch("automedia.core.config_loader.load_config")
    def test_other_secret_keywords_rejected(self, mock_load: MagicMock) -> None:
        """All secret keywords (key, secret, password, token) are rejected."""
        mock_load.return_value = MOCK_CONFIG

        assert get_config(key="platforms.wechat.app_secret")["error"] == "secret key not exposed"
        assert get_config(key="platforms.wechat.access_token")["error"] == "secret key not exposed"
        assert get_config(key="pool.redis_password")["error"] == "secret key not exposed"


# ===================================================================
# Tests: get_config — error handling
# ===================================================================


class TestGetConfigErrors:
    """Tests for ``get_config`` error handling."""

    @patch("automedia.core.config_loader.load_config")
    def test_load_config_raises(self, mock_load: MagicMock) -> None:
        """When load_config raises, get_config returns an error dict."""
        mock_load.side_effect = RuntimeError("boom")

        result = get_config()

        assert "error" in result
        assert "boom" in result["error"]

    @patch("automedia.core.config_loader.load_config")
    def test_load_config_raises_with_key(self, mock_load: MagicMock) -> None:
        """Error from load_config when a key is provided."""
        mock_load.side_effect = ValueError("bad config")

        result = get_config(key="project")

        assert "error" in result
        assert "bad config" in result["error"]
