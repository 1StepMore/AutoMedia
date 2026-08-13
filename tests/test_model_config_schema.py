"""Tests for automedia.manifests.model_config_schema — ModelConfig/ProviderConfig."""

from __future__ import annotations

import pytest
import yaml

from automedia.manifests.model_config_schema import (
    ModelConfig,
    ProviderConfig,
    _parse_provider,
    load_model_config,
)

# ---------------------------------------------------------------------------
# ProviderConfig dataclass
# ---------------------------------------------------------------------------


class TestProviderConfig:
    """Unit tests for ProviderConfig defaults."""

    def test_default_construction(self):
        pc = ProviderConfig()
        assert pc.provider == ""
        assert pc.model == ""
        assert pc.base_url == ""
        assert pc.api_key == ""

    def test_explicit_values(self):
        pc = ProviderConfig(
            provider="openai", model="gpt-4", base_url="https://api.openai.com/v1", api_key="sk-123"
        )
        assert pc.provider == "openai"
        assert pc.model == "gpt-4"
        assert pc.base_url == "https://api.openai.com/v1"
        assert pc.api_key == "sk-123"


# ---------------------------------------------------------------------------
# ModelConfig dataclass
# ---------------------------------------------------------------------------


class TestModelConfig:
    """Unit tests for ModelConfig defaults."""

    def test_default_construction(self):
        mc = ModelConfig()
        assert isinstance(mc.text_generation, ProviderConfig)
        assert isinstance(mc.vision, ProviderConfig)
        assert isinstance(mc.subtitle_proofread, ProviderConfig)
        assert isinstance(mc.translation, ProviderConfig)

    def test_slots_are_independent(self):
        mc = ModelConfig()
        mc.text_generation.model = "gpt-4"
        assert mc.vision.model == ""


# ---------------------------------------------------------------------------
# _parse_provider helper
# ---------------------------------------------------------------------------


class TestParseProvider:
    """Unit tests for the provider YAML parser."""

    def test_none_returns_default(self):
        pc = _parse_provider(None)
        assert pc.provider == ""
        assert pc.api_key == ""

    def test_non_dict_returns_default(self):
        pc = _parse_provider("not a dict")
        assert pc.provider == ""

    def test_parses_all_fields(self):
        raw = {
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
        }
        pc = _parse_provider(raw)
        assert pc.provider == "openai"
        assert pc.model == "gpt-4o"
        assert pc.base_url == "https://api.openai.com/v1"
        assert pc.api_key == "sk-test"

    def test_missing_api_key_resolves_from_credential_loader(self, monkeypatch):
        """When api_key is missing, credential_loader is used."""

        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-from-env")
        raw = {"provider": "openai", "model": "gpt-4"}
        pc = _parse_provider(raw)
        assert pc.api_key == "sk-from-env"

    def test_empty_api_key_resolves_from_credential_loader(self, monkeypatch):
        """Empty string api_key is treated as missing."""

        monkeypatch.setenv("AUTOMEDIA_ANTHROPIC", "sk-ant-env")
        raw = {"provider": "anthropic", "model": "claude-3", "api_key": ""}
        pc = _parse_provider(raw)
        assert pc.api_key == "sk-ant-env"

    def test_explicit_api_key_not_overridden(self, monkeypatch):
        """When api_key is set in YAML, credential loader is NOT called."""
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-from-env")
        raw = {"provider": "openai", "model": "gpt-4", "api_key": "sk-explicit"}
        pc = _parse_provider(raw)
        assert pc.api_key == "sk-explicit"

    def test_no_provider_no_credential_lookup(self, monkeypatch):
        """When provider is empty, no credential lookup happens."""
        raw = {"model": "gpt-4"}
        pc = _parse_provider(raw)
        assert pc.api_key == ""


# ---------------------------------------------------------------------------
# load_model_config
# ---------------------------------------------------------------------------


class TestLoadModelConfig:
    """Integration tests for load_model_config."""

    def _write_config(self, tmp_path, data: dict, name: str = "model_config.yaml"):
        p = tmp_path / name
        p.write_text(yaml.dump(data), encoding="utf-8")
        return str(p)

    def test_loads_full_config(self, tmp_path):
        data = {
            "text_generation": {
                "provider": "openai",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-openai",
            },
            "vision": {
                "provider": "openai",
                "model": "gpt-4o-vision",
                "api_key": "sk-vision",
            },
            "subtitle_proofread": {
                "provider": "anthropic",
                "model": "claude-3",
                "api_key": "sk-ant",
            },
            "translation": {
                "provider": "deepseek",
                "model": "deepseek-v2",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-ds",
            },
        }
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)

        assert mc.text_generation.provider == "openai"
        assert mc.text_generation.model == "gpt-4o"
        assert mc.vision.model == "gpt-4o-vision"
        assert mc.subtitle_proofread.provider == "anthropic"
        assert mc.translation.base_url == "https://api.deepseek.com"

    def test_loads_partial_config(self, tmp_path):
        data = {"text_generation": {"provider": "openai", "model": "gpt-4"}}
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)

        assert mc.text_generation.model == "gpt-4"
        assert mc.vision.provider == ""  # default
        assert mc.subtitle_proofread.model == ""  # default
        assert mc.translation.api_key == ""  # default

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Model config not found"):
            load_model_config(str(tmp_path / "nope.yaml"))

    def test_non_dict_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_model_config(str(p))

    def test_empty_yaml_returns_defaults(self, tmp_path):
        path = self._write_config(tmp_path, {})
        mc = load_model_config(path)
        assert mc.text_generation.provider == ""
        assert mc.vision.model == ""

    def test_api_key_resolution_integration(self, tmp_path, monkeypatch):
        """End-to-end: missing api_key in YAML resolved from env var."""
        monkeypatch.setenv("AUTOMEDIA_MYPROVIDER", "sk-resolved")
        data = {
            "text_generation": {"provider": "myprovider", "model": "test-model"},
        }
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)
        assert mc.text_generation.api_key == "sk-resolved"

    def test_slots_are_independent_instances(self, tmp_path):
        data = {
            "text_generation": {"provider": "a", "model": "m1"},
            "vision": {"provider": "b", "model": "m2"},
        }
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)

        assert mc.text_generation.provider == "a"
        assert mc.vision.provider == "b"
        # Mutating one doesn't affect the other
        mc.text_generation.model = "changed"
        assert mc.vision.model == "m2"

    def test_missing_fields_default_to_empty(self, tmp_path):
        data = {
            "text_generation": {"provider": "openai"},
            # model, base_url, api_key all missing
        }
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)
        assert mc.text_generation.model == ""
        assert mc.text_generation.base_url == ""
