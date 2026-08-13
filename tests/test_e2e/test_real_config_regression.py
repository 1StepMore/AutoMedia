"""Regression test: loads sanitized real-style config files across all 6
layers and verifies the merged output matches expectations.

This test locks the 6-layer merge behaviour with realistic fixture structure
so that future changes (PRD-1 M4) do not break configuration merging.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from automedia.core.config_loader import load_config

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "real_config"

# Expected top-level config keys — no others should leak into the merged dict.
_ALLOWLIST = {
    "project",
    "paths",
    "llm",
    "content",
    "platforms",
    "cron",
    "engines",
    "pool",
    "pipeline",
    "prompts",
    "brand",
    "gate_engine",
}


# ---------------------------------------------------------------------------
# Isolation fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_automedia_env_vars(monkeypatch):
    """Remove AUTOMEDIA_* env vars loaded from .env so config tests are isolated."""
    original = {k: v for k, v in os.environ.items() if k.startswith("AUTOMEDIA_")}
    for k in original:
        monkeypatch.delenv(k, raising=False)
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRealConfigRegression:
    """Regression tests using realistic config files across all 6 layers."""

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _setup_layers(self, tmp_path: Path):
        """Populate temp directories with fixture config files for all 6 layers.

        Returns ``(project_dir, home_dir)`` so the caller can monkeypatch
        ``expanduser`` and pass ``config_dir`` to ``load_config``.
        """
        # Layer 2 — project directory    (config_dir)
        project_dir = tmp_path / "project" / ".automedia"
        project_dir.mkdir(parents=True)
        shutil.copy2(
            FIXTURE_DIR / "project_config.yaml",
            project_dir / "project_config.yaml",
        )

        # Layers 3-5 — user home directory  (~/.automedia/)
        home_dir = tmp_path / "home"
        user_dir = home_dir / ".automedia"
        user_dir.mkdir(parents=True)

        # Layer 3 — user-level files
        shutil.copy2(
            FIXTURE_DIR / "user" / "model_config.yaml",
            user_dir / "model_config.yaml",
        )
        shutil.copy2(
            FIXTURE_DIR / "user" / "brand_profile.yaml",
            user_dir / "brand_profile.yaml",
        )

        # Layer 4 — override rules
        rules_dir = user_dir / "overrides" / "rules"
        rules_dir.mkdir(parents=True)
        shutil.copy2(
            FIXTURE_DIR / "user" / "overrides" / "rules" / "01-content-rules.yaml",
            rules_dir / "01-content-rules.yaml",
        )

        # Layer 5 — override prompts
        prompts_dir = user_dir / "overrides" / "prompts"
        prompts_dir.mkdir(parents=True)
        shutil.copy2(
            FIXTURE_DIR / "user" / "overrides" / "prompts" / "system.j2",
            prompts_dir / "system.j2",
        )

        return project_dir, home_dir

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_all_six_layers_merge_correctly(self, tmp_path, monkeypatch):
        """All 6 layers merge; highest priority wins for overlapping keys."""
        project_dir, home_dir = self._setup_layers(tmp_path)

        monkeypatch.setattr(
            os.path,
            "expanduser",
            lambda p: str(home_dir) if p == "~" else p,
        )

        # Layer 6a — environment variable (special remapped LLM key)
        monkeypatch.setenv("AUTOMEDIA_LLM_TEMPERATURE", "0.1")

        # Layer 6b — explicit overrides param (highest priority)
        overrides = {"project": {"name": "OverrideName"}}

        config = load_config(config_dir=str(project_dir), overrides=overrides)

        # ── Layer 1 — Built-in defaults (preserved when not overridden) ──
        assert config["cron"]["enabled"] is True
        assert config["pool"]["retention_days"] == 7
        assert config["pipeline"]["video"]["enabled"] is True
        # Platform not touched by any override
        assert config["platforms"]["zhihu"]["enabled"] is False

        # ── Layer 2 — Project overrides defaults ────────────────────────
        assert config["project"]["version"] == "2.0.0-test"
        assert config["paths"]["data_dir"] == "/tmp/regression-data"
        assert config["paths"]["output_dir"] == "/tmp/regression-output"

        # ── Layer 3 — User overrides project ────────────────────────────
        assert config["llm"]["text_generation"]["model"] == "claude-3-opus"
        assert config["llm"]["text_generation"]["max_tokens"] == 4096
        assert config["content"]["default_language"] == "en"
        assert config["brand"]["name"] == "RegressionBrand"

        # ── Layer 4 — Override rules over user ──────────────────────────
        assert config["content"]["default_tone"] == "casual"
        assert config["content"]["min_title_length"] == 15
        assert config["platforms"]["wechat"]["enabled"] is True

        # ── Layer 5 — Override prompts ──────────────────────────────────
        assert "system" in config["prompts"]
        assert "{{ brand.name }}" in config["prompts"]["system"]
        assert "{{ content.default_tone }}" in config["prompts"]["system"]

        # ── Layer 6a — Environment variable ─────────────────────────────
        # AUTOMEDIA_LLM_TEMPERATURE is remapped to llm.text_generation.temperature
        assert config["llm"]["text_generation"]["temperature"] == 0.1

        # ── Layer 6b — Overrides param (highest priority) ───────────────
        assert config["project"]["name"] == "OverrideName"

    def test_no_unexpected_top_level_keys(self, tmp_path, monkeypatch):
        """Only known top-level keys appear in the merged config."""
        project_dir, home_dir = self._setup_layers(tmp_path)

        monkeypatch.setattr(
            os.path,
            "expanduser",
            lambda p: str(home_dir) if p == "~" else p,
        )

        config = load_config(config_dir=str(project_dir))

        actual_keys = set(config.keys())
        unexpected = actual_keys - _ALLOWLIST
        assert not unexpected, f"Unexpected top-level keys found: {unexpected}"

    def test_override_precedence_chain(self, tmp_path, monkeypatch):
        """Each layer correctly overrides the previous for the same key."""
        project_dir, home_dir = self._setup_layers(tmp_path)

        monkeypatch.setattr(
            os.path,
            "expanduser",
            lambda p: str(home_dir) if p == "~" else p,
        )

        #
        # Verify the chain for `content.default_tone`:
        #   default("neutral", L1) → user("professional", L3) → rules("casual", L4)
        #
        config = load_config(config_dir=str(project_dir))
        assert config["content"]["default_tone"] == "casual"

        #
        # Verify the chain for `llm.text_generation.model`:
        #   default("gpt-4o-mini", L1) → project("gpt-4", L2) → user("claude-3-opus", L3)
        #
        assert config["llm"]["text_generation"]["model"] == "claude-3-opus"

        #
        # Verify the full L1→L6 chain for `llm.text_generation.temperature`:
        #   default(0.7) → project(0.5) → env(0.1, L6a) → overrides(0.01, L6b)
        #
        monkeypatch.setenv("AUTOMEDIA_LLM_TEMPERATURE", "0.1")
        config2 = load_config(
            config_dir=str(project_dir),
            overrides={
                "llm": {"text_generation": {"temperature": 0.01}},
            },
        )
        assert config2["llm"]["text_generation"]["temperature"] == 0.01
