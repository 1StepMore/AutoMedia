"""RED tests for HITLConfig — preset loading, overrides merge, executor resolution.

Scenarios
---------
1. 27 nodes loaded correctly from preset
2. get_executor() returns "human"/"agent" per preset config
3. Overrides correctly override single node
4. Invalid node name raises KeyError
5. set_executor() updates node config
6. list_nodes() returns all nodes with config
"""

from __future__ import annotations

import pytest
import yaml

from automedia.decision import dependency


class TestHITLConfigPreset:
    """Preset configuration loading."""

    def test_27_nodes_loaded(self) -> None:
        from automedia.hitl.config import HITLConfig
        config = HITLConfig(preset_name="test_automated")
        nodes = config.list_nodes()
        assert len(nodes) == 27, f"Expected 27 nodes, got {len(nodes)}"

    def test_automated_preset_brand_questionnaire_is_human(self) -> None:
        from automedia.hitl.config import HITLConfig
        config = HITLConfig(preset_name="test_automated")
        assert config.get_executor("brand_questionnaire") == "human"

    def test_automated_preset_build_nodes_are_agent(self) -> None:
        from automedia.hitl.config import HITLConfig
        config = HITLConfig(preset_name="test_automated")
        for node_name in ["brand_positioning", "market_research", "competitor_analysis"]:
            assert config.get_executor(node_name) == "agent"

    def test_unknown_node_raises_key_error(self) -> None:
        from automedia.hitl.config import HITLConfig
        config = HITLConfig(preset_name="test_automated")
        with pytest.raises(KeyError):
            config.get_executor("nonexistent_node")


class TestHITLConfigOverrides:
    """Override merging behavior."""

    def test_override_single_node(self, tmp_path) -> None:
        from automedia.hitl.config import HITLConfig
        overrides_dir = tmp_path / "hitl" / "overrides"
        overrides_dir.mkdir(parents=True)
        override_file = overrides_dir / "custom.yaml"
        override_file.write_text(yaml.dump({
            "brand_positioning": {"autoset": "human"},
        }))
        config = HITLConfig(preset_name="test_automated", overrides_dir=str(overrides_dir))
        assert config.get_executor("brand_positioning") == "human"

    def test_override_only_changes_specified_node(self, tmp_path) -> None:
        from automedia.hitl.config import HITLConfig
        overrides_dir = tmp_path / "hitl" / "overrides"
        overrides_dir.mkdir(parents=True)
        override_file = overrides_dir / "custom.yaml"
        override_file.write_text(yaml.dump({
            "brand_positioning": {"autoset": "human"},
        }))
        config = HITLConfig(preset_name="test_automated", overrides_dir=str(overrides_dir))
        assert config.get_executor("market_research") == "agent"


class TestHITLConfigSetExecutor:
    """Dynamic executor changes."""

    def test_set_executor_changes_value(self) -> None:
        from automedia.hitl.config import HITLConfig
        config = HITLConfig(preset_name="test_automated")
        config.set_executor("brand_positioning", "human")
        assert config.get_executor("brand_positioning") == "human"

    def test_set_executor_invalid_value_raises(self) -> None:
        from automedia.hitl.config import HITLConfig
        config = HITLConfig(preset_name="test_automated")
        with pytest.raises(ValueError):
            config.set_executor("brand_positioning", "robot")
