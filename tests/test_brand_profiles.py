"""Tests for multi-brand profile storage.

Covers:
- ``load_brand_profiles()``
- ``save_brand_profile()``
- ``list_brand_names()``
- Fallback compatibility in ``run_full_pipeline``
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from automedia.gates.base import BaseGate, _registry
from automedia.manifests.brand_profile_schema import (
    BrandProfile,
    list_brand_names,
    load_brand_profiles,
    save_brand_profile,
)

# =========================================================================
# Helpers
# =========================================================================


def _profile_data(
    brand_name: str = "TestBrand",
    **overrides: Any,
) -> dict[str, Any]:
    """Build a valid brand profile dict, with optional overrides."""
    data = {
        "brand_name": brand_name,
        "aliases": ["TB", "Test B"],
        "cta_principles": ["Include CTA", "Use action verbs"],
        "blocked_words": ["spam"],
        "tone_guidelines": "Professional",
        "brand_identity": "AI内容生产",
        "languages": {"zh": {"locale": "zh-CN"}},
    }
    data.update(overrides)
    return data


# =========================================================================
# load_brand_profiles
# =========================================================================


class TestLoadBrandProfiles:
    """Unit tests for load_brand_profiles()."""

    def test_returns_empty_dict_when_file_missing(self, tmp_path: Any) -> None:
        """No file → empty dict."""
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            tmp_path / "nonexistent.yaml",
        ):
            profiles = load_brand_profiles()
            assert profiles == {}

    def test_returns_empty_dict_for_empty_file(self, tmp_path: Any) -> None:
        """Empty file → empty dict."""
        bp_file = tmp_path / "brand_profiles.yaml"
        bp_file.write_text("", encoding="utf-8")
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()
            assert profiles == {}

    def test_returns_empty_dict_for_non_dict_yaml(self, tmp_path: Any) -> None:
        """Non-dict YAML (e.g. list) → empty dict."""
        bp_file = tmp_path / "brand_profiles.yaml"
        bp_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()
            assert profiles == {}

    def test_loads_single_profile(self, tmp_path: Any) -> None:
        """Single valid profile is loaded correctly."""
        data = {"acme": _profile_data("Acme")}
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()
        assert "acme" in profiles
        assert isinstance(profiles["acme"], BrandProfile)
        assert profiles["acme"].brand_name == "Acme"
        assert profiles["acme"].aliases == ["TB", "Test B"]

    def test_loads_multiple_profiles(self, tmp_path: Any) -> None:
        """Multiple profiles are all loaded."""
        data = {
            "acme": _profile_data("Acme"),
            "beta": _profile_data("Beta", aliases=["B"]),
            "gamma": _profile_data("Gamma", tone_guidelines="Casual"),
        }
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()
        assert set(profiles) == {"acme", "beta", "gamma"}
        assert profiles["beta"].aliases == ["B"]
        assert profiles["gamma"].tone_guidelines == "Casual"

    def test_skips_invalid_profiles(self, tmp_path: Any) -> None:
        """Profiles missing brand_name are skipped."""
        data = {
            "valid": _profile_data("ValidBrand"),
            "invalid": {"aliases": ["NoName"]},  # missing brand_name
        }
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()
        assert "valid" in profiles
        assert "invalid" not in profiles


# =========================================================================
# New fields (industry, target_audience, personality, platforms)
# =========================================================================


class TestBrandProfileNewFields:
    """Tests for the new industry/target_audience/personality/platforms fields."""

    def test_brand_profile_new_fields(self, tmp_path: Any) -> None:
        """Profile with new fields set loads correctly (list format)."""
        data = {
            "acme": _profile_data(
                "Acme",
                industry="Technology",
                target_audience="Developers",
                personality="Professional",
                platforms=["wechat", "zhihu"],
            ),
        }
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()

        bp = profiles["acme"]
        assert bp.industry == "Technology"
        assert bp.target_audience == "Developers"
        assert bp.personality == "Professional"
        assert bp.platforms == ["wechat", "zhihu"]

    def test_platforms_legacy_dict_format(self, tmp_path: Any) -> None:
        """Legacy dict format for platforms extracts keys as platform list."""
        data = {
            "acme": _profile_data(
                "Acme",
                platforms={
                    "wechat": {"enabled": True},
                    "xiaohongshu": {"enabled": False},
                },
            ),
        }
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()

        bp = profiles["acme"]
        # Legacy dict keys are extracted as platform names
        assert sorted(bp.platforms) == ["wechat", "xiaohongshu"]

    def test_validation_with_partial_data(self, tmp_path: Any) -> None:
        """Profile with only brand_name loads new fields as empty defaults."""
        # Build data without the new fields to simulate an older YAML file
        data = {
            "partial": {
                "brand_name": "Partial",
                "aliases": ["P"],
                "cta_principles": [],
                "blocked_words": [],
                "tone_guidelines": "",
                "brand_identity": "",
                "languages": {},
            },
        }
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()

        bp = profiles["partial"]
        assert bp.industry == ""
        assert bp.target_audience == ""
        assert bp.personality == ""
        assert bp.platforms == []

    def test_validation_with_minimal_data(self, tmp_path: Any) -> None:
        """Profile dict with only brand_name creates valid profile with empty defaults."""
        bp_file = tmp_path / "brand_profiles.yaml"
        raw = {"minimal": {"brand_name": "Minimal"}}
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(raw, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            profiles = load_brand_profiles()

        bp = profiles["minimal"]
        assert bp.brand_name == "Minimal"
        assert bp.industry == ""
        assert bp.target_audience == ""
        assert bp.personality == ""
        assert bp.platforms == []
        assert bp.aliases == []
        assert bp.languages == {}


# =========================================================================
# Platform validation
# =========================================================================


class TestBrandProfilePlatformValidation:
    """Tests for platform name validation against AdapterRegistry."""

    def test_valid_platforms_load_without_warning(
        self,
        tmp_path: Any,
        recwarn: Any,
    ) -> None:
        """Known platform names load without triggering a warning."""
        data = {"acme": _profile_data("Acme", platforms=["wechat", "zhihu"])}
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            with patch(
                "automedia.manifests.brand_profile_schema._get_registered_platform_names",
                return_value={"wechat", "zhihu"},
            ):
                profiles = load_brand_profiles()
        assert "acme" in profiles
        # No warnings should be emitted for valid platforms
        platform_warnings = [w for w in recwarn if "not a registered adapter" in str(w.message)]
        assert len(platform_warnings) == 0

    def test_unknown_platform_triggers_warning(self, tmp_path: Any) -> None:
        """Unknown platform names trigger a warning."""
        data = {"acme": _profile_data("Acme", platforms=["unknown_platform"])}
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            with patch(
                "automedia.manifests.brand_profile_schema._get_registered_platform_names",
                return_value={"wechat", "zhihu"},
            ):
                with pytest.warns(UserWarning, match="not a registered adapter") as record:
                    profiles = load_brand_profiles()
        assert "acme" in profiles
        assert len(record) == 1
        assert "unknown_platform" in str(record[0].message)

    def test_no_warning_for_empty_platforms(
        self,
        tmp_path: Any,
        recwarn: Any,
    ) -> None:
        """Empty platforms list does not trigger any warning."""
        data = {"acme": _profile_data("Acme", platforms=[])}
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            with patch(
                "automedia.manifests.brand_profile_schema._get_registered_platform_names",
                return_value={"wechat"},
            ):
                profiles = load_brand_profiles()
        assert "acme" in profiles
        platform_warnings = [w for w in recwarn if "not a registered adapter" in str(w.message)]
        assert len(platform_warnings) == 0

    def test_no_warning_when_registry_unavailable(
        self,
        tmp_path: Any,
        recwarn: Any,
    ) -> None:
        """When registry is unavailable, validation is skipped without warning."""
        data = {"acme": _profile_data("Acme", platforms=["unknown"])}
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            with patch(
                "automedia.manifests.brand_profile_schema._get_registered_platform_names",
                return_value=set(),
            ):
                profiles = load_brand_profiles()
        assert "acme" in profiles
        platform_warnings = [w for w in recwarn if "not a registered adapter" in str(w.message)]
        assert len(platform_warnings) == 0


# =========================================================================
# save_brand_profile
# =========================================================================


class TestSaveBrandProfile:
    """Unit tests for save_brand_profile()."""

    def test_creates_new_file(self, tmp_path: Any) -> None:
        """Saving a profile creates the YAML file."""
        bp_file = tmp_path / "brand_profiles.yaml"
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            save_brand_profile("acme", _profile_data("Acme"))
        assert bp_file.is_file()
        with open(bp_file, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        assert "acme" in loaded
        assert loaded["acme"]["brand_name"] == "Acme"

    def test_upserts_into_existing(self, tmp_path: Any) -> None:
        """Saving a second profile does not erase the first."""
        bp_file = tmp_path / "brand_profiles.yaml"
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            save_brand_profile("acme", _profile_data("Acme"))
            save_brand_profile("beta", _profile_data("Beta"))
        with open(bp_file, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        assert set(loaded) == {"acme", "beta"}

    def test_updates_existing_brand(self, tmp_path: Any) -> None:
        """Saving with an existing brand name overwrites it."""
        bp_file = tmp_path / "brand_profiles.yaml"
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            save_brand_profile("acme", _profile_data("Acme", tone_guidelines="Old"))
            save_brand_profile("acme", _profile_data("Acme", tone_guidelines="New"))
        with open(bp_file, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        assert loaded["acme"]["tone_guidelines"] == "New"

    def test_raises_on_invalid_data(self, tmp_path: Any) -> None:
        """Saving invalid data raises ValueError."""
        bp_file = tmp_path / "brand_profiles.yaml"
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            with pytest.raises(ValueError, match="validation failed"):
                save_brand_profile("bad", {"aliases": ["NoName"]})

    def test_atomic_write_does_not_corrupt_on_failure(self, tmp_path: Any) -> None:
        """If yaml.dump fails mid-write, original file is preserved."""
        bp_file = tmp_path / "brand_profiles.yaml"
        # Write an initial valid file
        initial = {"existing": _profile_data("Existing")}
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(initial, fh)
        original_content = bp_file.read_text()

        # Mock safe_dump to raise — the file should remain intact
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            with patch(
                "automedia.manifests.brand_profile_schema.yaml.safe_dump",
                side_effect=RuntimeError("dump failed"),
            ):
                with pytest.raises(RuntimeError):
                    save_brand_profile("acme", _profile_data("Acme"))

        assert bp_file.read_text() == original_content


# =========================================================================
# list_brand_names
# =========================================================================


class TestListBrandNames:
    """Unit tests for list_brand_names()."""

    def test_returns_empty_list_when_no_profiles(self, tmp_path: Any) -> None:
        """No profiles → empty list."""
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            tmp_path / "nonexistent.yaml",
        ):
            assert list_brand_names() == []

    def test_returns_sorted_names(self, tmp_path: Any) -> None:
        """Brand names are returned in sorted order."""
        data = {
            "zeta": _profile_data("Zeta"),
            "alpha": _profile_data("Alpha"),
            "beta": _profile_data("Beta"),
        }
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            names = list_brand_names()
        assert names == ["alpha", "beta", "zeta"]

    def test_excludes_invalid_profiles(self, tmp_path: Any) -> None:
        """Invalid profiles are not listed."""
        data = {
            "valid": _profile_data("Valid"),
            "invalid": {"no_name": True},
        }
        bp_file = tmp_path / "brand_profiles.yaml"
        with open(bp_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
        with patch(
            "automedia.manifests.brand_profile_schema._BRAND_PROFILES_PATH",
            bp_file,
        ):
            names = list_brand_names()
        assert names == ["valid"]


# =========================================================================
# Fallback compatibility (runner.py)
# =========================================================================


class TestFallbackCompat:
    """run_full_pipeline loads brand from multi-brand profiles, then
    falls back to project_dir/brand-profile.yaml."""

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    @patch("automedia.pipelines.runner.load_brand_profile")
    def test_uses_multi_brand_when_available(
        self,
        mock_load_single: MagicMock,
        mock_load_multi: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """When brand is in multi-brand profiles, use that — skip fallback."""
        from automedia.pipelines.runner import run_full_pipeline

        # Multi-brand profiles contains 'mybrand'
        mock_load_multi.return_value = {
            "mybrand": BrandProfile(
                brand_name="MyBrand",
                aliases=["MB"],
                tone_guidelines="Friendly",
            ),
        }

        mock_proj = MagicMock()
        mock_proj.project_id = "fb1"
        mock_proj.project_dir = str(tmp_path / "fb1")
        mock_project.init.return_value = mock_proj

        captured: dict[str, Any] = {"brand_profile": None}

        class _CaptureGate(BaseGate):
            _gate_name = "G55"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                captured["brand_profile"] = gate_context.get("brand_profile")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureGate()]

        try:
            run_full_pipeline("topic", "mybrand", mode="auto")

            # Should have loaded from multi-brand profiles
            bp = captured["brand_profile"]
            assert bp is not None, "brand_profile should be set from multi-brand profiles"
            if isinstance(bp, dict):
                assert bp.get("brand_name") == "MyBrand"
            else:
                assert bp.brand_name == "MyBrand"

            # Fallback should NOT have been called
            mock_load_single.assert_not_called()
        finally:
            # Clean up registry to avoid polluting other tests
            try:
                del _registry._registry["G55"]
            except KeyError:
                pass

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    @patch("automedia.pipelines.runner.load_brand_profile")
    def test_falls_back_to_project_file(
        self,
        mock_load_single: MagicMock,
        mock_load_multi: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """When brand is NOT in multi-brand profiles, fall back to
        project_dir/brand-profile.yaml."""
        from automedia.pipelines.runner import run_full_pipeline

        mock_load_multi.return_value = {}  # empty — no multi-brand profiles
        mock_load_single.return_value = BrandProfile(
            brand_name="LegacyBrand",
            aliases=["LB"],
            tone_guidelines="Legacy",
        )

        mock_proj = MagicMock()
        mock_proj.project_id = "fb2"
        mock_proj.project_dir = str(tmp_path / "fb2")
        mock_project.init.return_value = mock_proj

        captured: dict[str, Any] = {"brand_profile": None}

        class _CaptureGate(BaseGate):
            _gate_name = "G56"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                captured["brand_profile"] = gate_context.get("brand_profile")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureGate()]

        try:
            run_full_pipeline("topic", "legacy-brand", mode="auto")

            # Should have fallen back to project file
            bp = captured["brand_profile"]
            assert bp is not None, "brand_profile should be set via fallback"
            if isinstance(bp, dict):
                assert bp.get("brand_name") == "LegacyBrand"
            else:
                assert bp.brand_name == "LegacyBrand"

            mock_load_single.assert_called_once()
        finally:
            try:
                del _registry._registry["G56"]
            except KeyError:
                pass

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    @patch("automedia.pipelines.runner.load_brand_profile")
    def test_none_when_both_missing(
        self,
        mock_load_single: MagicMock,
        mock_load_multi: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """When both sources are missing, brand_profile is None."""
        from automedia.pipelines.runner import run_full_pipeline

        mock_load_multi.return_value = {}  # empty
        mock_load_single.side_effect = FileNotFoundError("not found")

        mock_proj = MagicMock()
        mock_proj.project_id = "fb3"
        mock_proj.project_dir = str(tmp_path / "fb3")
        mock_project.init.return_value = mock_proj

        captured: dict[str, Any] = {"brand_profile": "UNSET"}

        class _CaptureGate(BaseGate):
            _gate_name = "G57"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                captured["brand_profile"] = gate_context.get("brand_profile")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureGate()]

        try:
            run_full_pipeline("topic", "ghost-brand", mode="auto")

            # Both sources missing → None
            assert captured["brand_profile"] is None
        finally:
            try:
                del _registry._registry["G57"]
            except KeyError:
                pass

    @patch("automedia.pipelines.runner.load_config", return_value={})
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner._build_gates_from_names")
    @patch("automedia.pipelines.runner._record_gate_md5s")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    @patch("automedia.pipelines.runner.load_brand_profile")
    def test_fallback_works_with_existing_project_file(
        self,
        mock_load_single: MagicMock,
        mock_load_multi: MagicMock,
        mock_record: MagicMock,
        mock_build: MagicMock,
        mock_project: MagicMock,
        mock_config: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Backward compat: existing projects with brand-profile.yaml only
        continue to work when multi-brand is empty."""
        from automedia.pipelines.runner import run_full_pipeline

        mock_load_multi.return_value = {}  # no multi-brand
        mock_load_single.return_value = BrandProfile(
            brand_name="ExistingBrand",
            aliases=["EB"],
            cta_principles=["Legacy CTA"],
            blocked_words=["bad"],
            tone_guidelines="Old style",
            brand_identity="Legacy identity",
            languages={"zh": {"tts_voice": "zh-CN-XiaoxiaoNeural"}},
        )

        mock_proj = MagicMock()
        mock_proj.project_id = "fb4"
        mock_proj.project_dir = str(tmp_path / "fb4")
        mock_project.init.return_value = mock_proj

        # Verify the loaded profile has all fields preserved
        captured: dict[str, Any] = {"brand_profile": None}

        class _CaptureGate(BaseGate):
            _gate_name = "G86"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                captured["brand_profile"] = gate_context.get("brand_profile")
                return {"passed": True, "gate": self.gate_name}

        mock_build.return_value = [_CaptureGate()]

        try:
            run_full_pipeline("topic", "existing-brand", mode="auto")

            bp = captured["brand_profile"]
            assert bp is not None
        finally:
            try:
                del _registry._registry["G86"]
            except KeyError:
                pass
        if isinstance(bp, dict):
            assert bp.get("brand_name") == "ExistingBrand"
            assert "Legacy CTA" in bp.get("cta_principles", [])
            assert "bad" in bp.get("blocked_words", [])
        else:
            assert bp.brand_name == "ExistingBrand"
            assert "Legacy CTA" in bp.cta_principles
            assert "bad" in bp.blocked_words
