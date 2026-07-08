"""E2E: Provider switching in model_config.yaml propagates to config and LLM client.

Verifies that changing ``provider`` in model_config.yaml causes both the parsed
:class:`~automedia.manifests.model_config_schema.ProviderConfig` and the
LLM client construction to reflect the new provider.

PRD-1 M4: "切换 model_config.yaml 的 provider 后, 所有 LLM 调用指向新 endpoint"

All tests are offline — no real LLM API calls are made.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from automedia.core.config_loader import load_config
from automedia.core.llm_client import LLMError, _build_client
from automedia.manifests.model_config_schema import load_model_config


# ---------------------------------------------------------------------------
# Auto-clean AUTOMEDIA_* env vars so load_config tests are isolated
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_automedia_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove AUTOMEDIA_* env vars loaded from .env so config tests are isolated."""
    original = {k: v for k, v in os.environ.items() if k.startswith("AUTOMEDIA_")}
    for k in original:
        monkeypatch.delenv(k, raising=False)


# ---------------------------------------------------------------------------
# Isolate ~/.automedia so user config does not pollute tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_user_automedia(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect ``~/.automedia`` to a temp directory so existing user config
    does not interfere with ``load_config`` tests."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(os.path, "expanduser", lambda _: str(fake_home / ".automedia"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_model_config(tmp_path: Path, data: dict[str, Any], name: str = "model_config.yaml") -> str:
    """Write *data* as YAML to *tmp_path*/*name* and return the absolute path."""
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return str(p)


def _build_llm_cfg(provider: str, api_key: str = "sk-test") -> dict[str, Any]:
    """Build a minimal ``llm.text_generation`` config dict for *provider*."""
    return {
        "llm": {
            "text_generation": {
                "provider": provider,
                "model": _PROVIDER_MODELS[provider],
                "base_url": _PROVIDER_URLS[provider],
                "api_key": api_key,
            }
        }
    }


_PROVIDER_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

_PROVIDER_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "deepseek": "deepseek-v3",
}


# ---------------------------------------------------------------------------
# Tests — load_model_config parses provider correctly
# ---------------------------------------------------------------------------


class TestLoadModelConfigProvider:
    """``load_model_config`` correctly reflects the ``provider`` field."""

    def test_openai_provider(self, tmp_path: Path) -> None:
        """Parsing YAML with provider=openai yields ``ProviderConfig.provider == 'openai'``."""
        data = {
            "text_generation": {
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-openai-test",
            }
        }
        path = _write_model_config(tmp_path, data)
        mc = load_model_config(path)

        assert mc.text_generation.provider == "openai"
        assert mc.text_generation.model == "gpt-4o"
        assert mc.text_generation.base_url == "https://api.openai.com/v1"
        assert mc.text_generation.api_key == "sk-openai-test"

    def test_anthropic_provider(self, tmp_path: Path) -> None:
        """Switching provider to 'anthropic' yields ``ProviderConfig.provider == 'anthropic'``."""
        data = {
            "text_generation": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "sk-ant-test",
            }
        }
        path = _write_model_config(tmp_path, data)
        mc = load_model_config(path)

        assert mc.text_generation.provider == "anthropic"
        assert mc.text_generation.model == "claude-sonnet-4-20250514"
        assert mc.text_generation.base_url == "https://api.anthropic.com/v1"

    def test_switch_from_openai_to_anthropic(self, tmp_path: Path) -> None:
        """Overwriting an openai config with anthropic updates the provider (switch scenario)."""
        # Phase 1: openai
        data_openai = {
            "text_generation": {
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-openai",
            }
        }
        path = _write_model_config(tmp_path, data_openai)
        mc = load_model_config(path)
        assert mc.text_generation.provider == "openai"
        assert mc.text_generation.base_url == "https://api.openai.com/v1"

        # Phase 2: overwrite file with anthropic — config changes
        data_anthropic = {
            "text_generation": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "sk-ant",
            }
        }
        path = _write_model_config(tmp_path, data_anthropic)
        mc = load_model_config(path)
        assert mc.text_generation.provider == "anthropic"
        assert mc.text_generation.base_url == "https://api.anthropic.com/v1"

    def test_multiple_providers_in_different_slots(self, tmp_path: Path) -> None:
        """Different task slots can use different providers simultaneously."""
        data = {
            "text_generation": {
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-openai",
            },
            "vision": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "sk-ant",
            },
        }
        path = _write_model_config(tmp_path, data)
        mc = load_model_config(path)

        assert mc.text_generation.provider == "openai"
        assert mc.vision.provider == "anthropic"
        # Slots that are not in the YAML get default (empty) ProviderConfig
        assert mc.subtitle_proofread.provider == ""
        assert mc.translation.provider == ""


