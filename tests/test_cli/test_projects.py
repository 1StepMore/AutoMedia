"""Tests for ``automedia projects`` CLI commands.

Covers all three sub-commands (list, get, get-assets) plus the internal
helper functions ``_discover_projects`` and ``_collect_assets``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.cli.commands.projects import (
    _ASSET_SUBDIRS,
    _collect_assets,
    _discover_projects,
)

runner = CliRunner()


# =========================================================================
# 1. Internal helpers: _discover_projects
# =========================================================================


class TestDiscoverProjects:
    """Direct tests for the ``_discover_projects()`` helper."""

    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        """Empty directory returns empty list."""
        result = _discover_projects(str(tmp_path))
        assert result == []

    def test_discover_single_project(self, tmp_path: Path) -> None:
        """Single valid project info file is discovered."""
        proj_dir = tmp_path / "20260707_my-project"
        proj_dir.mkdir()
        info = {"project_id": "abc123", "topic": "Test", "brand": "B"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = _discover_projects(str(tmp_path))
        assert len(result) == 1
        assert result[0]["project_id"] == "abc123"
        assert result[0]["topic"] == "Test"
        assert result[0]["_dir"] == str(proj_dir)

    def test_discover_multiple_projects(self, tmp_path: Path) -> None:
        """Multiple projects are discovered and sorted."""
        for i in range(3):
            proj_dir = tmp_path / f"2026070{i}_proj-{i}"
            proj_dir.mkdir()
            info = {"project_id": f"id{i:03d}", "topic": f"Topic {i}", "brand": "B"}
            (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = _discover_projects(str(tmp_path))
        assert len(result) == 3

    def test_discover_skips_invalid_json(self, tmp_path: Path) -> None:
        """Invalid JSON files are skipped gracefully."""
        proj_dir = tmp_path / "20260707_bad-json"
        proj_dir.mkdir()
        (proj_dir / "00_project_info.json").write_text(
            "this is not json{{", encoding="utf-8"
        )

        proj_dir2 = tmp_path / "20260708_good-json"
        proj_dir2.mkdir()
        info = {"project_id": "good", "topic": "Good", "brand": "B"}
        (proj_dir2 / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = _discover_projects(str(tmp_path))
        assert len(result) == 1
        assert result[0]["project_id"] == "good"

    def test_discover_skips_os_error_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError when reading a file is skipped gracefully."""
        proj_dir = tmp_path / "20260707_issue"
        proj_dir.mkdir()
        (proj_dir / "00_project_info.json").write_text("{}", encoding="utf-8")

        proj_dir2 = tmp_path / "20260708_ok"
        proj_dir2.mkdir()
        info = {"project_id": "ok", "topic": "OK", "brand": "B"}
        (proj_dir2 / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        original_open = open

        def _failing_open(*args: Any, **kwargs: Any) -> Any:
            fpath = str(args[0]) if args else ""
            if "issue" in fpath:
                raise OSError("Permission denied")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", _failing_open)
        result = _discover_projects(str(tmp_path))
        assert len(result) == 1
        assert result[0]["project_id"] == "ok"


# =========================================================================
# 2. Internal helpers: _collect_assets
# =========================================================================


class TestCollectAssets:
    """Direct tests for the ``_collect_assets()`` helper."""

    def test_collect_assets_with_files(self, tmp_path: Path) -> None:
        """Files inside standard subdirs are collected."""
        for subdir in _ASSET_SUBDIRS:
            (tmp_path / subdir).mkdir(parents=True)
        (tmp_path / "01_content" / "article.md").write_text("# Hello")
        (tmp_path / "02_images" / "cover.png").write_bytes(b"\x89PNG")
        (tmp_path / "03_video" / "final.mp4").write_bytes(b"\x00mp4")

        assets = _collect_assets(tmp_path)
        names = {a["name"] for a in assets}
        assert "article.md" in names
        assert "cover.png" in names
        assert "final.mp4" in names

    def test_collect_assets_empty_dirs(self, tmp_path: Path) -> None:
        """No files yields empty list."""
        for subdir in _ASSET_SUBDIRS:
            (tmp_path / subdir).mkdir(parents=True)
        assets = _collect_assets(tmp_path)
        assert assets == []

    def test_collect_assets_missing_dir(self, tmp_path: Path) -> None:
        """Missing subdirs are silently skipped."""
        # Only create 01_content
        (tmp_path / "01_content").mkdir(parents=True)
        (tmp_path / "01_content" / "draft.md").write_text("# Draft")
        assets = _collect_assets(tmp_path)
        assert len(assets) == 1
        assert assets[0]["name"] == "draft.md"
        assert assets[0]["subdir"] == "01_content"

    def test_collect_assets_nonexistent_project_dir(self, tmp_path: Path) -> None:
        """Non-existent project directory returns empty list."""
        assets = _collect_assets(tmp_path / "nonexistent")
        assert assets == []

    def test_collect_assets_include_size(self, tmp_path: Path) -> None:
        """Each asset entry includes name, path, subdir, and size."""
        (tmp_path / "01_content").mkdir(parents=True)
        (tmp_path / "01_content" / "test.txt").write_text("hello world")
        assets = _collect_assets(tmp_path)
        assert len(assets) == 1
        entry = assets[0]
        assert "name" in entry
        assert "path" in entry
        assert "subdir" in entry
        assert "size" in entry
        assert int(entry["size"]) >= 11  # "hello world" is 11 bytes


# =========================================================================
# 3. projects list
# =========================================================================


class TestProjectsList:
    """Tests for ``automedia projects list``."""

    def test_list_empty(self, tmp_path: Path) -> None:
        """Empty directory shows 'No projects found'."""
        result = runner.invoke(app, ["projects", "list", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No projects found" in result.output

    def test_list_finds_project(self, tmp_path: Path) -> None:
        """A valid project appears in the list output."""
        proj_dir = tmp_path / "20260707_test-topic"
        proj_dir.mkdir()
        info = {"project_id": "abc123def456", "topic": "Test Topic", "brand": "TestBrand"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = runner.invoke(app, ["projects", "list", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "abc123def456" in result.output
        assert "Test Topic" in result.output
        assert "TestBrand" in result.output

    def test_list_with_status_filter(self, tmp_path: Path) -> None:
        """--status filter narrows results."""
        for i, status in enumerate(["draft", "published", "archived"]):
            proj_dir = tmp_path / f"2026070{i}_proj-{i}"
            proj_dir.mkdir()
            info = {
                "project_id": f"id{i:03d}",
                "topic": f"Topic {i}",
                "brand": "B",
                "status": status,
            }
            (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = runner.invoke(
            app, ["projects", "list", "--base-dir", str(tmp_path), "--status", "published"]
        )
        assert result.exit_code == 0
        assert "id001" in result.output  # the published one
        assert "id000" not in result.output  # draft, excluded
        assert "id002" not in result.output  # archived, excluded

    def test_list_status_no_match(self, tmp_path: Path) -> None:
        """--status filter that matches nothing shows 'No projects found'."""
        proj_dir = tmp_path / "20260707_proj"
        proj_dir.mkdir()
        info = {"project_id": "abc", "topic": "T", "brand": "B", "status": "draft"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = runner.invoke(
            app, ["projects", "list", "--base-dir", str(tmp_path), "--status", "published"]
        )
        assert result.exit_code == 0
        assert "No projects found" in result.output

    def test_list_nonexistent_base_dir(self, tmp_path: Path) -> None:
        """Non-existent base_dir shows no projects (Path.glob handles it)."""
        result = runner.invoke(app, ["projects", "list", "--base-dir", str(tmp_path / "nonexistent")])
        assert result.exit_code == 0
        assert "No projects found" in result.output

    def test_list_json_empty(self, tmp_path: Path) -> None:
        """--json projects list on empty dir returns valid JSON."""
        result = runner.invoke(app, ["--json", "projects", "list", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == 0
        assert data["items"] == []

    def test_list_json_with_projects(self, tmp_path: Path) -> None:
        """--json projects lists projects as JSON array."""
        proj_dir = tmp_path / "20260707_test"
        proj_dir.mkdir()
        info = {"project_id": "json123", "topic": "JSON Topic", "brand": "JSONBrand"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = runner.invoke(app, ["--json", "projects", "list", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == 1
        assert data["items"][0]["project_id"] == "json123"
        # _dir key should NOT be in JSON output
        assert "_dir" not in data["items"][0]

    def test_list_json_nonexistent_base_dir(self, tmp_path: Path) -> None:
        """--json projects list with non-existent base_dir returns empty JSON."""
        result = runner.invoke(
            app, ["--json", "projects", "list", "--base-dir", str(tmp_path / "nope")]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == 0


# =========================================================================
# 4. projects get
# =========================================================================


class TestProjectsGet:
    """Tests for ``automedia projects get``."""

    def _create_project(self, base_dir: Path, project_id: str = "abc123") -> dict[str, Any]:
        """Helper to create a project directory and return its info."""
        proj_dir = base_dir / "20260707_test"
        proj_dir.mkdir()
        info = {
            "project_id": project_id,
            "topic": "Test Topic",
            "brand": "TestBrand",
            "tenant_id": "default",
            "created_at": "2026-07-07T00:00:00+00:00",
        }
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")
        return info

    def test_get_found(self, tmp_path: Path) -> None:
        """Getting an existing project returns its info."""
        self._create_project(tmp_path)
        result = runner.invoke(app, ["projects", "get", "abc123", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["project_id"] == "abc123"
        assert data["topic"] == "Test Topic"

    def test_get_not_found(self, tmp_path: Path) -> None:
        """Getting a nonexistent project returns error."""
        self._create_project(tmp_path, "abc123")
        result = runner.invoke(app, ["projects", "get", "nonexistent", "--base-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_get_nonexistent_base_dir(self, tmp_path: Path) -> None:
        """Non-existent base_dir shows 'not found' (no projects discovered)."""
        result = runner.invoke(
            app, ["projects", "get", "abc123", "--base-dir", str(tmp_path / "nope")]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_get_json_found(self, tmp_path: Path) -> None:
        """--json projects get returns project as JSON."""
        self._create_project(tmp_path)
        result = runner.invoke(
            app, ["--json", "projects", "get", "abc123", "--base-dir", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["project_id"] == "abc123"
        assert "_dir" not in data

    def test_get_json_not_found(self, tmp_path: Path) -> None:
        """--json projects get with bad ID returns JSON error."""
        self._create_project(tmp_path)
        result = runner.invoke(
            app, ["--json", "projects", "get", "nonexistent", "--base-dir", str(tmp_path)]
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_get_json_invalid_base_dir(self, tmp_path: Path) -> None:
        """--json projects get with invalid base_dir returns JSON error."""
        result = runner.invoke(
            app, ["--json", "projects", "get", "abc123", "--base-dir", str(tmp_path / "nope")]
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"


# =========================================================================
# 5. projects get-assets
# =========================================================================


class TestProjectsGetAssets:
    """Tests for ``automedia projects get-assets``."""

    def _create_project_with_assets(self, base_dir: Path) -> dict[str, Any]:
        """Helper to create project dir with asset files."""
        project_id = "asset_proj_001"
        proj_dir = base_dir / "20260708_asset-topic"
        proj_dir.mkdir()
        info = {"project_id": project_id, "topic": "Asset Topic", "brand": "AssetBrand"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        (proj_dir / "01_content").mkdir()
        (proj_dir / "02_images").mkdir()
        (proj_dir / "03_video").mkdir()

        (proj_dir / "01_content" / "article.md").write_text("# Article")
        (proj_dir / "02_images" / "cover.png").write_bytes(b"\x89PNG\x0d\x0a")
        (proj_dir / "03_video" / "clip.mp4").write_bytes(b"\x00\x00\x00\x00moov")

        return {"base_dir": str(base_dir), "project_id": project_id}

    def _create_project_no_assets(self, base_dir: Path) -> dict[str, Any]:
        """Helper to create project dir without asset files."""
        project_id = "empty_proj_002"
        proj_dir = base_dir / "20260709_empty"
        proj_dir.mkdir()
        info = {"project_id": project_id, "topic": "Empty", "brand": "B"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")
        # Create asset subdirs but no files in them
        for subdir in _ASSET_SUBDIRS:
            (proj_dir / subdir).mkdir(parents=True, exist_ok=True)
        return {"base_dir": str(base_dir), "project_id": project_id}

    def test_get_assets_found(self, tmp_path: Path) -> None:
        """Existing project returns its assets."""
        proj = self._create_project_with_assets(tmp_path)
        result = runner.invoke(
            app, ["projects", "get-assets", proj["project_id"], "--base-dir", proj["base_dir"]]
        )
        assert result.exit_code == 0
        assets = json.loads(result.output)
        assert isinstance(assets, list)
        names = {a["name"] for a in assets}
        assert "article.md" in names
        assert "cover.png" in names
        assert "clip.mp4" in names

    def test_get_assets_not_found(self, tmp_path: Path) -> None:
        """Getting assets for a nonexistent project returns error."""
        self._create_project_with_assets(tmp_path)
        result = runner.invoke(
            app, ["projects", "get-assets", "nonexistent", "--base-dir", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_get_assets_nonexistent_base_dir(self, tmp_path: Path) -> None:
        """Non-existent base_dir shows 'not found' (no projects discovered)."""
        result = runner.invoke(
            app, ["projects", "get-assets", "abc123", "--base-dir", str(tmp_path / "nope")]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_get_assets_empty_project(self, tmp_path: Path) -> None:
        """Project with empty asset subdirs returns empty list."""
        proj = self._create_project_no_assets(tmp_path)
        result = runner.invoke(
            app, ["projects", "get-assets", proj["project_id"], "--base-dir", proj["base_dir"]]
        )
        assert result.exit_code == 0
        assets = json.loads(result.output)
        assert isinstance(assets, list)
        assert len(assets) == 0

    def test_get_assets_json(self, tmp_path: Path) -> None:
        """--json projects get-assets returns JSON with status/items/count."""
        proj = self._create_project_with_assets(tmp_path)
        result = runner.invoke(
            app,
            ["--json", "projects", "get-assets", proj["project_id"], "--base-dir", proj["base_dir"]],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] >= 3
        names = {a["name"] for a in data["items"]}
        assert "article.md" in names
        assert "cover.png" in names
        assert "clip.mp4" in names

    def test_get_assets_json_empty(self, tmp_path: Path) -> None:
        """--json projects get-assets on empty project returns JSON with count 0."""
        proj = self._create_project_no_assets(tmp_path)
        result = runner.invoke(
            app,
            ["--json", "projects", "get-assets", proj["project_id"], "--base-dir", proj["base_dir"]],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == 0

    def test_get_assets_json_not_found(self, tmp_path: Path) -> None:
        """--json projects get-assets with bad ID returns JSON error."""
        self._create_project_with_assets(tmp_path)
        result = runner.invoke(
            app, ["--json", "projects", "get-assets", "nonexistent", "--base-dir", str(tmp_path)]
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"


# =========================================================================
# 6. Edge cases and integration
# =========================================================================


class TestProjectsEdgeCases:
    """Edge cases for projects commands."""

    def test_list_with_missing_info_fields(self, tmp_path: Path) -> None:
        """Projects missing optional fields still display."""
        proj_dir = tmp_path / "20260707_test"
        proj_dir.mkdir()
        # Minimal info — missing brand, status, etc.
        info = {"project_id": "minimal123"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        result = runner.invoke(app, ["projects", "list", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "minimal123" in result.output

    def test_get_assets_with_file_in_nested_subdir(self, tmp_path: Path) -> None:
        """Files in nested subdirectories are discovered."""
        proj_dir = tmp_path / "20260710_nested"
        proj_dir.mkdir()
        info = {"project_id": "nested001", "topic": "Nested", "brand": "B"}
        (proj_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

        # Create nested content
        (proj_dir / "01_content" / "drafts").mkdir(parents=True)
        (proj_dir / "01_content" / "drafts" / "draft_v1.md").write_text("# V1")
        (proj_dir / "01_content" / "drafts" / "draft_v2.md").write_text("# V2")

        result = runner.invoke(
            app, ["projects", "get-assets", "nested001", "--base-dir", str(tmp_path)]
        )
        assert result.exit_code == 0
        assets = json.loads(result.output)
        assert len(assets) == 2
        names = {a["name"] for a in assets}
        assert "draft_v1.md" in names
        assert "draft_v2.md" in names

    def test_command_help_shows_subcommands(self) -> None:
        """``automedia projects --help`` lists all sub-commands."""
        result = runner.invoke(app, ["projects", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "get" in result.output
        assert "get-assets" in result.output

    def test_help_is_registered_in_main_app(self) -> None:
        """The projects command appears in the main app's help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "projects" in result.output
        assert "List and inspect media projects" in result.output


# =========================================================================
# 7. Error handling — _discover_projects raises
# =========================================================================


class TestProjectsErrorHandling:
    """Force the ``except Exception`` branches in commands."""

    def test_list_discovery_error(self, tmp_path: Path) -> None:
        """projects list shows error when _discover_projects raises."""
        with patch("automedia.cli.commands.projects._discover_projects") as mock:
            mock.side_effect = RuntimeError("boom")
            result = runner.invoke(
                app, ["projects", "list", "--base-dir", str(tmp_path)]
            )
        assert result.exit_code == 1
        assert "Error scanning projects" in result.output

    def test_list_json_discovery_error(self, tmp_path: Path) -> None:
        """--json projects list returns JSON error when discovery fails."""
        with patch("automedia.cli.commands.projects._discover_projects") as mock:
            mock.side_effect = RuntimeError("boom")
            result = runner.invoke(
                app, ["--json", "projects", "list", "--base-dir", str(tmp_path)]
            )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_get_discovery_error(self, tmp_path: Path) -> None:
        """projects get shows error when _discover_projects raises."""
        with patch("automedia.cli.commands.projects._discover_projects") as mock:
            mock.side_effect = RuntimeError("boom")
            result = runner.invoke(
                app, ["projects", "get", "abc123", "--base-dir", str(tmp_path)]
            )
        assert result.exit_code == 1
        assert "Error scanning projects" in result.output

    def test_get_json_discovery_error(self, tmp_path: Path) -> None:
        """--json projects get returns JSON error when discovery fails."""
        with patch("automedia.cli.commands.projects._discover_projects") as mock:
            mock.side_effect = RuntimeError("boom")
            result = runner.invoke(
                app, ["--json", "projects", "get", "abc123", "--base-dir", str(tmp_path)]
            )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_get_assets_discovery_error(self, tmp_path: Path) -> None:
        """projects get-assets shows error when _discover_projects raises."""
        with patch("automedia.cli.commands.projects._discover_projects") as mock:
            mock.side_effect = RuntimeError("boom")
            result = runner.invoke(
                app, ["projects", "get-assets", "abc123", "--base-dir", str(tmp_path)]
            )
        assert result.exit_code == 1
        assert "Error scanning projects" in result.output

    def test_get_assets_json_discovery_error(self, tmp_path: Path) -> None:
        """--json projects get-assets returns JSON error when discovery fails."""
        with patch("automedia.cli.commands.projects._discover_projects") as mock:
            mock.side_effect = RuntimeError("boom")
            result = runner.invoke(
                app, ["--json", "projects", "get-assets", "abc123", "--base-dir", str(tmp_path)]
            )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
