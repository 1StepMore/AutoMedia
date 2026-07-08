"""Integration tests for config_loader — Layer 4 (overrides/rules) and Layer 5 (overrides/prompts).

These tests verify that ``load_config()`` correctly picks up override files from
the ``~/.automedia/overrides/`` directory and merges them with the correct priority.

Layer 4: ``~/.automedia/overrides/rules/*.yaml``  — generic config overrides
Layer 5: ``~/.automedia/overrides/prompts/*.j2``  — Jinja2 prompt templates
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from automedia.core.config_loader import load_config


@pytest.fixture(autouse=True)
def _clear_automedia_env_vars(monkeypatch):
    """Remove AUTOMEDIA_* env vars so override tests are isolated."""
    for k in list(os.environ):
        if k.startswith("AUTOMEDIA_"):
            monkeypatch.delenv(k, raising=False)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_override_dirs(tmp_path: Path):
    """Create the ``~/.automedia/overrides/{rules,prompts}`` layout.

    Returns ``(home_dir, rules_dir, prompts_dir)``.
    """
    home = tmp_path / "home"
    user = home / ".automedia"
    user.mkdir(parents=True)
    rules = user / "overrides" / "rules"
    rules.mkdir(parents=True)
    prompts = user / "overrides" / "prompts"
    prompts.mkdir(parents=True)
    return home, rules, prompts


def _patch_home(monkeypatch, home: Path):
    """Redirect ``os.path.expanduser("~")`` to *home*."""
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(home) if p == "~" else p
    )


# ---------------------------------------------------------------------------
# Layer 4 — overrides/rules/*.yaml
# ---------------------------------------------------------------------------


class TestLayer4Rules:
    """Override rules loaded from ``~/.automedia/overrides/rules/*.yaml``."""

    def test_rules_override_builtin_defaults(self, tmp_path, monkeypatch):
        """Layer 4 YAML overrides built-in defaults (Layer 1)."""
        home, rules, _ = _setup_override_dirs(tmp_path)
        (rules / "brand_a.yaml").write_text(
            "content:\n"
            "  default_tone: enthusiastic\n"
            "  default_language: en\n"
        )
        _patch_home(monkeypatch, home)

        config = load_config()

        # Overridden by the rule
        assert config["content"]["default_tone"] == "enthusiastic"
        assert config["content"]["default_language"] == "en"
        # Still inherited from defaults.yaml
        assert config["content"]["min_title_length"] == 10
        assert config["content"]["max_title_length"] == 100

    def test_brand_profile_in_rules(self, tmp_path, monkeypatch):
        """Brand-scoped settings in rule files appear in the merged config."""
        home, rules, _ = _setup_override_dirs(tmp_path)
        (rules / "brand_acme.yaml").write_text(
            "brand:\n"
            "  name: Acme\n"
            "  tone: professional\n"
            "  language: en\n"
            "  cta_principles:\n"
            "    - Sign up now\n"
            "    - Free trial\n"
        )
        _patch_home(monkeypatch, home)

        config = load_config()

        assert config["brand"]["name"] == "Acme"
        assert config["brand"]["tone"] == "professional"
        assert config["brand"]["language"] == "en"
        assert config["brand"]["cta_principles"] == ["Sign up now", "Free trial"]

    def test_multiple_rule_files_merge(self, tmp_path, monkeypatch):
        """Multiple YAML files in overrides/rules/ are deep-merged together."""
        home, rules, _ = _setup_override_dirs(tmp_path)
        (rules / "brand_a.yaml").write_text("brand_a:\n  key: a_value\n")
        (rules / "brand_b.yaml").write_text("brand_b:\n  key: b_value\n")
        _patch_home(monkeypatch, home)

        config = load_config()

        assert config["brand_a"]["key"] == "a_value"
        assert config["brand_b"]["key"] == "b_value"

    def test_conflicting_rules_alphabetical_order_wins(self, tmp_path, monkeypatch):
        """When two rule files set the same key, the later-sorted file wins."""
        home, rules, _ = _setup_override_dirs(tmp_path)
        (rules / "b_second.yaml").write_text("shared_key: from_b")
        (rules / "a_first.yaml").write_text("shared_key: from_a")
        _patch_home(monkeypatch, home)

        config = load_config()

        # b_second.yaml processed after a_first.yaml → its value wins
        assert config["shared_key"] == "from_b"

    def test_rules_deep_merge_with_defaults(self, tmp_path, monkeypatch):
        """Rule file keys are deep-merged with defaults, not a wholesale replace."""
        home, rules, _ = _setup_override_dirs(tmp_path)
        (rules / "llm_override.yaml").write_text(
            "llm:\n  text_generation:\n    temperature: 0.9\n"
        )
        _patch_home(monkeypatch, home)

        config = load_config()

        # Overridden value
        assert config["llm"]["text_generation"]["temperature"] == 0.9
        # Other sub-keys of text_generation should still come from defaults
        assert config["llm"]["text_generation"]["model"] == "gpt-4o-mini"
        assert config["llm"]["text_generation"]["max_tokens"] == 2048

    def test_missing_rules_dir_silently_skipped(self, tmp_path, monkeypatch):
        """No exception when overrides/rules/ does not exist."""
        home = tmp_path / "home"
        (home / ".automedia").mkdir(parents=True)
        _patch_home(monkeypatch, home)

        config = load_config()

        assert "llm" in config  # defaults still present

    def test_empty_rules_dir_no_effect(self, tmp_path, monkeypatch):
        """An empty overrides/rules/ directory adds nothing to the config."""
        home, rules, _ = _setup_override_dirs(tmp_path)
        # rules dir exists but is empty
        _patch_home(monkeypatch, home)

        config = load_config()

        assert "llm" in config
        # No unexpected keys from empty dir
        assert "rules_only" not in config


# ---------------------------------------------------------------------------
# Layer 5 — overrides/prompts/*.j2
# ---------------------------------------------------------------------------


class TestLayer5Prompts:
    """Prompt templates loaded from ``~/.automedia/overrides/prompts/*.j2``."""

    def test_prompts_loaded_under_prompts_key(self, tmp_path, monkeypatch):
        """J2 template files appear under config['prompts'] after load_config()."""
        home, _, prompts = _setup_override_dirs(tmp_path)
        (prompts / "system.j2").write_text(
            "You are a helpful assistant for {{ brand_name }}."
        )
        (prompts / "user.j2").write_text(
            "Translate the following to {{ language }}: {{ content }}"
        )
        _patch_home(monkeypatch, home)

        config = load_config()

        assert "prompts" in config
        assert (
            config["prompts"]["system"]
            == "You are a helpful assistant for {{ brand_name }}."
        )
        assert (
            config["prompts"]["user"]
            == "Translate the following to {{ language }}: {{ content }}"
        )

    def test_prompts_maintain_sorted_order(self, tmp_path, monkeypatch):
        """Prompt keys appear in alphabetical filename order."""
        home, _, prompts = _setup_override_dirs(tmp_path)
        (prompts / "z_last.j2").write_text("last")
        (prompts / "a_first.j2").write_text("first")
        (prompts / "m_middle.j2").write_text("middle")
        _patch_home(monkeypatch, home)

        config = load_config()

        keys = list(config["prompts"].keys())
        assert keys == ["a_first", "m_middle", "z_last"]

    def test_non_j2_files_ignored_in_prompts(self, tmp_path, monkeypatch):
        """Only *.j2 files are loaded; .txt, .yaml etc. are skipped."""
        home, _, prompts = _setup_override_dirs(tmp_path)
        (prompts / "valid.j2").write_text("prompt content")
        (prompts / "notes.txt").write_text("ignored")
        (prompts / "config.yaml").write_text("also: ignored")
        _patch_home(monkeypatch, home)

        config = load_config()

        assert "prompts" in config
        assert "valid" in config["prompts"]
        assert "notes" not in config["prompts"]
        assert "config" not in config["prompts"]

    def test_prompts_do_not_affect_other_config_keys(self, tmp_path, monkeypatch):
        """Layer 5 data is confined to the 'prompts' sub-dict."""
        home, _, prompts = _setup_override_dirs(tmp_path)
        (prompts / "system.j2").write_text("system prompt")
        _patch_home(monkeypatch, home)

        config = load_config()

        assert config["prompts"]["system"] == "system prompt"
        # Core config values are untouched
        assert config["llm"]["text_generation"]["provider"] == "openai"
        assert config["content"]["default_tone"] == "neutral"

    def test_missing_prompts_dir_silently_skipped(self, tmp_path, monkeypatch):
        """No exception when overrides/prompts/ does not exist."""
        home = tmp_path / "home"
        (home / ".automedia").mkdir(parents=True)
        _patch_home(monkeypatch, home)

        config = load_config()

        assert "prompts" not in config
        assert "llm" in config

    def test_empty_prompts_dir_no_prompts_key(self, tmp_path, monkeypatch):
        """An empty overrides/prompts/ directory produces no 'prompts' key."""
        home, _, prompts = _setup_override_dirs(tmp_path)
        # prompts dir exists but is empty
        _patch_home(monkeypatch, home)

        config = load_config()

        assert "prompts" not in config


# ---------------------------------------------------------------------------
# Combined — Layer 4 + Layer 5 together
# ---------------------------------------------------------------------------


class TestLayers4And5Combined:
    """Interaction between rule overrides and prompt overrides."""

    def test_rules_and_prompts_coexist(self, tmp_path, monkeypatch):
        """Both Layer 4 and Layer 5 data appear in the same merged config."""
        home, rules, prompts = _setup_override_dirs(tmp_path)
        (rules / "settings.yaml").write_text("theme: dark\n")
        (prompts / "system.j2").write_text("System: {{ theme }}")
        _patch_home(monkeypatch, home)

        config = load_config()

        assert config["theme"] == "dark"
        assert config["prompts"]["system"] == "System: {{ theme }}"

    def test_prompts_under_user_still_merged(self, tmp_path, monkeypatch):
        """User-level prompts dir (~/.automedia/prompts/ if any) also works."""
        home, rules, prompts = _setup_override_dirs(tmp_path)
        # Also create a user-level prompts dir (Layer 3 style)
        user_prompts = home / ".automedia" / "prompts"
        user_prompts.mkdir(exist_ok=True)
        (user_prompts / "greeting.j2").write_text("Hello")
        # Override with a more specific prompt (Layer 5)
        (prompts / "greeting.j2").write_text("Override Hello")
        _patch_home(monkeypatch, home)

        config = load_config()

        # Layer 5 wins over Layer 3 for prompts
        assert config.get("prompts", {}).get("greeting") == "Override Hello"


# ---------------------------------------------------------------------------
# Override priority — Layer 4 / Layer 5 ordering in the 6-layer chain
# ---------------------------------------------------------------------------


class TestOverridePriority:
    """Verify that Layer 4 and Layer 5 are positioned correctly in the priority chain.

    Priority (lowest → highest):
        1. Built-in defaults.yaml
        2. Project .automedia/
        3. User ~/.automedia/
        4. ~/.automedia/overrides/rules/*.yaml   ◄── Layer 4
        5. ~/.automedia/overrides/prompts/*.j2    ◄── Layer 5
        6a. AUTOMEDIA_* env vars
        6b. explicit overrides parameter
    """

    def _setup_all_layers(
        self, tmp_path: Path,
    ) -> tuple[Path, Path, Path, Path, Path]:
        """Create directories for all 5 file-based layers.

        Returns ``(home, project_dir, user_dir, rules_dir, prompts_dir)``.
        """
        home = tmp_path / "home"
        user = home / ".automedia"
        user.mkdir(parents=True)
        project = tmp_path / "project" / ".automedia"
        project.mkdir(parents=True)
        rules = user / "overrides" / "rules"
        rules.mkdir(parents=True)
        prompts = user / "overrides" / "prompts"
        prompts.mkdir(parents=True)
        return home, project, user, rules, prompts

    def test_layer4_overrides_layer3(self, tmp_path, monkeypatch):
        """Layer 4 (rules) wins over Layer 3 (user ~/.automedia/)."""
        home, project, user, rules, _ = self._setup_all_layers(tmp_path)
        (user / "settings.yaml").write_text("key: user_value")
        (rules / "override.yaml").write_text("key: rules_value")
        _patch_home(monkeypatch, home)

        config = load_config(config_dir=str(project))

        assert config["key"] == "rules_value"

    def test_layer4_overrides_layer2(self, tmp_path, monkeypatch):
        """Layer 4 (rules) wins over Layer 2 (project .automedia/)."""
        home, project, user, rules, _ = self._setup_all_layers(tmp_path)
        (project / "settings.yaml").write_text("key: project_value")
        (rules / "override.yaml").write_text("key: rules_value")
        _patch_home(monkeypatch, home)

        config = load_config(config_dir=str(project))

        assert config["key"] == "rules_value"

    def test_full_priority_chain(self, tmp_path, monkeypatch):
        """All file layers present: Layer 4 value propagates to final config."""
        home, project, user, rules, prompts = self._setup_all_layers(tmp_path)

        # Layer 1 – built-in defaults (content.default_tone = neutral)
        # Layer 2
        (project / "p.yaml").write_text(
            "llm:\n  text_generation:\n    model: gpt-4\n"
        )
        # Layer 3 — different key so no conflict with rules
        (user / "u.yaml").write_text("user_custom: true\n")
        # Layer 4
        (rules / "r.yaml").write_text(
            "content:\n  default_tone: enthusiastic\n"
        )
        # Layer 5
        (prompts / "system.j2").write_text("Custom system prompt.")

        _patch_home(monkeypatch, home)

        config = load_config(config_dir=str(project))

        # Layer 1 — defaults still present for un-overridden keys
        assert config["llm"]["text_generation"]["temperature"] == 0.7
        # Layer 2 — project value
        assert config["llm"]["text_generation"]["model"] == "gpt-4"
        # Layer 3 — user value
        assert config["user_custom"] is True
        # Layer 4 — rules override default
        assert config["content"]["default_tone"] == "enthusiastic"
        # Layer 5 — prompts loaded
        assert config["prompts"]["system"] == "Custom system prompt."
