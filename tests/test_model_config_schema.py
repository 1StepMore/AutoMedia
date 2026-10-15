"""Tests for automedia.manifests.model_config_schema — ModelConfig/ProviderConfig."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

from automedia.manifests.model_config_schema import (
    ModelConfig,
    ProviderConfig,
    _parse_provider,
    backup_model_config,
    load_model_config,
    save_model_config,
    validate_model_config_updates,
)

# ---------------------------------------------------------------------------
# ProviderConfig dataclass
# ---------------------------------------------------------------------------


class TestProviderConfig:
    """Unit tests for ProviderConfig defaults."""

    def test_default_construction(self) -> None:
        pc = ProviderConfig()
        assert pc.provider == ""
        assert pc.model == ""
        assert pc.base_url == ""
        assert pc.api_key == ""

    def test_explicit_values(self) -> None:
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

    def test_default_construction(self) -> None:
        mc = ModelConfig()
        assert isinstance(mc.text_generation, ProviderConfig)
        assert isinstance(mc.vision, ProviderConfig)
        assert isinstance(mc.subtitle_proofread, ProviderConfig)
        assert isinstance(mc.translation, ProviderConfig)

    def test_slots_are_independent(self) -> None:
        mc = ModelConfig()
        mc.text_generation.model = "gpt-4"
        assert mc.vision.model == ""


# ---------------------------------------------------------------------------
# _parse_provider helper
# ---------------------------------------------------------------------------


class TestParseProvider:
    """Unit tests for the provider YAML parser."""

    def test_none_returns_default(self) -> None:
        pc = _parse_provider(None)
        assert pc.provider == ""
        assert pc.api_key == ""

    def test_non_dict_returns_default(self) -> None:
        pc = _parse_provider("not a dict")
        assert pc.provider == ""

    def test_parses_all_fields(self) -> None:
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

    def test_missing_api_key_resolves_from_credential_loader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When api_key is missing, credential_loader is used."""

        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-from-env")
        raw = {"provider": "openai", "model": "gpt-4"}
        pc = _parse_provider(raw)
        assert pc.api_key == "sk-from-env"

    def test_empty_api_key_resolves_from_credential_loader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty string api_key is treated as missing."""

        monkeypatch.setenv("AUTOMEDIA_ANTHROPIC", "sk-ant-env")
        raw = {"provider": "anthropic", "model": "claude-3", "api_key": ""}
        pc = _parse_provider(raw)
        assert pc.api_key == "sk-ant-env"

    def test_explicit_api_key_not_overridden(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When api_key is set in YAML, credential loader is NOT called."""
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-from-env")
        raw = {"provider": "openai", "model": "gpt-4", "api_key": "sk-explicit"}
        pc = _parse_provider(raw)
        assert pc.api_key == "sk-explicit"

    def test_no_provider_no_credential_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When provider is empty, no credential lookup happens."""
        raw = {"model": "gpt-4"}
        pc = _parse_provider(raw)
        assert pc.api_key == ""


# ---------------------------------------------------------------------------
# load_model_config
# ---------------------------------------------------------------------------


class TestLoadModelConfig:
    """Integration tests for load_model_config."""

    def _write_config(self, tmp_path: Path, data: dict, name: str = "model_config.yaml") -> str:
        p = tmp_path / name
        p.write_text(yaml.dump(data), encoding="utf-8")
        return str(p)

    def test_loads_full_config(self, tmp_path: Path) -> None:
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

    def test_loads_partial_config(self, tmp_path: Path) -> None:
        data = {"text_generation": {"provider": "openai", "model": "gpt-4"}}
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)

        assert mc.text_generation.model == "gpt-4"
        assert mc.vision.provider == ""  # default
        assert mc.subtitle_proofread.model == ""  # default
        assert mc.translation.api_key == ""  # default

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Model config not found"):
            load_model_config(str(tmp_path / "nope.yaml"))

    def test_non_dict_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_model_config(str(p))

    def test_empty_yaml_returns_defaults(self, tmp_path: Path) -> None:
        path = self._write_config(tmp_path, {})
        mc = load_model_config(path)
        assert mc.text_generation.provider == ""
        assert mc.vision.model == ""

    def test_api_key_resolution_integration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: missing api_key in YAML resolved from env var."""
        monkeypatch.setenv("AUTOMEDIA_MYPROVIDER", "sk-resolved")
        data = {
            "text_generation": {"provider": "myprovider", "model": "test-model"},
        }
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)
        assert mc.text_generation.api_key == "sk-resolved"

    def test_slots_are_independent_instances(self, tmp_path: Path) -> None:
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

    def test_missing_fields_default_to_empty(self, tmp_path: Path) -> None:
        data = {
            "text_generation": {"provider": "openai"},
            # model, base_url, api_key all missing
        }
        path = self._write_config(tmp_path, data)
        mc = load_model_config(path)
        assert mc.text_generation.model == ""
        assert mc.text_generation.base_url == ""


