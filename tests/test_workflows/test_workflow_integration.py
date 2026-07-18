"""End-to-end workflow integration tests.

Tests the full lifecycle: WorkflowLoader → YAML parsing → extends resolution
→ validation → merge with brand profile → pipeline parameter pass-through.

All tests use synthetic fixtures — zero production data.
No tests require LLM API calls or external services.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from automedia.core.workflow import Workflow, WorkflowLoader


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture()
def isolated_user_dir(tmp_path: Path) -> Iterator[Path]:
    """Redirect user config dir to a temp path so user workflows don't interfere."""
    import automedia.core.workflow as _wf_mod

    user_dir = tmp_path / "user_cfg"
    user_dir.mkdir()
    (user_dir / "workflows").mkdir()

    original = _wf_mod.get_user_config_dir
    _wf_mod.get_user_config_dir = lambda: user_dir  # type: ignore[method-assign]
    yield user_dir
    _wf_mod.get_user_config_dir = original


@pytest.fixture()
def workflows_dir(tmp_path: Path, isolated_user_dir: Path) -> Path:
    """Create a project-level workflows directory."""
    wd = tmp_path / "workflows"
    wd.mkdir()
    return wd


def _write_workflow_yaml(workflows_dir: Path, name: str, data: dict[str, Any]) -> Path:
    """Write a workflow YAML file and return its path."""
    path = workflows_dir / f"{name}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)
    return path


# =====================================================================
# Synthetic fixture data
# =====================================================================

_SAMPLE_WORKFLOW: dict[str, Any] = {
    "name": "_test_wf_int",
    "mode": "text_only",
    "platforms": ["wechat", "zhihu"],
    "brand": "TestBrand",
    "gates": {
        "include": ["G0", "G1"],
        "exclude": ["V0", "V1"],
    },
    "prompts": {
        "cw": "Write about {topic} in a professional tone",
    },
    "media": {
        "wechat": {"width": 1080, "height": 1920},
    },
    "schedule": {
        "expression": "0 6 * * 1",
        "count": 3,
    },
}

_BASE_WORKFLOW: dict[str, Any] = {
    "name": "_test_wf_base",
    "mode": "auto",
    "platforms": ["wechat"],
    "brand": "BaseBrand",
    "gates": {"include": ["G0"]},
    "prompts": {"cw": "Default writing prompt"},
    "media": {
        "wechat": {"width": 1080, "height": 1920},
    },
}

_EXTENDS_WORKFLOW: dict[str, Any] = {
    "name": "_test_wf_child",
    "extends": "_test_wf_base",
    "mode": "text_only",
    "platforms": ["zhihu"],
}


# =====================================================================
# Test 1 — WorkflowLoader loads all fields from a valid YAML
# =====================================================================


class TestWorkflowLoader:
    """WorkflowLoader loads YAML, validates, and returns a Workflow dataclass."""

    def test_loads_all_fields(self, workflows_dir: Path) -> None:
        """Create workflow YAML, load via WorkflowLoader, assert all 9 fields."""
        _write_workflow_yaml(workflows_dir, "_test_wf_int", _SAMPLE_WORKFLOW)

        loader = WorkflowLoader(workflows_dir=str(workflows_dir))
        wf = loader.load("_test_wf_int")

        assert isinstance(wf, Workflow)
        assert wf.name == "_test_wf_int"
        assert wf.mode == "text_only"
        assert wf.platforms == ["wechat", "zhihu"]
        assert wf.brand == "TestBrand"
        assert wf.gates == {"include": ["G0", "G1"], "exclude": ["V0", "V1"]}
        assert wf.prompts == {"cw": "Write about {topic} in a professional tone"}
        assert wf.media == {"wechat": {"width": 1080, "height": 1920}}
        assert wf.schedule == {"expression": "0 6 * * 1", "count": 3}
        # extends is None when not set
        assert wf.extends is None

    def test_minimal_workflow(self, workflows_dir: Path) -> None:
        """Workflow with only required fields loads without error."""
        minimal = {"name": "_test_minimal", "mode": "auto"}
        _write_workflow_yaml(workflows_dir, "_test_minimal", minimal)

        loader = WorkflowLoader(workflows_dir=str(workflows_dir))
        wf = loader.load("_test_minimal")

        assert wf.name == "_test_minimal"
        assert wf.mode == "auto"
        assert wf.platforms == []
        assert wf.brand is None
        assert wf.gates is None
        assert wf.prompts is None
        assert wf.media is None
        assert wf.schedule is None
        assert wf.extends is None

    def test_load_all(self, workflows_dir: Path) -> None:
        """load_all() discovers and returns all unique workflows."""
        _write_workflow_yaml(workflows_dir, "_test_wf_int", _SAMPLE_WORKFLOW)
        _write_workflow_yaml(workflows_dir, "_test_minimal", {"name": "_test_minimal", "mode": "auto"})

        loader = WorkflowLoader(workflows_dir=str(workflows_dir))
        all_wf = loader.load_all()

        assert isinstance(all_wf, dict)
        assert "_test_wf_int" in all_wf
        assert "_test_minimal" in all_wf
        assert len(all_wf) == 2
        assert all(isinstance(v, Workflow) for v in all_wf.values())


