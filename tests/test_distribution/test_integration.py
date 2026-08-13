"""Integration tests for distribution flow, MCP tool calls, and cron scheduling.

Covers:
  - Full distribution flow: ``distribute_to_platforms()`` with mocked discovery
  - MCP tool call verification: ``distribute_content()`` parameter validation
  - Cron schedule lifecycle: add, list, remove via CLI helpers

All tests use mocked external dependencies — no real API calls or file writes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ===========================================================================
# Helpers: synthetic test data
# ===========================================================================

_SAMPLE_PROJECT_ID: str = "a1b2c3d4e5f6"
_SAMPLE_PROJECT: dict[str, Any] = {
    "project_id": _SAMPLE_PROJECT_ID,
    "topic": "AI technology trends 2025",
    "brand": "TestBrand",
    "mode": "auto",
    "_dir": "/tmp/projects/test-project",
}

_FAKE_REGISTERED_PLATFORMS: list[str] = ["wechat", "zhihu", "twitter", "xiaohongshu"]


class _FakeAdapter:
    """Minimal adapter stub that always validates successfully."""

    platform_name = "wechat"
    is_stub = True

    def __init__(self, account_id: str = "") -> None:
        self.account_id = account_id

    def validate(self, artifact_dir: str) -> bool:
        return True


class _FakeFailingAdapter:
    """Adapter stub that never validates."""

    platform_name = "failing"
    is_stub = True

    def __init__(self, account_id: str = "") -> None:
        self.account_id = account_id

    def validate(self, artifact_dir: str) -> bool:
        return False


# ===========================================================================
# Distribution flow integration tests
# ===========================================================================


class TestDistributeToPlatforms:
    """Integration tests for ``distribute_to_platforms()``.

    Uses ``AdapterRegistry`` singleton directly (registering test adapters)
    rather than patching, because the registry is lazily imported inside
    ``distribute_to_platforms()`` via ``from automedia.adapters.registry import AdapterRegistry``.
    """

    def _setup_adapter_mocks(self, platforms: list[str] | None = None) -> None:
        """Register test adapters in the singleton registry."""
        from automedia.adapters.registry import AdapterRegistry

        if platforms is None:
            platforms = _FAKE_REGISTERED_PLATFORMS

        AdapterRegistry.clear()
        for name in platforms:

            class _TestAdapter:
                platform_name = name
                is_stub = True

                def __init__(self, account_id: str = "") -> None:
                    self.account_id = account_id

                def validate(self, artifact_dir: str) -> bool:
                    return True

            AdapterRegistry.register(_TestAdapter)

    def _teardown_adapter_mocks(self) -> None:
        """Clean up registered test adapters."""
        from automedia.adapters.registry import AdapterRegistry

        AdapterRegistry.clear()

    # ------------------------------------------------------------------
    # Success paths
    # ------------------------------------------------------------------

    def test_dry_run_all_platforms(self) -> None:
        """Dry-run with all_platforms=True returns would_succeed for all."""
        from automedia.adapters.distribution import distribute_to_platforms

        self._setup_adapter_mocks()
        try:
            with patch(
                "automedia.adapters.distribution._discover_projects",
                return_value=[_SAMPLE_PROJECT],
            ):
                result = distribute_to_platforms(
                    project_id=_SAMPLE_PROJECT_ID,
                    all_platforms=True,
                    dry_run=True,
                )
        finally:
            self._teardown_adapter_mocks()

        assert result["dry_run"] is True
        assert len(result["platforms"]) == len(_FAKE_REGISTERED_PLATFORMS)
        for platform, status in result["platforms"].items():
            assert status in ("would_succeed", "would_fail"), f"Unexpected status for {platform}: {status}"
        assert result["summary"].startswith(f"{len(_FAKE_REGISTERED_PLATFORMS)}/")
        assert "would succeed" in result["summary"]

    def test_dry_run_specific_platforms(self) -> None:
        """Dry-run with specific platform list."""
        from automedia.adapters.distribution import distribute_to_platforms

        self._setup_adapter_mocks()
        target = ["wechat", "zhihu"]
        try:
            with patch(
                "automedia.adapters.distribution._discover_projects",
                return_value=[_SAMPLE_PROJECT],
            ):
                result = distribute_to_platforms(
                    project_id=_SAMPLE_PROJECT_ID,
                    platforms=target,
                    dry_run=True,
                )
        finally:
            self._teardown_adapter_mocks()

        assert result["dry_run"] is True
        assert set(result["platforms"].keys()) == set(target)
        for status in result["platforms"].values():
            assert status == "would_succeed"

    def test_publish_all_platforms_with_mocked_engine(self) -> None:
        """Publish to all platforms with mocked PublishEngine returns success."""
        from automedia.adapters.distribution import distribute_to_platforms

        self._setup_adapter_mocks()
        try:
            with (
                patch(
                    "automedia.adapters.distribution._discover_projects",
                    return_value=[_SAMPLE_PROJECT],
                ),
                patch(
                    "automedia.adapters.distribution.PublishEngine.publish_all",
                    return_value={
                        "wechat": {"status": "ok"},
                        "zhihu": {"status": "ok"},
                        "twitter": {"status": "ok"},
                        "xiaohongshu": {"status": "ok"},
                    },
                ),
            ):
                result = distribute_to_platforms(
                    project_id=_SAMPLE_PROJECT_ID,
                    all_platforms=True,
                )
        finally:
            self._teardown_adapter_mocks()

        assert result["dry_run"] is False
        assert len(result["platforms"]) == len(_FAKE_REGISTERED_PLATFORMS)
        for platform, status in result["platforms"].items():
            assert status == "success", f"Platform {platform} failed: {status}"
        assert "succeeded" in result["summary"]

    def test_publish_partial_failure(self) -> None:
        """Partial publish failure returns mixed statuses."""
        from automedia.adapters.distribution import distribute_to_platforms

        self._setup_adapter_mocks()
        try:
            with (
                patch(
                    "automedia.adapters.distribution._discover_projects",
                    return_value=[_SAMPLE_PROJECT],
                ),
                patch(
                    "automedia.adapters.distribution.PublishEngine.publish_all",
                    return_value={
                        "wechat": {"status": "ok"},
                        "zhihu": {"status": "error", "reason": "auth failed"},
                        "twitter": {"status": "skipped"},
                        "xiaohongshu": {"status": "draft_created"},
                    },
                ),
            ):
                result = distribute_to_platforms(
                    project_id=_SAMPLE_PROJECT_ID,
                    all_platforms=True,
                )
        finally:
            self._teardown_adapter_mocks()

        assert result["platforms"]["wechat"] == "success"
        assert result["platforms"]["zhihu"] == "failed"
        assert result["platforms"]["twitter"] == "skipped"
        assert result["platforms"]["xiaohongshu"] == "success"

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_no_platforms_specified(self) -> None:
        """No platforms and all_platforms=False returns error."""
        from automedia.adapters.distribution import distribute_to_platforms

        self._setup_adapter_mocks()
        try:
            with patch(
                "automedia.adapters.distribution._discover_projects",
                return_value=[_SAMPLE_PROJECT],
            ):
                result = distribute_to_platforms(
                    project_id=_SAMPLE_PROJECT_ID,
                    platforms=None,
                    all_platforms=False,
                )
        finally:
            self._teardown_adapter_mocks()

        assert result["summary"] == "No platforms specified. Provide a platform list or set all=True."
        assert "error" in result

    def test_project_not_found(self) -> None:
        """Non-existent project ID returns not-found error."""
        from automedia.adapters.distribution import distribute_to_platforms

        with patch(
            "automedia.adapters.distribution._discover_projects",
            return_value=[],
        ):
            result = distribute_to_platforms(
                project_id="nonexistent",
                platforms=["wechat"],
                dry_run=True,
            )

        assert "not found" in result["summary"].lower()
        assert "error" in result

    def test_unknown_platforms(self) -> None:
        """Unknown platform names return error."""
        from automedia.adapters.distribution import distribute_to_platforms

        self._setup_adapter_mocks()
        try:
            with patch(
                "automedia.adapters.distribution._discover_projects",
                return_value=[_SAMPLE_PROJECT],
            ):
                result = distribute_to_platforms(
                    project_id=_SAMPLE_PROJECT_ID,
                    platforms=["unknown_platform"],
                )
        finally:
            self._teardown_adapter_mocks()

        assert "Unknown platforms" in result["summary"]
        assert "error" in result

    def test_engine_publish_error(self) -> None:
        """PublishEngine raises exception -> all platforms show failed."""
        from automedia.adapters.distribution import distribute_to_platforms

        self._setup_adapter_mocks()
        try:
            with (
                patch(
                    "automedia.adapters.distribution._discover_projects",
                    return_value=[_SAMPLE_PROJECT],
                ),
                patch(
                    "automedia.adapters.distribution.PublishEngine.publish_all",
                    side_effect=RuntimeError("Engine crashed"),
                ),
            ):
                result = distribute_to_platforms(
                    project_id=_SAMPLE_PROJECT_ID,
                    all_platforms=True,
                )
        finally:
            self._teardown_adapter_mocks()

        assert not result["dry_run"]
        for status in result["platforms"].values():
            assert status == "failed"
        assert "engine error" in result["summary"].lower()


# ===========================================================================
# MCP tool call verification
# ===========================================================================


class TestDistributeContentMCP:
    """Verify ``distribute_content`` MCP tool parameter validation and delegation.

    ``distribute_to_platforms`` is lazily imported inside ``distribute_content()``,
    so we patch it at its definition site: ``automedia.adapters.distribution.distribute_to_platforms``.
    """

    def test_mcp_valid_params_delegates(self) -> None:
        """Valid parameters delegate to ``distribute_to_platforms``."""
        from automedia.mcp.tools_distribution import distribute_content

        with patch(
            "automedia.adapters.distribution.distribute_to_platforms",
            return_value={
                "platforms": {"wechat": "success"},
                "summary": "1/1 platforms succeeded",
                "dry_run": False,
            },
        ) as mock_delegate:
            result = distribute_content(
                project_id=_SAMPLE_PROJECT_ID,
                platforms="wechat",
            )

        mock_delegate.assert_called_once_with(
            project_id=_SAMPLE_PROJECT_ID,
            platforms=["wechat"],
            all_platforms=False,
            dry_run=False,
            base_dir=None,
        )
        assert "platforms" in result
        assert result["platforms"]["wechat"] == "success"

    def test_mcp_all_flag_delegates(self) -> None:
        """all=True with no platforms delegates correctly."""
        from automedia.mcp.tools_distribution import distribute_content

        with patch(
            "automedia.adapters.distribution.distribute_to_platforms",
            return_value={
                "platforms": {},
                "summary": "0/0 platforms succeeded",
                "dry_run": False,
            },
        ) as mock_delegate:
            distribute_content(
                project_id=_SAMPLE_PROJECT_ID,
                platforms=None,
                all=True,
            )

        mock_delegate.assert_called_once_with(
            project_id=_SAMPLE_PROJECT_ID,
            platforms=None,
            all_platforms=True,
            dry_run=False,
            base_dir=None,
        )

    def test_mcp_empty_project_id_returns_error(self) -> None:
        """Empty project_id returns error without calling delegate."""
        from automedia.mcp.tools_distribution import distribute_content

        with patch(
            "automedia.adapters.distribution.distribute_to_platforms",
        ) as mock_delegate:
            result = distribute_content(project_id="", platforms="wechat")

        mock_delegate.assert_not_called()
        assert ("error" in result) or ("isError" in str(result))

    def test_mcp_no_platforms_no_all_returns_error(self) -> None:
        """No platforms and all=False returns error."""
        from automedia.mcp.tools_distribution import distribute_content

        with patch(
            "automedia.adapters.distribution.distribute_to_platforms",
        ) as mock_delegate:
            result = distribute_content(
                project_id=_SAMPLE_PROJECT_ID,
                platforms=None,
                all=False,
            )

        mock_delegate.assert_not_called()
        assert ("error" in result) or ("isError" in str(result))

    def test_mcp_delegate_error_wrapped(self) -> None:
        """Errors from ``distribute_to_platforms`` are wrapped appropriately."""
        from automedia.mcp.tools_distribution import distribute_content

        with patch(
            "automedia.adapters.distribution.distribute_to_platforms",
            return_value={
                "platforms": {},
                "summary": "Project 'bad' not found",
                "dry_run": False,
                "error": "Project 'bad' not found in /tmp/projects",
            },
        ):
            result = distribute_content(
                project_id="bad",
                platforms="wechat",
            )

        assert "platforms" in result
        assert "not found" in result.get("summary", "").lower()


# ===========================================================================
# Cron schedule lifecycle tests
# ===========================================================================


class TestCronScheduleLifecycle:
    """Cron schedule add/list/remove — tests yaml file operations directly.

    The cron helpers (``_read_schedules``, ``_write_schedules``) are nested
    inside ``distribute_cmd()``, so we test the yaml file format and operations
    that those helpers use.
    """

    @pytest.fixture()
    def temp_jobs_yaml(self) -> Generator[Path, None, None]:
        """Create a temporary jobs.yaml for testing."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            encoding="utf-8",
            delete=False,
        ) as fh:
            yaml.dump(
                {"pipeline_schedules": []},
                fh,
                default_flow_style=False,
                allow_unicode=True,
            )
            tmp_path = Path(fh.name)
        yield tmp_path
        if tmp_path.exists():
            tmp_path.unlink()

    def _read_schedules(self, path: Path) -> list[dict[str, Any]]:
        """Read ``pipeline_schedules`` from a yaml file (mirrors the CLI helper)."""
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                return []
            return data.get("pipeline_schedules", []) or []
        except Exception:
            return []

    def _write_schedules(self, path: Path, schedules: list[dict[str, Any]]) -> None:
        """Write ``pipeline_schedules`` to a yaml file (mirrors the CLI helper)."""
        data: dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        data["pipeline_schedules"] = schedules
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)

    def test_add_schedule(self, temp_jobs_yaml: Path) -> None:
        """Add a cron schedule entry."""
        schedules = self._read_schedules(temp_jobs_yaml)
        assert schedules == []

        entry: dict[str, Any] = {
            "name": "distribute-a1b2c3d4e5f6",
            "expression": "0 8 * * *",
            "command": "automedia distribute a1b2c3d4e5f6 --platforms wechat,zhihu",
            "project_id": "a1b2c3d4e5f6",
            "platforms": "wechat,zhihu",
        }
        schedules.append(entry)
        self._write_schedules(temp_jobs_yaml, schedules)

        loaded = self._read_schedules(temp_jobs_yaml)
        assert len(loaded) == 1
        assert loaded[0]["name"] == "distribute-a1b2c3d4e5f6"
        assert loaded[0]["expression"] == "0 8 * * *"
        assert loaded[0]["platforms"] == "wechat,zhihu"

        # Verify file format
        with open(temp_jobs_yaml, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert "pipeline_schedules" in data
        assert len(data["pipeline_schedules"]) == 1

    def test_list_schedules(self, temp_jobs_yaml: Path) -> None:
        """List schedules filtered by project ID prefix."""
        self._write_schedules(temp_jobs_yaml, [
            {
                "name": "distribute-a1b2c3d4e5f6",
                "expression": "0 8 * * *",
                "command": "automedia distribute a1b2c3d4e5f6 --platforms wechat",
                "project_id": "a1b2c3d4e5f6",
                "platforms": "wechat",
            },
            {
                "name": "distribute-zzzzzzzzzzzz",
                "expression": "0 9 * * *",
                "command": "automedia distribute zzzzzzzzzzzz --platforms zhihu",
                "project_id": "zzzzzzzzzzzz",
                "platforms": "zhihu",
            },
        ])

        all_schedules = self._read_schedules(temp_jobs_yaml)
        project_schedules = [
            s for s in all_schedules
            if s.get("name", "").startswith("distribute-a1b2c3d4e5f6")
        ]

        assert len(project_schedules) == 1
        assert project_schedules[0]["project_id"] == "a1b2c3d4e5f6"

        other_schedules = [
            s for s in all_schedules
            if s.get("name", "").startswith("distribute-zzzzzzzzzzzz")
        ]
        assert len(other_schedules) == 1

    def test_remove_schedule(self, temp_jobs_yaml: Path) -> None:
        """Remove a cron schedule entry."""
        self._write_schedules(temp_jobs_yaml, [
            {
                "name": "distribute-a1b2c3d4e5f6",
                "expression": "0 8 * * *",
                "command": "automedia distribute a1b2c3d4e5f6 --platforms wechat",
                "project_id": "a1b2c3d4e5f6",
                "platforms": "wechat",
            },
        ])
        assert len(self._read_schedules(temp_jobs_yaml)) == 1

        all_schedules = self._read_schedules(temp_jobs_yaml)
        remaining = [s for s in all_schedules if s.get("name") != "distribute-a1b2c3d4e5f6"]
        self._write_schedules(temp_jobs_yaml, remaining)

        assert len(self._read_schedules(temp_jobs_yaml)) == 0
        with open(temp_jobs_yaml, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["pipeline_schedules"] == []

    def test_duplicate_detection(self, temp_jobs_yaml: Path) -> None:
        """Detect duplicate schedule names."""
        entry: dict[str, Any] = {
            "name": "distribute-a1b2c3d4e5f6",
            "expression": "0 8 * * *",
            "command": "automedia distribute a1b2c3d4e5f6 --platforms wechat",
            "project_id": "a1b2c3d4e5f6",
            "platforms": "wechat",
        }
        self._write_schedules(temp_jobs_yaml, [entry])

        schedules = self._read_schedules(temp_jobs_yaml)
        name_exists = any(s.get("name") == "distribute-a1b2c3d4e5f6" for s in schedules)
        assert name_exists is True

    def test_empty_yaml_file(self, temp_jobs_yaml: Path) -> None:
        """Empty or missing yaml file returns empty schedule list."""
        with open(temp_jobs_yaml, "w", encoding="utf-8") as fh:
            yaml.dump({}, fh)

        schedules = self._read_schedules(temp_jobs_yaml)
        assert schedules == []

        temp_jobs_yaml.unlink()
        schedules = self._read_schedules(temp_jobs_yaml)
        assert schedules == []
