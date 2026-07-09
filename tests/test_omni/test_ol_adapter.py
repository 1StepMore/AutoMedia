"""Tests for OLAdapter."""

from __future__ import annotations

import inspect
import typing

import pytest

from automedia.omni.ol_adapter import OLAdapter, TranslationResult


class TestTranslationResult:
    def test_has_all_fields(self) -> None:
        r = TranslationResult(
            translated_md="# Bonjour",
            xliff_path="/tmp/translated.xlf",
            warnings=["low quality"],
        )
        assert r.translated_md == "# Bonjour"
        assert r.xliff_path == "/tmp/translated.xlf"
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

    def test_ol_adapter_validate_env_returns_false_without_env(self) -> None:
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

    def test_init_default_config_path(self) -> None:
        adapter = OLAdapter()
        assert adapter.config_path == "ol_config.yaml"

    def test_judge_returns_stub(self) -> None:
        adapter = OLAdapter()
        result = adapter.judge("any text")
        assert isinstance(result, dict)
        assert result["score"] == 1.0
        assert "feedback" in result

    def test_translate_returns_translation_result(self) -> None:
        adapter = OLAdapter()
        assert callable(adapter.translate)
        hints = typing.get_type_hints(adapter.translate)
        assert hints["return"] is TranslationResult


def test_translate_graceful_on_missing_config() -> None:
    """translate() returns TranslationResult with warning instead of crashing."""
    adapter = OLAdapter()
    import os
    # Ensure OL_CONFIG_PATH points to a non-existent file
    bad_path = "/tmp/nonexistent_ol_config.yaml"
    os.environ["OL_CONFIG_PATH"] = bad_path
    try:
        result = adapter.translate("# Hello", source_lang="en", target_lang="zh")
        assert isinstance(result, TranslationResult)
        assert result.translated_md == ""
        assert len(result.warnings) > 0
        assert "Config not found" in result.warnings[0]
    finally:
        del os.environ["OL_CONFIG_PATH"]