# ---------------------------------------------------------------------------
# Tests — LLM client resolves correct endpoint / base_url per provider
# ---------------------------------------------------------------------------


class TestLLMClientEndpointResolution:
    """``_build_client`` passes provider-specific parameters to ``OpenAI()``."""

    def test_openai_endpoint(self) -> None:
        """With provider=openai, ``_build_client`` passes the OpenAI base_url."""
        config = _build_llm_cfg("openai")
        with patch("openai.OpenAI") as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(
                api_key="sk-test",
                base_url="https://api.openai.com/v1",
            )

    def test_anthropic_endpoint(self) -> None:
        """With provider=anthropic, ``_build_client`` passes the Anthropic base_url."""
        config = _build_llm_cfg("anthropic")
        with patch("openai.OpenAI") as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(
                api_key="sk-test",
                base_url="https://api.anthropic.com/v1",
            )

    def test_deepseek_endpoint(self) -> None:
        """With provider=deepseek, ``_build_client`` passes the DeepSeek base_url."""
        config = _build_llm_cfg("deepseek")
        with patch("openai.OpenAI") as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(
                api_key="sk-test",
                base_url="https://api.deepseek.com/v1",
            )

    def test_base_url_omitted_when_empty(self) -> None:
        """When base_url is empty, ``OpenAI()`` is called without ``base_url`` (uses library default)."""
        config = {
            "llm": {
                "text_generation": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "base_url": "",
                    "api_key": "sk-test",
                }
            }
        }
        with patch("openai.OpenAI") as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(api_key="sk-test")

    def test_api_key_resolved_from_env_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When api_key is absent in config, ``resolve_api_key`` supplies it from ``AUTOMEDIA_*``."""
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-from-env")
        config = {
            "llm": {
                "text_generation": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "base_url": "https://api.openai.com/v1",
                }
            }
        }
        with patch("openai.OpenAI") as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(
                api_key="sk-from-env",
                base_url="https://api.openai.com/v1",
            )

    def test_missing_api_key_raises_llm_error(self) -> None:
        """When no api_key can be resolved, ``_build_client`` raises ``LLMError``."""
        config = {
            "llm": {
                "text_generation": {
                    "provider": "unknown-provider",
                    "model": "test-model",
                    "base_url": "https://example.com",
                    # api_key omitted and no env → should raise
                }
            }
        }
        with pytest.raises(LLMError, match="No API key"):
            _build_client(config)


# ---------------------------------------------------------------------------
# Tests — load_config picks up provider from project .automedia/model_config.yaml
# ---------------------------------------------------------------------------


class TestLoadConfigProviderMerge:
    """``load_config()`` reads ``llm.text_generation.provider`` from project config."""

    def _create_project_config(self, tmp_path: Path, provider: str) -> str:
        """Create ``.automedia/model_config.yaml`` with an ``llm`` section."""
        config_dir = tmp_path / ".automedia"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "model_config.yaml"
        data = {
            "llm": {
                "text_generation": {
                    "provider": provider,
                    "model": "test-model",
                    "base_url": f"https://api.{provider}.com/v1",
                }
            }
        }
        config_file.write_text(yaml.dump(data), encoding="utf-8")
        return str(config_dir)

    def test_openai_provider(self, tmp_path: Path) -> None:
        """``load_config`` returns ``llm.text_generation.provider == 'openai'`` from project config."""
        config_dir = self._create_project_config(tmp_path, "openai")
        config = load_config(config_dir=config_dir)

        llm_tg = config.get("llm", {}).get("text_generation", {})
        assert llm_tg.get("provider") == "openai"
        assert llm_tg.get("model") == "test-model"
        assert llm_tg.get("base_url") == "https://api.openai.com/v1"

    def test_anthropic_provider(self, tmp_path: Path) -> None:
        """``load_config`` returns ``llm.text_generation.provider == 'anthropic'`` after switching."""
        config_dir = self._create_project_config(tmp_path, "anthropic")
        config = load_config(config_dir=config_dir)

        llm_tg = config.get("llm", {}).get("text_generation", {})
        assert llm_tg.get("provider") == "anthropic"
        assert llm_tg.get("model") == "test-model"
        assert llm_tg.get("base_url") == "https://api.anthropic.com/v1"

    def test_project_config_overrides_builtin_default(self, tmp_path: Path) -> None:
        """Project-level provider ('anthropic') overrides the built-in default ('openai')."""
        config_dir = self._create_project_config(tmp_path, "anthropic")
        config = load_config(config_dir=config_dir)

        assert config["llm"]["text_generation"]["provider"] == "anthropic"
