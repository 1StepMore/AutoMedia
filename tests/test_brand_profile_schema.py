"""Tests for automedia.manifests.brand_profile_schema — BrandProfile dataclass."""

from __future__ import annotations

import pytest
import yaml

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

    def test_valid_minimal(self):
        assert validate_brand_profile({"brand_name": "Acme"}) is True

    def test_valid_full(self):
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

    def test_missing_brand_name(self):
        assert validate_brand_profile({"aliases": ["TB"]}) is False

    def test_empty_brand_name(self):
        assert validate_brand_profile({"brand_name": ""}) is False

    def test_whitespace_only_brand_name(self):
        assert validate_brand_profile({"brand_name": "   "}) is False

    def test_non_string_brand_name(self):
        assert validate_brand_profile({"brand_name": 42}) is False

    def test_not_a_dict(self):
        assert validate_brand_profile("not a dict") is False
        assert validate_brand_profile(None) is False
        assert validate_brand_profile([1, 2]) is False

    def test_extra_keys_ignored(self):
        assert validate_brand_profile({"brand_name": "X", "unknown": True}) is True


# ---------------------------------------------------------------------------
# load_brand_profile
# ---------------------------------------------------------------------------


class TestLoadBrandProfile:
    """Unit tests for loading brand-profile.yaml files."""

    def _write_profile(self, tmp_path, data: dict, name: str = "brand-profile.yaml"):
        p = tmp_path / name
        p.write_text(yaml.dump(data), encoding="utf-8")
        return str(p)

    def test_loads_full_profile(self, tmp_path):
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

    def test_loads_minimal_profile(self, tmp_path):
        path = self._write_profile(tmp_path, {"brand_name": "Acme"})
        bp = load_brand_profile(path)

        assert bp.brand_name == "Acme"
        assert bp.aliases == []
        assert bp.cta_principles == []
        assert bp.blocked_words == []
        assert bp.tone_guidelines == ""
        assert bp.brand_identity == ""
        assert bp.languages == {}

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Brand profile not found"):
            load_brand_profile(str(tmp_path / "nope.yaml"))

    def test_non_dict_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_brand_profile(str(p))

    def test_empty_brand_name_raises(self, tmp_path):
        path = self._write_profile(tmp_path, {"brand_name": ""})
        with pytest.raises(ValueError, match="validation failed"):
            load_brand_profile(str(path))

    def test_partial_optional_fields(self, tmp_path):
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

    def test_default_construction(self):
        bp = BrandProfile()
        assert bp.brand_name == ""
        assert bp.aliases == []
        assert bp.cta_principles == []
        assert bp.blocked_words == []
        assert bp.tone_guidelines == ""
        assert bp.brand_identity == ""
        assert bp.languages == {}

    def test_lists_are_independent(self):
        bp1 = BrandProfile()
        bp2 = BrandProfile()
        bp1.aliases.append("X")
        assert "X" not in bp2.aliases

    def test_languages_dict_is_independent(self):
        bp1 = BrandProfile()
        bp2 = BrandProfile()
        bp1.languages["en"] = {"locale": "en-US"}
        assert "en" not in bp2.languages
