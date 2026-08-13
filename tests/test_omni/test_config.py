"""Tests for automedia.omni.config — OmniConfig / load_omni_config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from automedia.omni.config import OmniConfig, load_omni_config


class TestOmniConfig:
    def test_default_construction(self):
        cfg = OmniConfig()
        assert cfg.integration_mode == "sdk"
        assert cfg.max_auto_extract_mb == 50

    def test_explicit_values(self):
        cfg = OmniConfig(integration_mode="subprocess", max_auto_extract_mb=200)
        assert cfg.integration_mode == "subprocess"
        assert cfg.max_auto_extract_mb == 200


class TestLoadOmniConfig:
    def _write_config(self, tmp_path, data: dict, name: str = "omni_config.yaml"):
        p = tmp_path / name
        p.write_text(yaml.dump(data), encoding="utf-8")
        return p

    def test_loads_full_config(self, tmp_path):
        data = {"integration_mode": "subprocess", "max_auto_extract_mb": 100}
        path = self._write_config(tmp_path, data)
        cfg = load_omni_config(path)
        assert cfg.integration_mode == "subprocess"
        assert cfg.max_auto_extract_mb == 100

    def test_loads_partial_config(self, tmp_path):
        data = {"integration_mode": "sdk"}
        path = self._write_config(tmp_path, data)
        cfg = load_omni_config(path)
        assert cfg.integration_mode == "sdk"
        assert cfg.max_auto_extract_mb == 50  # default

    def test_missing_config_returns_defaults(self, tmp_path):
        path = tmp_path / "nonexistent.yaml"
        cfg = load_omni_config(path)
        assert cfg.integration_mode == "sdk"
        assert cfg.max_auto_extract_mb == 50

    def test_custom_config_path(self, tmp_path):
        data = {"integration_mode": "subprocess", "max_auto_extract_mb": 75}
        path = self._write_config(tmp_path, data, name="custom_config.yaml")
        cfg = load_omni_config(path)
        assert cfg.integration_mode == "subprocess"
        assert cfg.max_auto_extract_mb == 75

    def test_invalid_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_omni_config(p)

    def test_empty_yaml_returns_defaults(self, tmp_path):
        p = self._write_config(tmp_path, {})
        cfg = load_omni_config(p)
        assert cfg.integration_mode == "sdk"
        assert cfg.max_auto_extract_mb == 50

    def test_default_path_when_none(self, monkeypatch, tmp_path):
        """When config_path=None, ~/.automedia/omni_config.yaml is used."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        cfg = load_omni_config()
        assert isinstance(cfg, OmniConfig)
        assert cfg.integration_mode == "sdk"

    def test_default_path_loads_file(self, monkeypatch, tmp_path):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        config_dir = fake_home / ".automedia"
        config_dir.mkdir()
        config_file = config_dir / "omni_config.yaml"
        config_file.write_text(
            yaml.dump({"integration_mode": "subprocess", "max_auto_extract_mb": 999}),
            encoding="utf-8",
        )

        cfg = load_omni_config()
        assert cfg.integration_mode == "subprocess"
        assert cfg.max_auto_extract_mb == 999
