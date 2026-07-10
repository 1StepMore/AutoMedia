"""Tests for automedia.core.config_loader — 6-layer priority merge."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from automedia.core.config_loader import (
    _env_to_config,
    _load_j2_dir,
    _load_yaml_dir,
    _load_yaml_file,
    deep_merge,
    load_config,
)


@pytest.fixture(autouse=True)
def _clear_automedia_env_vars(monkeypatch):
    """Remove AUTOMEDIA_* env vars loaded from .env so config tests are isolated."""
    original = {k: v for k, v in os.environ.items() if k.startswith("AUTOMEDIA_")}
    for k in original:
        monkeypatch.delenv(k, raising=False)
    yield


# ---------------------------------------------------------------------------
# deep_merge
# ---------------------------------------------------------------------------


class TestDeepMerge:
    """Unit tests for the recursive dict merge helper."""

    def test_flat_overwrite(self):
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        over = {"a": {"y": 99, "z": 3}}
        expected = {"a": {"x": 1, "y": 99, "z": 3}}
        assert deep_merge(base, over) == expected

    def test_scalar_overwritten_by_dict(self):
        assert deep_merge({"a": 1}, {"a": {"x": 1}}) == {"a": {"x": 1}}

    def test_dict_overwritten_by_scalar(self):
        assert deep_merge({"a": {"x": 1}}, {"a": 1}) == {"a": 1}

    def test_empty_override_is_noop(self):
        assert deep_merge({"a": 1}, {}) == {"a": 1}

    def test_empty_base(self):
        assert deep_merge({}, {"a": 1}) == {"a": 1}

    def test_inputs_not_mutated(self):
        base = {"a": {"x": 1}}
        over = {"a": {"y": 2}}
        deep_merge(base, over)
        assert base == {"a": {"x": 1}}
        assert over == {"a": {"y": 2}}

    def test_deep_nesting(self):
        base = {"a": {"b": {"c": {"d": 1}}}}
        over = {"a": {"b": {"c": {"d": 2, "e": 3}}}}
        result = deep_merge(base, over)
        assert result == {"a": {"b": {"c": {"d": 2, "e": 3}}}}


# ---------------------------------------------------------------------------
# _load_yaml_file
# ---------------------------------------------------------------------------


class TestLoadYamlFile:
    def test_missing_file_returns_empty(self, tmp_path):
        assert _load_yaml_file(tmp_path / "nope.yaml") == {}

    def test_loads_valid_yaml(self, tmp_path):
        p = tmp_path / "c.yaml"
        p.write_text("x: 1\ny: hello\n")
        assert _load_yaml_file(p) == {"x": 1, "y": "hello"}

    def test_empty_yaml_returns_empty(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        assert _load_yaml_file(p) == {}

    def test_non_dict_yaml_returns_empty(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- a\n- b\n")
        assert _load_yaml_file(p) == {}


# ---------------------------------------------------------------------------
# _load_yaml_dir
# ---------------------------------------------------------------------------


class TestLoadYamlDir:
    def test_missing_dir_returns_empty(self):
        assert _load_yaml_dir("/nonexistent/path/xyz") == {}

    def test_loads_yaml_and_yml(self, tmp_path):
        (tmp_path / "a.yaml").write_text("x: 1")
        (tmp_path / "b.yml").write_text("y: 2")
        result = _load_yaml_dir(str(tmp_path))
        assert result == {"x": 1, "y": 2}

    def test_skips_non_yaml_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("ignore me")
        (tmp_path / "a.yaml").write_text("x: 1")
        result = _load_yaml_dir(str(tmp_path))
        assert result == {"x": 1}

    def test_sorted_order_later_wins(self, tmp_path):
        (tmp_path / "b.yaml").write_text("x: 2")
        (tmp_path / "a.yaml").write_text("x: 1")
        result = _load_yaml_dir(str(tmp_path))
        assert result["x"] == 2  # b.yaml processed after a.yaml

    def test_nested_merge_across_files(self, tmp_path):
        (tmp_path / "a.yaml").write_text("llm:\n  model: gpt-4")
        (tmp_path / "b.yaml").write_text("llm:\n  api_key: sk-123")
        result = _load_yaml_dir(str(tmp_path))
        assert result == {"llm": {"model": "gpt-4", "api_key": "sk-123"}}


# ---------------------------------------------------------------------------
# _load_j2_dir
# ---------------------------------------------------------------------------


class TestLoadJ2Dir:
    def test_missing_dir_returns_empty(self):
        assert _load_j2_dir("/nonexistent/path/xyz") == {}

    def test_loads_j2_files(self, tmp_path):
        (tmp_path / "greeting.j2").write_text("Hello {{ name }}")
        (tmp_path / "farewell.j2").write_text("Goodbye {{ name }}")
        result = _load_j2_dir(str(tmp_path))
        assert result == {
            "prompts": {
                "greeting": "Hello {{ name }}",
                "farewell": "Goodbye {{ name }}",
            }
        }

    def test_skips_non_j2_files(self, tmp_path):
        (tmp_path / "notes.txt").write_text("ignore")
        (tmp_path / "p.j2").write_text("content")
        result = _load_j2_dir(str(tmp_path))
        assert result == {"prompts": {"p": "content"}}

    def test_sorted_order(self, tmp_path):
        (tmp_path / "z.j2").write_text("last")
        (tmp_path / "a.j2").write_text("first")
        result = _load_j2_dir(str(tmp_path))
        assert list(result["prompts"].keys()) == ["a", "z"]


# ---------------------------------------------------------------------------
# _env_to_config
# ---------------------------------------------------------------------------


class TestEnvToConfig:
    @pytest.fixture(autouse=True)
    def _clear_automedia_env(self, monkeypatch):
        """Clear existing AUTOMEDIA_* env vars so tests run in a clean environment."""
        original = {k: v for k, v in os.environ.items() if k.startswith("AUTOMEDIA_")}
        for k in original:
            monkeypatch.delenv(k, raising=False)
        yield

    def test_basic_mapping(self, monkeypatch):
        monkeypatch.setenv("AUTOMEDIA_FOO", "bar")
        result = _env_to_config()
        assert result == {"foo": "bar"}

    def test_nested_mapping(self, monkeypatch):
        monkeypatch.setenv("AUTOMEDIA_LLM_API_KEY", "sk-test")
        result = _env_to_config()
        assert result == {"llm": {"text_generation": {"api_key": "sk-test"}}}

    def test_ignores_non_prefix_vars(self, monkeypatch):
        monkeypatch.setenv("HOME", "/tmp")
        monkeypatch.setenv("AUTOMEDIA_X", "1")
        result = _env_to_config()
        assert result == {"x": "1"}
        assert "home" not in result

    def test_empty_prefix_only_is_skipped(self, monkeypatch):
        monkeypatch.setenv("AUTOMEDIA_", "val")
        result = _env_to_config()
        assert result == {}

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("AUTOMEDIA_A", "1")
        monkeypatch.setenv("AUTOMEDIA_B_C", "2")
        result = _env_to_config()
        assert result == {"a": "1", "b": {"c": "2"}}

    def test_values_are_strings(self, monkeypatch):
        monkeypatch.setenv("AUTOMEDIA_NUM", "42")
        result = _env_to_config()
        assert result["num"] == "42"  # env vars are always strings


# ---------------------------------------------------------------------------
# load_config – integration tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Integration tests for the full 6-layer config merge."""

    @staticmethod
    def _setup_dirs(tmp_path: Path):
        """Create the standard directory layout under *tmp_path*.

        Returns ``(project_dir, home_dir, user_dir, rules_dir, prompts_dir)``.
        """
        project = tmp_path / "project" / ".automedia"
        project.mkdir(parents=True)
        home = tmp_path / "home"
        user = home / ".automedia"
        user.mkdir(parents=True)
        rules = user / "overrides" / "rules"
        rules.mkdir(parents=True)
        prompts = user / "overrides" / "prompts"
        prompts.mkdir(parents=True)
        return project, home, user, rules, prompts

    # -- Layer priority -------------------------------------------------------

    def test_defaults_loaded(self, tmp_path, monkeypatch):
        """Layer 1: built-in defaults.yaml is the base config."""
        project, home, *_ = self._setup_dirs(tmp_path)
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        config = load_config(config_dir=str(project))
        assert "llm" in config
        assert "text_generation" in config["llm"]
        assert config["llm"]["text_generation"]["temperature"] == 0.7

    def test_project_overrides_defaults(self, tmp_path, monkeypatch):
        """Layer 2 > Layer 1."""
        project, home, *_ = self._setup_dirs(tmp_path)
        (project / "override.yaml").write_text("llm:\n  text_generation:\n    model: gpt-4\n")
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        config = load_config(config_dir=str(project))
        assert config["llm"]["text_generation"]["model"] == "gpt-4"
        # defaults still present
        assert config["llm"]["text_generation"]["temperature"] == 0.7

    def test_user_overrides_project(self, tmp_path, monkeypatch):
        """Layer 3 > Layer 2."""
        project, home, user, *_ = self._setup_dirs(tmp_path)
        (project / "c.yaml").write_text("k: project")
        (user / "c.yaml").write_text("k: user")
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        config = load_config(config_dir=str(project))
        assert config["k"] == "user"

    def test_rules_overrides_user(self, tmp_path, monkeypatch):
        """Layer 4 > Layer 3."""
        project, home, user, rules, *_ = self._setup_dirs(tmp_path)
        (user / "c.yaml").write_text("k: user")
        (rules / "c.yaml").write_text("k: rules")
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        config = load_config(config_dir=str(project))
        assert config["k"] == "rules"

    def test_env_overrides_rules(self, tmp_path, monkeypatch):
        """Layer 6a (env) > Layer 4 (rules)."""
        project, home, user, rules, *_ = self._setup_dirs(tmp_path)
        (rules / "c.yaml").write_text("k: rules")
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        monkeypatch.setenv("AUTOMEDIA_K", "env")
        config = load_config(config_dir=str(project))
        assert config["k"] == "env"

    def test_overrides_overrides_env(self, tmp_path, monkeypatch):
        """Layer 6b (overrides param) > Layer 6a (env)."""
        project, home, *_ = self._setup_dirs(tmp_path)
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        monkeypatch.setenv("AUTOMEDIA_K", "env")
        config = load_config(config_dir=str(project), overrides={"k": "override"})
        assert config["k"] == "override"

    # -- Missing directories silently skip ------------------------------------

    def test_missing_project_dir_silent(self, tmp_path, monkeypatch):
        """Non-existent project config dir is silently skipped (no exception)."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        config = load_config(config_dir="/nonexistent/project/.automedia")
        assert "llm" in config  # defaults still loaded

    def test_missing_user_dir_silent(self, tmp_path, monkeypatch):
        """Non-existent user config dir is silently skipped."""
        project = tmp_path / "project" / ".automedia"
        project.mkdir(parents=True)
        monkeypatch.setattr(
            os.path,
            "expanduser",
            lambda p: "/nonexistent/home" if p == "~" else p,
        )
        config = load_config(config_dir=str(project))
        assert "llm" in config

    def test_missing_all_dirs_silent(self, monkeypatch):
        """All config dirs missing — only env vars and overrides apply."""
        monkeypatch.setattr(
            os.path,
            "expanduser",
            lambda p: "/nonexistent/home" if p == "~" else p,
        )
        monkeypatch.setattr(os, "getcwd", lambda: "/nonexistent/cwd")
        monkeypatch.setenv("AUTOMEDIA_X", "1")
        config = load_config(overrides={"y": "2"})
        assert config["x"] == "1"
        assert config["y"] == "2"

    # -- Env var mapping tests ------------------------------------------------

    def test_env_var_nested_mapping(self, tmp_path, monkeypatch):
        """AUTOMEDIA_LLM_API_KEY maps to config["llm"]["text_generation"]["api_key"]."""
        project, home, *_ = self._setup_dirs(tmp_path)
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        monkeypatch.setenv("AUTOMEDIA_LLM_API_KEY", "sk-secret")
        config = load_config(config_dir=str(project))
        assert config["llm"]["text_generation"]["api_key"] == "sk-secret"

    def test_env_var_adds_nested_key(self, tmp_path, monkeypatch):
        """Env var creates new nested keys that coexist with defaults."""
        project, home, *_ = self._setup_dirs(tmp_path)
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        monkeypatch.setenv("AUTOMEDIA_LLM_API_KEY", "sk-new")
        config = load_config(config_dir=str(project))
        assert config["llm"]["text_generation"]["api_key"] == "sk-new"
        assert config["llm"]["text_generation"]["model"] == "gpt-4o-mini"

    # -- Full 6-layer merge ---------------------------------------------------

    def test_full_six_layer_merge(self, tmp_path, monkeypatch):
        """All 6 layers contribute; highest priority wins for overlaps."""
        project, home, user, rules, prompts = self._setup_dirs(tmp_path)

        # Layer 2 – project
        (project / "a.yaml").write_text("layer: project\nproject_only: true\n")

        # Layer 3 – user
        (user / "a.yaml").write_text("layer: user\nuser_only: true\n")

        # Layer 4 – rules
        (rules / "a.yaml").write_text("layer: rules\nrules_only: true\n")

        # Layer 5 – prompts
        (prompts / "template.j2").write_text("Hello {{ name }}")

        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)

        # Layer 6a – env
        monkeypatch.setenv("AUTOMEDIA_LAYER", "env")
        monkeypatch.setenv("AUTOMEDIA_ENV_ONLY", "true")

        # Layer 6b – overrides
        overrides = {"layer": "override", "override_only": True}

        config = load_config(config_dir=str(project), overrides=overrides)

        # Highest priority wins for the shared "layer" key
        assert config["layer"] == "override"

        # Each layer's unique key is present
        assert config["project_only"] is True
        assert config["user_only"] is True
        assert config["rules_only"] is True
        assert config["env"]["only"] == "true"
        assert config["override_only"] is True

        # Prompts loaded from layer 5
        assert config["prompts"]["template"] == "Hello {{ name }}"

        # Defaults still present
        assert "llm" in config
        assert config["llm"]["text_generation"]["temperature"] == 0.7

    def test_no_config_dir_uses_cwd(self, tmp_path, monkeypatch):
        """When config_dir is None, $CWD/.automedia/ is used."""
        project = tmp_path / "cwd" / ".automedia"
        project.mkdir(parents=True)
        (project / "c.yaml").write_text("k: from_cwd")
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path / "cwd"))
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        config = load_config()
        assert config["k"] == "from_cwd"

    def test_none_overrides_is_noop(self, tmp_path, monkeypatch):
        """Passing overrides=None does not crash."""
        project, home, *_ = self._setup_dirs(tmp_path)
        monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else p)
        config = load_config(config_dir=str(project), overrides=None)
        assert "llm" in config
