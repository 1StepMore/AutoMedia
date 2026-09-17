"""Tests for automedia.manifests.brand_profile_schema — BrandProfile dataclass."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

from automedia.adapters.registry import AdapterRegistry
from automedia.manifests import brand_profile_schema as schema
from automedia.manifests.brand_profile_schema import (
    BrandProfile,
    load_brand_profile,
    validate_brand_profile,
)

# ---------------------------------------------------------------------------
# validate_brand_profile
# ---------------------------------------------------------------------------


class TestValidateBrandProfile:
    """Unit tests for the brand-profile validation function."""

    def test_valid_minimal(self) -> None:
        assert validate_brand_profile({"brand_name": "Acme"}) is True

    def test_valid_full(self) -> None:
        data = {
            "brand_name": "TestBrand",
            "aliases": ["TB"],
            "cta_principles": ["Be clear"],
            "blocked_words": ["spam"],
            "tone_guidelines": "Professional",
            "brand_identity": "AI startup",
            "languages": {"zh": {"locale": "zh-CN"}},
        }
        assert validate_brand_profile(data) is True

    def test_missing_brand_name(self) -> None:
        assert validate_brand_profile({"aliases": ["TB"]}) is False

    def test_empty_brand_name(self) -> None:
        assert validate_brand_profile({"brand_name": ""}) is False

    def test_whitespace_only_brand_name(self) -> None:
        assert validate_brand_profile({"brand_name": "   "}) is False

    def test_non_string_brand_name(self) -> None:
        assert validate_brand_profile({"brand_name": 42}) is False

    def test_not_a_dict(self) -> None:
        assert validate_brand_profile("not a dict") is False
        assert validate_brand_profile(None) is False
        assert validate_brand_profile([1, 2]) is False

    def test_extra_keys_ignored(self) -> None:
        assert validate_brand_profile({"brand_name": "X", "unknown": True}) is True


# ---------------------------------------------------------------------------
# load_brand_profile
# ---------------------------------------------------------------------------


class TestLoadBrandProfile:
    """Unit tests for loading brand-profile.yaml files."""

    def _write_profile(
        self,
        tmp_path: Path,
        data: dict[str, Any],
        name: str = "brand-profile.yaml",
    ) -> str:
        p = tmp_path / name
        p.write_text(yaml.dump(data), encoding="utf-8")
        return str(p)

    def test_loads_full_profile(self, tmp_path: Path) -> None:
        data = {
            "brand_name": "TestBrand",
            "aliases": ["TB", "Test B"],
            "cta_principles": ["Include CTA", "Link to demo"],
            "blocked_words": ["spam", "scam"],
            "tone_guidelines": "Professional yet friendly",
            "brand_identity": "AI内容生产",
            "languages": {"zh": {"locale": "zh-CN", "default": True}},
        }
        path = self._write_profile(tmp_path, data)
        bp = load_brand_profile(path)

        assert bp.brand_name == "TestBrand"
        assert bp.aliases == ["TB", "Test B"]
        assert bp.cta_principles == ["Include CTA", "Link to demo"]
        assert bp.blocked_words == ["spam", "scam"]
        assert bp.tone_guidelines == "Professional yet friendly"
        assert bp.brand_identity == "AI内容生产"
        assert bp.languages == {"zh": {"locale": "zh-CN", "default": True}}

    def test_loads_minimal_profile(self, tmp_path: Path) -> None:
        path = self._write_profile(tmp_path, {"brand_name": "Acme"})
        bp = load_brand_profile(path)

        assert bp.brand_name == "Acme"
        assert bp.aliases == []
        assert bp.cta_principles == []
        assert bp.blocked_words == []
        assert bp.tone_guidelines == ""
        assert bp.brand_identity == ""
        assert bp.languages == {}

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Brand profile not found"):
            load_brand_profile(str(tmp_path / "nope.yaml"))

    def test_non_dict_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_brand_profile(str(p))

    def test_empty_brand_name_raises(self, tmp_path: Path) -> None:
        path = self._write_profile(tmp_path, {"brand_name": ""})
        with pytest.raises(ValueError, match="validation failed"):
            load_brand_profile(str(path))

    def test_partial_optional_fields(self, tmp_path: Path) -> None:
        data = {"brand_name": "Partial", "blocked_words": ["bad"]}
        path = self._write_profile(tmp_path, data)
        bp = load_brand_profile(path)

        assert bp.brand_name == "Partial"
        assert bp.blocked_words == ["bad"]
        assert bp.aliases == []
        assert bp.tone_guidelines == ""


# ---------------------------------------------------------------------------
# BrandProfile dataclass
# ---------------------------------------------------------------------------


class TestBrandProfileDefaults:
    """Verify dataclass defaults are safe."""

    def test_default_construction(self) -> None:
        bp = BrandProfile()
        assert bp.brand_name == ""
        assert bp.aliases == []
        assert bp.cta_principles == []
        assert bp.blocked_words == []
        assert bp.tone_guidelines == ""
        assert bp.brand_identity == ""
        assert bp.languages == {}

    def test_lists_are_independent(self) -> None:
        bp1 = BrandProfile()
        bp2 = BrandProfile()
        bp1.aliases.append("X")
        assert "X" not in bp2.aliases

    def test_languages_dict_is_independent(self) -> None:
        bp1 = BrandProfile()
        bp2 = BrandProfile()
        bp1.languages["en"] = {"locale": "en-US"}
        assert "en" not in bp2.languages


# ---------------------------------------------------------------------------
# Exception-narrowing guard tests (pareto-hardening todo 4)
# ---------------------------------------------------------------------------


def _raise_import_error() -> list[str]:
    raise ImportError("registry import failed")


def _raise_attribute_error() -> list[str]:
    raise AttributeError("registry has no list")


def _raise_type_error(*args: object, **kwargs: object) -> list[str]:
    raise TypeError("unexpected failure")


def _raise_os_error(*args: object, **kwargs: object) -> object:
    raise OSError("disk failure")


def _raise_yaml_error(*args: object, **kwargs: object) -> object:
    raise yaml.YAMLError("malformed yaml")


class TestExceptionNarrowingGuards:
    """The three narrowed handlers must keep their fallback for listed exceptions.

    Each handler wraps a different failure surface, so each guard proves:
    (a) a *listed* exception still yields the original fallback value, and
    (b) an *unlisted* exception is no longer swallowed (it propagates).
    """

    _FALLBACK_PLATFORMS: ClassVar[set[str]] = {"wechat", "zhihu", "xiaohongshu", "feishu"}

    # -- _get_registered_platform_names (ex line 128) ----------------------

    def test_registry_import_error_falls_back_to_hardcoded_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(AdapterRegistry, "list", _raise_import_error)
        assert schema._get_registered_platform_names() == self._FALLBACK_PLATFORMS

    def test_registry_attribute_error_falls_back_to_hardcoded_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(AdapterRegistry, "list", _raise_attribute_error)
        assert schema._get_registered_platform_names() == self._FALLBACK_PLATFORMS

    def test_registry_unlisted_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(AdapterRegistry, "list", _raise_type_error)
        with pytest.raises(TypeError, match="unexpected failure"):
            schema._get_registered_platform_names()

    # -- load_brand_profiles (ex line 267) ---------------------------------

    def test_load_brand_profiles_yaml_error_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile_file = tmp_path / "brand_profiles.yaml"
        profile_file.write_text("acme:\n  brand_name: Acme\n", encoding="utf-8")
        monkeypatch.setattr(schema, "_BRAND_PROFILES_PATH", profile_file)
        monkeypatch.setattr(yaml, "safe_load", _raise_yaml_error)

        assert schema.load_brand_profiles() == {}

    def test_load_brand_profiles_os_error_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile_file = tmp_path / "brand_profiles.yaml"
        profile_file.write_text("acme:\n  brand_name: Acme\n", encoding="utf-8")
        monkeypatch.setattr(schema, "_BRAND_PROFILES_PATH", profile_file)
        monkeypatch.setattr(yaml, "safe_load", _raise_os_error)

        assert schema.load_brand_profiles() == {}

    def test_load_brand_profiles_unlisted_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile_file = tmp_path / "brand_profiles.yaml"
        profile_file.write_text("acme:\n  brand_name: Acme\n", encoding="utf-8")
        monkeypatch.setattr(schema, "_BRAND_PROFILES_PATH", profile_file)
        monkeypatch.setattr(yaml, "safe_load", _raise_type_error)

        with pytest.raises(TypeError, match="unexpected failure"):
            schema.load_brand_profiles()

    # -- save_brand_profile existing-read (ex line 328) --------------------

    def test_save_brand_profile_yaml_error_rebuilds_from_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile_file = tmp_path / "brand_profiles.yaml"
        profile_file.write_text("old:\n  brand_name: Old\n", encoding="utf-8")
        monkeypatch.setattr(schema, "_BRAND_PROFILES_PATH", profile_file)
        real_safe_load = yaml.safe_load
        monkeypatch.setattr(yaml, "safe_load", _raise_yaml_error)

        schema.save_brand_profile("new", {"brand_name": "New"})

        written = real_safe_load(profile_file.read_text(encoding="utf-8"))
        # The failed existing read is discarded (fallback ``existing = {}``),
        # so only the newly saved profile is present.
        assert written == {"new": {"brand_name": "New"}}

    def test_save_brand_profile_os_error_rebuilds_from_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile_file = tmp_path / "brand_profiles.yaml"
        profile_file.write_text("old:\n  brand_name: Old\n", encoding="utf-8")
        monkeypatch.setattr(schema, "_BRAND_PROFILES_PATH", profile_file)
        real_safe_load = yaml.safe_load
        monkeypatch.setattr(yaml, "safe_load", _raise_os_error)

        schema.save_brand_profile("new", {"brand_name": "New"})

        written = real_safe_load(profile_file.read_text(encoding="utf-8"))
        assert written == {"new": {"brand_name": "New"}}

    def test_save_brand_profile_unlisted_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile_file = tmp_path / "brand_profiles.yaml"
        profile_file.write_text("old:\n  brand_name: Old\n", encoding="utf-8")
        monkeypatch.setattr(schema, "_BRAND_PROFILES_PATH", profile_file)
        monkeypatch.setattr(yaml, "safe_load", _raise_type_error)

        with pytest.raises(TypeError, match="unexpected failure"):
            schema.save_brand_profile("new", {"brand_name": "New"})