# ---------------------------------------------------------------------------
# save_model_config
# ---------------------------------------------------------------------------


class TestSaveModelConfig:
    """Unit tests for the merge-aware save_model_config writer."""

    _FALLBACK: ClassVar[list[dict[str, str]]] = [
        {
            "provider": "agnes",
            "model": "glm-4",
            "api_key": "sk-y",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
        },
        {
            "provider": "openrouter",
            "model": "openai/gpt-4o-mini",
            "api_key": "sk-z",
            "base_url": "https://openrouter.ai/api/v1",
        },
    ]

    def _seed(self, tmp_path: Path, data: dict, name: str = "model_config.yaml") -> Path:
        p = tmp_path / name
        p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return p

    def _read(self, path: Path) -> dict:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def test_preserves_fallback_chain_when_update_sets_primary_only(self, tmp_path: Path) -> None:
        """Updating only provider/model must keep the existing fallback chain."""
        seed = {
            "llm": {
                "text_generation": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "api_key": "sk-x",
                    "base_url": "https://api.deepseek.com/v1",
                    "fallback": self._FALLBACK,
                }
            }
        }
        path = self._seed(tmp_path, seed)
        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "new-provider", "model": "new-model"}}},
        )
        slot = self._read(path)["llm"]["text_generation"]
        assert slot["fallback"] == self._FALLBACK

    def test_replaces_primary_keys_while_keeping_fallback(self, tmp_path: Path) -> None:
        """Provided provider/model replace the old values; fallback is untouched."""
        seed = {
            "llm": {
                "text_generation": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "api_key": "sk-x",
                    "base_url": "https://api.deepseek.com/v1",
                    "fallback": self._FALLBACK,
                }
            }
        }
        path = self._seed(tmp_path, seed)
        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "openai", "model": "gpt-4o"}}},
        )
        slot = self._read(path)["llm"]["text_generation"]
        assert slot["provider"] == "openai"
        assert slot["model"] == "gpt-4o"
        assert slot["fallback"] == self._FALLBACK

    def test_preserves_sibling_slot(self, tmp_path: Path) -> None:
        """Updating text_generation must leave the vision slot intact."""
        seed = {
            "llm": {
                "text_generation": {"provider": "deepseek", "model": "deepseek-chat"},
                "vision": {"provider": "openai", "model": "gpt-4o-vision", "api_key": "sk-v"},
            }
        }
        path = self._seed(tmp_path, seed)
        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "new", "model": "new-model"}}},
        )
        data = self._read(path)
        assert data["llm"]["vision"] == seed["llm"]["vision"]
        assert data["llm"]["text_generation"]["provider"] == "new"

    def test_creates_file_when_missing_with_parent_dir(self, tmp_path: Path) -> None:
        """A missing file (and missing parent dir) is created from scratch."""
        path = tmp_path / "nested" / "dir" / "model_config.yaml"
        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}},
        )
        assert path.is_file()
        data = self._read(path)
        assert data["llm"]["text_generation"]["provider"] == "deepseek"
        assert data["llm"]["text_generation"]["model"] == "deepseek-chat"

    def test_chmod_0600_on_created_file(self, tmp_path: Path) -> None:
        """A newly created config file must be readable/writable by owner only."""
        path = tmp_path / "model_config.yaml"
        save_model_config(path, {"llm": {"text_generation": {"provider": "deepseek"}}})
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_unicode_content_round_trips(self, tmp_path: Path) -> None:
        """Unicode values in the base and in the update survive the write."""
        seed = {
            "llm": {
                "text_generation": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "base_url": "https://api.deepseek.com/v1",
                    "note": "中文备注",
                }
            }
        }
        path = self._seed(tmp_path, seed)
        save_model_config(
            path,
            {"llm": {"text_generation": {"model": "中文模型"}}},
        )
        slot = self._read(path)["llm"]["text_generation"]
        assert slot["model"] == "中文模型"
        assert slot["note"] == "中文备注"

    def test_non_dict_existing_content_is_replaced(self, tmp_path: Path) -> None:
        """A scalar-list YAML file must not crash; it is treated as an empty base."""
        path = tmp_path / "model_config.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}},
        )
        assert self._read(path) == {
            "llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}
        }

    def test_empty_existing_file_is_treated_as_empty_base(self, tmp_path: Path) -> None:
        """An empty file must not crash; it is treated as an empty base."""
        path = tmp_path / "model_config.yaml"
        path.write_text("", encoding="utf-8")
        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}},
        )
        assert self._read(path) == {
            "llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}
        }

    def test_unparseable_existing_content_is_treated_as_empty_base(self, tmp_path: Path) -> None:
        """Garbage YAML must not crash; it is treated as an empty base."""
        path = tmp_path / "model_config.yaml"
        path.write_text("{{{{ not: [valid", encoding="utf-8")
        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}},
        )
        assert self._read(path) == {
            "llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}
        }


