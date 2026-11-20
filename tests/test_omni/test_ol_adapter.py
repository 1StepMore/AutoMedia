"""Tests for OLAdapter."""

from __future__ import annotations

import typing
from typing import Any

from automedia.omni.ol_adapter import (
    OLAdapter,
    TranslationResult,
    resolve_config_path,
    stamp_translation_frontmatter,
)


class TestTranslationResult:
    def test_has_all_fields(self, tmp_path: Any) -> None:
        xliff = str(tmp_path / "translated.xlf")
        r = TranslationResult(
            translated_md="# Bonjour",
            xliff_path=xliff,
            warnings=["low quality"],
        )
        assert r.translated_md == "# Bonjour"
        assert r.xliff_path == xliff
        assert r.warnings == ["low quality"]

    def test_xliff_path_defaults_to_none(self) -> None:
        r = TranslationResult(translated_md="# Bonjour", warnings=[])
        assert r.xliff_path is None

    def test_warnings_defaults_to_empty_list(self) -> None:
        r = TranslationResult(translated_md="# Bonjour")
        assert r.warnings == []


class TestOLAdapterContract:
    def test_ol_adapter_name_returns_ol(self) -> None:
        adapter = OLAdapter()
        assert adapter.name == "ol"

    def test_ol_adapter_validate_env_returns_false_without_env(self, monkeypatch: Any) -> None:
        # Explicit isolation (#518): a leaked MCP_ALLOWED_DIRECTORIES (set in
        # the surrounding environment or by another test) flips validate_env()
        # to True and breaks this absence-assertion in full-suite runs.
        monkeypatch.delenv("MCP_ALLOWED_DIRECTORIES", raising=False)
        adapter = OLAdapter()
        assert adapter.validate_env() is False

    def test_ol_adapter_translate_exists_and_callable(self) -> None:
        adapter = OLAdapter()
        assert callable(adapter.translate)

    def test_ol_adapter_translate_graceful_without_env(self) -> None:
        adapter = OLAdapter()
        result = adapter.translate("hello")
        assert isinstance(result, TranslationResult)
        assert result.translated_md == ""
        assert len(result.warnings) > 0

    def test_init_stores_config_path(self) -> None:
        adapter = OLAdapter(config_path="my.yaml")
        assert adapter.config_path == "my.yaml"

    def test_init_default_config_path(self, tmp_path: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AUTOMEDIA_OL_CONFIG", raising=False)
        adapter = OLAdapter()
        assert adapter.config_path == ""

    def test_translate_returns_translation_result(self) -> None:
        adapter = OLAdapter()
        assert callable(adapter.translate)
        hints = typing.get_type_hints(adapter.translate)
        assert hints["return"] is TranslationResult


def test_translate_graceful_on_missing_config(tmp_path: Any) -> None:
    """translate() returns TranslationResult with warning instead of crashing."""
    adapter = OLAdapter()
    import os

    # Ensure OL_CONFIG_PATH points to a non-existent file
    bad_path = str(tmp_path / "nonexistent_ol_config.yaml")
    os.environ["OL_CONFIG_PATH"] = bad_path
    try:
        result = adapter.translate("# Hello", source_lang="en", target_lang="zh")
        assert isinstance(result, TranslationResult)
        assert result.translated_md == ""
        assert len(result.warnings) > 0
        assert "Config not found" in result.warnings[0]
    finally:
        del os.environ["OL_CONFIG_PATH"]


def test_resolve_config_path_precedence(tmp_path: Any, monkeypatch: Any) -> None:
    """explicit > AUTOMEDIA_OL_CONFIG > cwd > ~/.automedia/omni > None."""
    home = tmp_path / "home"
    work = tmp_path / "work"
    (home / ".automedia" / "omni").mkdir(parents=True)
    work.mkdir()

    explicit = tmp_path / "explicit.yaml"
    from_env = tmp_path / "env.yaml"
    cwd_config = work / "ol_config.yaml"
    home_config = home / ".automedia" / "omni" / "ol_config.yaml"
    for path in (explicit, from_env, cwd_config, home_config):
        path.write_text("source_lang: zh\n", encoding="utf-8")

    monkeypatch.delenv("AUTOMEDIA_OL_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)

    assert resolve_config_path(str(explicit)) == str(explicit)

    monkeypatch.setenv("AUTOMEDIA_OL_CONFIG", str(from_env))
    assert resolve_config_path() == str(from_env)

    monkeypatch.delenv("AUTOMEDIA_OL_CONFIG")
    assert resolve_config_path() == str(cwd_config)

    cwd_config.unlink()
    assert resolve_config_path() == str(home_config)

    home_config.unlink()
    assert resolve_config_path() is None


def test_stamp_frontmatter_adds_and_overwrites() -> None:
    """Missing frontmatter is prepended; existing keys are preserved/overwritten."""
    assert (
        stamp_translation_frontmatter("# Body", "zh", "en")
        == "---\nsource_lang: zh\ntarget_lang: en\n---\n\n# Body"
    )

    existing = "---\nsource_lang: fr\ntarget_lang: de\ntitle: Hello\n---\n# Body\n"
    stamped = stamp_translation_frontmatter(existing, "zh", "en")
    assert stamped.startswith("---\n")
    assert "source_lang: zh" in stamped
    assert "target_lang: en" in stamped
    assert "title: Hello" in stamped
    assert "# Body" in stamped

    assert stamp_translation_frontmatter("", "zh", "en") == ""
    assert stamp_translation_frontmatter("   \n", "zh", "en") == "   \n"