# =====================================================================
# Test 4 — Invalid workflow name raises FileNotFoundError
# =====================================================================


class TestWorkflowLoaderErrors:
    """WorkflowLoader error handling."""

    def test_invalid_name_raises_filenotfound(self, workflows_dir: Path) -> None:
        """Loading a non-existent workflow name raises FileNotFoundError."""
        loader = WorkflowLoader(workflows_dir=str(workflows_dir))
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent_workflow_name")

    def test_empty_workflows_dir(self, tmp_path: Path, isolated_user_dir: Path) -> None:
        """Empty workflows directory plus empty user dir raises FileNotFoundError."""
        empty_dir = tmp_path / "empty_workflows"
        empty_dir.mkdir()
        loader = WorkflowLoader(workflows_dir=str(empty_dir))
        with pytest.raises(FileNotFoundError):
            loader.load("any_workflow")


# =====================================================================
# Test 5 — Workflow extends loads merged config
# =====================================================================


class TestWorkflowExtends:
    """Workflow ``extends`` inheritance chain integration."""

    def test_extends_merges_config(self, workflows_dir: Path) -> None:
        """Child workflow inherits fields from parent, overrides where specified."""
        _write_workflow_yaml(workflows_dir, "_test_wf_base", _BASE_WORKFLOW)
        _write_workflow_yaml(workflows_dir, "_test_wf_child", _EXTENDS_WORKFLOW)

        loader = WorkflowLoader(workflows_dir=str(workflows_dir))
        wf = loader.load("_test_wf_child")

        assert isinstance(wf, Workflow)
        assert wf.name == "_test_wf_child"
        # Child overrides
        assert wf.mode == "text_only"
        assert wf.platforms == ["zhihu"]
        # Inherited from base
        assert wf.brand == "BaseBrand"
        assert wf.gates == {"include": ["G0"]}
        assert wf.prompts == {"cw": "Default writing prompt"}
        assert wf.media == {"wechat": {"width": 1080, "height": 1920}}
        # extends field is stripped after merge
        assert wf.extends is None

    def test_deep_merge_media(self, workflows_dir: Path) -> None:
        """Media specs are deep-merged (child fields supplement parent)."""
        _write_workflow_yaml(
            workflows_dir,
            "_test_wf_base",
            {
                "name": "_test_wf_base",
                "mode": "auto",
                "media": {"wechat": {"width": 1080, "height": 1920}},
            },
        )
        _write_workflow_yaml(
            workflows_dir,
            "_test_wf_child",
            {
                "name": "_test_wf_child",
                "extends": "_test_wf_base",
                "mode": "auto",
                "media": {"wechat": {"width": 800}, "zhihu": {"width": 640}},
            },
        )

        loader = WorkflowLoader(workflows_dir=str(workflows_dir))
        wf = loader.load("_test_wf_child")

        assert wf.media is not None
        # wechat.width overridden by child, wechat.height inherited from parent
        assert wf.media["wechat"] == {"width": 800, "height": 1920}
        # zhihu added by child
        assert wf.media["zhihu"] == {"width": 640}

    def test_name_mismatch_raises_valueerror(self, workflows_dir: Path) -> None:
        """YAML name field that differs from filename raises ValueError."""
        _write_workflow_yaml(
            workflows_dir,
            "_test_wf_mismatch",
            {"name": "wrong_name", "mode": "auto"},
        )
        loader = WorkflowLoader(workflows_dir=str(workflows_dir))
        with pytest.raises(ValueError, match="wrong_name"):
            loader.load("_test_wf_mismatch")


# =====================================================================
# Test 2 — _merge_workflow_config overrides brand profile fields
# =====================================================================