class TestWriteGuards:
    """Write guards from issue #208: backup, blank-value refusal, user scope."""

    def _seed(self, tmp_path: Path, data: dict) -> Path:
        p = tmp_path / "model_config.yaml"
        p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return p

    def _read(self, path: Path) -> dict:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def test_backup_created_before_overwrite(self, tmp_path: Path) -> None:
        """An existing file is copied to a timestamped backup before the write."""
        path = self._seed(
            tmp_path,
            {"llm": {"text_generation": {"provider": "amd", "model": "old-model"}}},
        )
        before = path.read_text(encoding="utf-8")

        save_model_config(
            path,
            {"llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}},
        )

        backups = sorted(tmp_path.glob("model_config.yaml.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == before
        assert "provider: deepseek" in path.read_text(encoding="utf-8")

    def test_no_backup_when_file_is_new(self, tmp_path: Path) -> None:
        """A first write has nothing to back up and creates no backup file."""
        path = tmp_path / "nested" / "model_config.yaml"
        save_model_config(path, {"llm": {"text_generation": {"provider": "deepseek"}}})

        assert path.is_file()
        assert not list(tmp_path.rglob("*.bak-*"))

    def test_backup_model_config_returns_none_without_file(self, tmp_path: Path) -> None:
        """backup_model_config is a no-op for a path that does not exist."""
        assert backup_model_config(tmp_path / "missing.yaml") is None

    def test_failed_backup_aborts_the_write(self, tmp_path: Path, monkeypatch) -> None:
        """If the backup cannot be made, the original file is left untouched."""
        path = self._seed(
            tmp_path,
            {"llm": {"text_generation": {"provider": "amd", "model": "old-model"}}},
        )
        before = path.read_text(encoding="utf-8")

        def _boom(_src, _dst):
            raise OSError("simulated backup failure")

        monkeypatch.setattr(
            "automedia.manifests.model_config_write_guard.shutil.copy2",
            _boom,
        )

        with pytest.raises(OSError, match="pre-write backup could not be created"):
            save_model_config(
                path,
                {"llm": {"text_generation": {"provider": "deepseek"}}},
            )

        assert path.read_text(encoding="utf-8") == before

    def test_empty_provider_is_refused(self, tmp_path: Path) -> None:
        """An explicitly empty provider is refused instead of being written."""
        path = self._seed(
            tmp_path,
            {"llm": {"text_generation": {"provider": "amd", "model": "old-model"}}},
        )

        with pytest.raises(ValueError, match=r"empty llm\.text_generation\.provider"):
            save_model_config(
                path,
                {"llm": {"text_generation": {"provider": ""}}},
            )

        slot = self._read(path)["llm"]["text_generation"]
        assert slot["provider"] == "amd"

    def test_whitespace_provider_is_refused(self, tmp_path: Path) -> None:
        """A whitespace-only provider is the same corruption, also refused."""
        path = tmp_path / "model_config.yaml"
        with pytest.raises(ValueError, match=r"empty llm\.text_generation\.provider"):
            save_model_config(path, {"llm": {"text_generation": {"provider": "  "}}})
        assert not path.exists()

    def test_empty_base_url_is_refused(self, tmp_path: Path) -> None:
        """A blank base_url is not a valid endpoint and is refused."""
        path = tmp_path / "model_config.yaml"
        with pytest.raises(ValueError, match=r"empty llm\.text_generation\.base_url"):
            save_model_config(path, {"llm": {"text_generation": {"base_url": ""}}})

    def test_update_without_provider_key_still_merges(self, tmp_path: Path) -> None:
        """Omitting the key is the documented way to leave provider alone."""
        path = self._seed(
            tmp_path,
            {"llm": {"text_generation": {"provider": "amd", "model": "old-model"}}},
        )
        save_model_config(path, {"llm": {"text_generation": {"model": "new-model"}}})

        slot = self._read(path)["llm"]["text_generation"]
        assert slot["provider"] == "amd"
        assert slot["model"] == "new-model"

    def test_empty_provider_in_a_sibling_slot_is_refused(self, tmp_path: Path) -> None:
        """The guard walks every configured slot, not only text_generation."""
        path = tmp_path / "model_config.yaml"
        with pytest.raises(ValueError, match=r"empty llm\.vision\.provider"):
            save_model_config(path, {"llm": {"vision": {"provider": ""}}})

    def test_validate_model_config_updates_accepts_a_valid_update(self) -> None:
        """A well-formed update passes validation without raising."""
        validate_model_config_updates({"llm": {"text_generation": {"provider": "deepseek"}}})

    def test_validate_model_config_updates_ignores_non_llm_payload(self) -> None:
        """A payload without an ``llm`` mapping is left to the writer."""
        validate_model_config_updates({"pipeline": {"mode": "auto"}})


class TestUserScopeGuard:
    """Refusing writes into the real user config directory (issue #208)."""

    @pytest.fixture(autouse=True)
    def _isolate_user_config_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Point the user config dir at *tmp_path* before any guard runs."""
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        self._tmp = tmp_path

    def test_isolated_dir_write_is_allowed(self, tmp_path: Path) -> None:
        """With AUTOMEDIA_CONFIG_DIR set, the target is not user scope."""
        path = tmp_path / "model_config.yaml"
        save_model_config(path, {"llm": {"text_generation": {"provider": "deepseek"}}})
        assert path.is_file()

    def test_real_user_dir_is_refused_without_opt_in(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A write aimed at the resolved user config dir needs the opt-in."""
        fake_home = tmp_path / "home"
        (fake_home / ".automedia").mkdir(parents=True)
        target = fake_home / ".automedia" / "model_config.yaml"
        target.write_text("llm:\n  text_generation:\n    provider: amd\n", encoding="utf-8")

        monkeypatch.delenv("AUTOMEDIA_CONFIG_DIR")
        monkeypatch.setenv("HOME", str(fake_home))

        with pytest.raises(ValueError, match="real user config directory"):
            save_model_config(
                target,
                {"llm": {"text_generation": {"provider": "deepseek"}}},
            )

        assert "provider: amd" in target.read_text(encoding="utf-8")

    def test_opt_in_allows_the_user_dir_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """allow_user_scope=True is the documented escape hatch."""
        fake_home = tmp_path / "home"
        (fake_home / ".automedia").mkdir(parents=True)
        target = fake_home / ".automedia" / "model_config.yaml"

        monkeypatch.delenv("AUTOMEDIA_CONFIG_DIR")
        monkeypatch.setenv("HOME", str(fake_home))

        save_model_config(
            target,
            {"llm": {"text_generation": {"provider": "deepseek"}}},
            allow_user_scope=True,
        )

        assert "provider: deepseek" in target.read_text(encoding="utf-8")
