"""Tests for the open-core feature tier marker module (plan todo 16).

`automedia.features` is a declarative marker module: FEATURE_TIERS maps
canonical gate IDs to open-core tiers, FEATURE_ALIASES resolves roadmap-style
snake_case ids, and check_tier reports tier availability. No license logic,
no enforcement call sites (todo 17 owns enforcement).
"""

from __future__ import annotations

import pytest

import automedia.features as features
from automedia.features import FEATURE_ALIASES, FEATURE_TIERS, check_tier

# ---------------------------------------------------------------------------
# Tier table shape and registry agreement
# ---------------------------------------------------------------------------


class TestFeatureTiers:
    def test_tier_keys(self) -> None:
        assert set(FEATURE_TIERS) == {"core", "pro", "enterprise"}

    def test_union_is_exactly_33_gates(self) -> None:
        assert sum(len(v) for v in FEATURE_TIERS.values()) == 33

    def test_union_equals_registry_keys(self) -> None:
        from automedia.gates import base as gate_base

        registered = {
            name
            for name, cls in gate_base._registry.get_all().items()
            if getattr(cls, "__module__", "").startswith("automedia.")
        }
        union = {name for names in FEATURE_TIERS.values() for name in names}
        assert union == registered

    def test_union_equals_33_canonical_names(self) -> None:
        from automedia.gates import base as gate_base

        registered = {
            name
            for name, cls in gate_base._registry.get_all().items()
            if getattr(cls, "__module__", "").startswith("automedia.")
        }
        assert len(registered) == 33

    def test_tier_lists_disjoint(self) -> None:
        core = set(FEATURE_TIERS["core"])
        pro = set(FEATURE_TIERS["pro"])
        enterprise = set(FEATURE_TIERS["enterprise"])
        assert not core & pro
        assert not core & enterprise
        assert not pro & enterprise

    def test_expected_memberships(self) -> None:
        assert "pre-gate" in FEATURE_TIERS["core"]
        assert "CW" in FEATURE_TIERS["core"]
        assert "G0" in FEATURE_TIERS["core"]
        assert "L3" in FEATURE_TIERS["enterprise"]
        assert "P1" in FEATURE_TIERS["enterprise"]
        assert "V7" in FEATURE_TIERS["pro"]
        assert "H0" in FEATURE_TIERS["pro"]
        assert "D1" in FEATURE_TIERS["pro"]


# ---------------------------------------------------------------------------
# Alias table
# ---------------------------------------------------------------------------


class TestAliases:
    def test_alias_table_not_empty(self) -> None:
        assert len(FEATURE_ALIASES) > 0

    def test_alias_values_are_canonical_gate_names(self) -> None:
        from automedia.gates import base as gate_base

        registered = {
            name
            for name, cls in gate_base._registry.get_all().items()
            if getattr(cls, "__module__", "").startswith("automedia.")
        }
        for alias, target in FEATURE_ALIASES.items():
            if isinstance(target, str):
                assert target in registered, f"alias {alias!r} -> {target!r}"
            else:
                assert set(target) <= registered, f"alias {alias!r} -> {target!r}"

    def test_known_aliases_present(self) -> None:
        assert FEATURE_ALIASES["video-gate-v7"] == "V7"
        assert FEATURE_ALIASES["director-panel"] == "H0"
        assert set(FEATURE_ALIASES["video-gates"]) == {f"V{i}" for i in range(8)}
        assert set(FEATURE_ALIASES["multi-platform-publish"]) == {f"D{i}" for i in range(1, 8)}
        assert set(FEATURE_ALIASES["gate-history-dashboard"]) == {"L1", "L2"}


# ---------------------------------------------------------------------------
# check_tier
# ---------------------------------------------------------------------------


class TestCheckTier:
    def test_canonical_gate_id(self) -> None:
        result = check_tier("V7")
        assert result["feature"] == "V7"
        assert result["tier"] == "pro"
        assert result["available"] is True

    def test_core_gate_available(self) -> None:
        result = check_tier("G0")
        assert result == {"feature": "G0", "tier": "core", "available": True}

    def test_alias_resolves_to_canonical(self) -> None:
        result = check_tier("video-gate-v7")
        assert result["feature"] == "V7"
        assert result["tier"] == "pro"
        assert result["available"] is True

    def test_group_alias(self) -> None:
        result = check_tier("video-gates")
        assert result["feature"] == "video-gates"
        assert result["tier"] == "pro"
        assert result["available"] is True

    def test_unknown_feature_no_exception(self) -> None:
        result = check_tier("does-not-exist")
        assert result["available"] is False
        assert "error" in result

    def test_empty_string_unknown(self) -> None:
        result = check_tier("")
        assert result["available"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Override semantics (env AUTOMEDIA_FEATURE_TIER)
# ---------------------------------------------------------------------------


class TestTierOverride:
    """With no override everything is open (free local = everything)."""

    def test_no_override_everything_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)
        assert check_tier("V7")["available"] is True
        assert check_tier("L3")["available"] is True
        assert check_tier("P4")["available"] is True

    def test_env_override_pro_blocks_enterprise(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "pro")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))  # no features.yaml
        assert check_tier("G0")["available"] is True
        assert check_tier("V7")["available"] is True
        assert check_tier("L3")["available"] is False
        assert check_tier("P1")["available"] is False

    def test_env_override_core_blocks_pro_and_enterprise(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "core")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        assert check_tier("pre-gate")["available"] is True
        assert check_tier("G0")["available"] is True
        assert check_tier("V7")["available"] is False
        assert check_tier("L3")["available"] is False

    def test_yaml_override_features_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        config_dir = tmp_path / "usercfg"
        config_dir.mkdir()
        (config_dir / "features.yaml").write_text("tier: pro\n", encoding="utf-8")
        monkeypatch.delenv("AUTOMEDIA_FEATURE_TIER", raising=False)
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(config_dir))
        assert check_tier("V7")["available"] is True
        assert check_tier("P1")["available"] is False

    def test_invalid_override_ignored_means_open(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "not-a-tier")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        assert check_tier("V7")["available"] is True
        assert check_tier("P1")["available"] is True

    def test_env_wins_over_yaml(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        config_dir = tmp_path / "usercfg"
        config_dir.mkdir()
        (config_dir / "features.yaml").write_text("tier: core\n", encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_FEATURE_TIER", "enterprise")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(config_dir))
        assert check_tier("V7")["available"] is True  # enterprise >= pro
        assert check_tier("P1")["available"] is True
        assert check_tier("G0")["available"] is True


# ---------------------------------------------------------------------------
# Module hygiene
# ---------------------------------------------------------------------------


def test_env_var_documented_in_module() -> None:
    assert "AUTOMEDIA_FEATURE_TIER" in (features.__doc__ or "")


def test_no_license_logic_imported() -> None:
    """Marker module only: must not import licensing machinery."""
    assert "license" not in vars(features)