class TestWorkflowMerge:
    """``_merge_workflow_config`` — workflow overrides brand profile."""

    # Import here to avoid triggering full pipeline imports at collection time
    @staticmethod
    def _merge(workflow: Workflow, brand_profile: dict[str, Any]) -> dict[str, Any]:
        from automedia.pipelines.runner import _merge_workflow_config

        return _merge_workflow_config(workflow, brand_profile)

    def test_workflow_overrides_brand_profile(self) -> None:
        """Workflow fields override corresponding brand profile fields."""
        workflow = Workflow(
            name="_test_merge",
            mode="text_only",
            platforms=["zhihu"],
            brand="OverrideBrand",
            gates={"include": ["G0"], "exclude": ["V0"]},
            prompts={"cw": "Custom prompt"},
            media={"zhihu": {"width": 800}},
            schedule={"expression": "0 * * * *", "count": 1},
            extends=None,
        )
        brand_profile: dict[str, Any] = {
            "brand_name": "OriginalBrand",
            "platforms": ["wechat"],
            "media": {"wechat": {"width": 1080}},
            "other_field": "should_survive",
        }

        merged = self._merge(workflow, brand_profile)

        # Workflow overrides
        assert merged["platforms"] == ["zhihu"]
        assert merged["workflow_gates"] == {"include": ["G0"], "exclude": ["V0"]}
        assert merged["workflow_prompts"] == {"cw": "Custom prompt"}
        # Media should be deep-merged (workflow overrides extend existing)
        assert merged["media"] == {
            "wechat": {"width": 1080},
            "zhihu": {"width": 800},
        }
        # Non-overridden fields survive
        assert merged["brand_name"] == "OriginalBrand"
        assert merged["other_field"] == "should_survive"
        # Original brand_profile is not mutated
        assert "workflow_gates" not in brand_profile

    def test_empty_platforms_no_override(self) -> None:
        """Workflow with empty platforms list does not override brand platforms."""
        workflow = Workflow(
            name="_test_no_plat",
            mode="auto",
            platforms=[],
            brand=None,
            gates=None,
            prompts=None,
            media=None,
            schedule=None,
            extends=None,
        )
        brand_profile: dict[str, Any] = {
            "brand_name": "OriginalBrand",
            "platforms": ["wechat"],
        }

        merged = self._merge(workflow, brand_profile)

        assert merged["platforms"] == ["wechat"]
        assert "workflow_gates" not in merged
        assert "workflow_prompts" not in merged

    def test_media_deep_merge(self) -> None:
        """Media specs deep-merge: workflow keys supplement, not replace."""
        workflow = Workflow(
            name="_test_media",
            mode="auto",
            platforms=[],
            brand=None,
            gates=None,
            prompts=None,
            media={
                "wechat": {"width": 800},  # override existing
                "zhihu": {"width": 640},  # new platform
            },
            schedule=None,
            extends=None,
        )
        brand_profile = {
            "brand_name": "Test",
            "platforms": ["wechat"],
            "media": {"wechat": {"width": 1080, "height": 1920}},
        }

        merged = self._merge(workflow, brand_profile)

        assert merged["media"] == {
            "wechat": {"width": 800, "height": 1920},
            "zhihu": {"width": 640},
        }

    def test_media_no_existing(self) -> None:
        """When brand profile has no media, workflow media is used as-is."""
        workflow = Workflow(
            name="_test_no_media",
            mode="auto",
            platforms=[],
            brand=None,
            gates=None,
            prompts=None,
            media={"wechat": {"width": 800}},
            schedule=None,
            extends=None,
        )
        brand_profile = {"brand_name": "Test"}

        merged = self._merge(workflow, brand_profile)

        assert merged["media"] == {"wechat": {"width": 800}}


# =====================================================================
# Test 3 — Pipeline runs without workflow (unchanged behaviour)
# =====================================================================


class TestPipelineWithoutWorkflow:
    """run_full_pipeline / MCP run_pipeline without workflow parameter."""

    def test_mcp_run_pipeline_starts_without_workflow(self) -> None:
        """MCP run_pipeline with no workflow param returns 'started' status."""
        from automedia.mcp.server import run_pipeline

        result = run_pipeline(
            topic="integration test topic",
            brand="TestBrand",
            mode="auto",
        )
        assert isinstance(result, dict)
        assert result["status"] == "started"
        assert "project_id" in result

    def test_mcp_run_pipeline_with_empty_workflow(self) -> None:
        """MCP run_pipeline with empty workflow string still starts."""
        from automedia.mcp.server import run_pipeline

        result = run_pipeline(
            topic="integration test topic",
            brand="TestBrand",
            mode="auto",
            workflow="",
        )
        assert isinstance(result, dict)
        assert result["status"] == "started"

    @patch("automedia.pipelines.runner.WorkflowLoader")
    @patch("automedia.pipelines.runner.load_brand_profiles")
    @patch("automedia.pipelines.runner.GateEngine")
    @patch("automedia.pipelines.runner.Project.init")
    @patch("automedia.pipelines.runner.load_config")
    def test_run_full_pipeline_without_workflow_returns_result(
        self,
        mock_load_config: Any,
        mock_project_init: Any,
        mock_gate_engine: Any,
        mock_load_brand_profiles: Any,
        mock_workflow_loader: Any,
    ) -> None:
        """run_full_pipeline returns a PipelineResult without workflow param."""
        from automedia.pipelines.runner import run_full_pipeline

        # Minimal mocks to let pipeline flow through without real execution
        mock_load_config.return_value = {}
        mock_project = mock_project_init.return_value
        mock_project.project_id = "test-000"
        mock_project.project_dir = "/tmp/test-workflow-integration"
        mock_load_brand_profiles.return_value = {}
        mock_engine = mock_gate_engine.return_value
        mock_engine.run.return_value = (True, [])
        # Prevent WorkflowLoader from being called
        mock_workflow_loader.return_value.load.side_effect = RuntimeError(
            "WorkflowLoader should not be called"
        )

        result = run_full_pipeline(
            topic="integration test",
            brand="TestBrand",
            mode="auto",
        )

        assert result.status == "success"
        assert result.project_id == "test-000"
        assert result.workflow == ""
        # Verify WorkflowLoader.load was NOT called (no workflow param)
        mock_workflow_loader.return_value.load.assert_not_called()
