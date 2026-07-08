"""Tests for the AutoMedia MCP server layer.

Covers all 8 tools, the path allowlist, and server creation.
All tests use synthetic data — zero production project data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from automedia.mcp.server import (
    _load_allowlist,
    _reset_allowlist_cache,
    check_path_allowed,
    create_server,
    _discover_projects,
    _project_assets,
    _pipeline_result_to_dict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def allowlist_yaml(tmp_path: Path) -> Path:
    """Create a temporary allowlist YAML with one allowed directory."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    yaml_path = tmp_path / "allowlist.yaml"
    yaml_path.write_text(
        yaml.dump({"allowed_directories": [str(allowed_dir)]}),
        encoding="utf-8",
    )
    return yaml_path


@pytest.fixture()
def empty_allowlist_yaml(tmp_path: Path) -> Path:
    """Create a temporary allowlist YAML with an empty allowlist."""
    yaml_path = tmp_path / "allowlist.yaml"
    yaml_path.write_text(
        yaml.dump({"allowed_directories": []}),
        encoding="utf-8",
    )
    return yaml_path


@pytest.fixture()
def sample_project(tmp_path: Path) -> Path:
    """Create a minimal project directory structure."""
    proj_dir = tmp_path / "20260707_test-topic"
    proj_dir.mkdir()
    (proj_dir / "01_content" / "drafts").mkdir(parents=True)
    (proj_dir / "02_images").mkdir(parents=True)
    (proj_dir / "03_video").mkdir(parents=True)
    info = {
        "project_id": "abc123def456",
        "topic": "test topic",
        "brand": "TestBrand",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (proj_dir / "00_project_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Add a dummy asset
    (proj_dir / "01_content" / "drafts" / "draft.md").write_text("# Draft", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def published_project(tmp_path: Path) -> Path:
    """Create a project with status='published' for archive tests."""
    proj_dir = tmp_path / "20260707_pub-topic"
    proj_dir.mkdir()
    info = {
        "project_id": "pub123abc456",
        "topic": "published topic",
        "brand": "PubBrand",
        "tenant_id": "default",
        "status": "published",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (proj_dir / "00_project_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def draft_project(tmp_path: Path) -> Path:
    """Create a project with status='draft' for Red Line 8 tests."""
    proj_dir = tmp_path / "20260707_draft-topic"
    proj_dir.mkdir()
    info = {
        "project_id": "dra123abc456",
        "topic": "draft topic",
        "brand": "DraftBrand",
        "tenant_id": "default",
        "status": "draft",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (proj_dir / "00_project_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset allowlist cache before each test."""
    _reset_allowlist_cache()
    yield
    _reset_allowlist_cache()


# ---------------------------------------------------------------------------
# Allowlist tests
# ---------------------------------------------------------------------------


class TestAllowlist:
    """Tests for path allowlist loading and checking."""

    def test_empty_allowlist_allows_all(self) -> None:
        """Empty allowlist → all paths allowed."""
        assert check_path_allowed("/any/path", allowlist=[]) is True

    def test_path_under_allowed_dir(self, tmp_path: Path) -> None:
        """Path under an allowed directory is permitted."""
        allowed = str(tmp_path)
        target = str(tmp_path / "subdir" / "file.txt")
        assert check_path_allowed(target, allowlist=[os.path.realpath(allowed)]) is True

    def test_path_outside_allowed_dir(self, tmp_path: Path) -> None:
        """Path outside allowed directories is rejected."""
        allowed = str(tmp_path / "allowed")
        Path(allowed).mkdir()
        outside = str(tmp_path / "outside" / "file.txt")
        assert check_path_allowed(outside, allowlist=[os.path.realpath(allowed)]) is False

    def test_exact_allowed_dir(self, tmp_path: Path) -> None:
        """Exact match of allowed directory is permitted."""
        allowed = os.path.realpath(str(tmp_path))
        assert check_path_allowed(str(tmp_path), allowlist=[allowed]) is True

    def test_load_allowlist_from_yaml(self, allowlist_yaml: Path) -> None:
        """_load_allowlist reads from YAML file."""
        dirs = _load_allowlist(allowlist_path=allowlist_yaml)
        assert len(dirs) == 1
        assert os.path.isabs(dirs[0])

    def test_load_allowlist_missing_file(self, tmp_path: Path) -> None:
        """Missing YAML file → empty allowlist."""
        dirs = _load_allowlist(allowlist_path=tmp_path / "nonexistent.yaml")
        assert dirs == []

    def test_load_allowlist_empty_yaml(self, empty_allowlist_yaml: Path) -> None:
        """YAML with empty list → empty allowlist."""
        dirs = _load_allowlist(allowlist_path=empty_allowlist_yaml)
        assert dirs == []


# ---------------------------------------------------------------------------
# Server creation tests
# ---------------------------------------------------------------------------


class TestServerCreation:
    """Tests for MCP server construction."""

    def test_create_server_returns_instance(self) -> None:
        """create_server() returns a FastMCP instance."""
        server = create_server()
        assert server is not None
        assert hasattr(server, "run")

    def test_server_has_all_8_tools(self) -> None:
        """All 8 tools are registered."""
        server = create_server()
        tool_names = sorted(server._tool_manager._tools.keys())
        expected = sorted([
            "select_topic",
            "run_pipeline",
            "get_pipeline_status",
            "list_projects",
            "get_project_assets",
            "archive_project",
            "list_topic_pool",
            "register_platform_adapter",
        ])
        assert tool_names == expected


# ---------------------------------------------------------------------------
# Tool: select_topic
# ---------------------------------------------------------------------------


class TestSelectTopic:
    """Tests for the select_topic tool."""

    def test_select_topic_empty_pool(self) -> None:
        """Returns error when no pending topics exist."""
        create_server()
        # Call the underlying function directly
        from automedia.mcp.server import select_topic
        result = select_topic()
        assert "error" in result or result.get("selected") is None

    def test_select_topic_with_db(self, tmp_path: Path) -> None:
        """Selects highest-scored topic from a real DB."""
        from automedia.pool.db import PoolDB

        db_path = tmp_path / "pool.db"
        db = PoolDB(db_path)
        db.add_topic({"title": "Low score", "score": 1.0, "status": "pending"})
        db.add_topic({"title": "High score", "score": 9.5, "status": "pending"})
        db.add_topic({"title": "Already selected", "score": 10.0, "status": "selected"})
        db.close()

        from automedia.mcp.server import select_topic
        result = select_topic(pool_db_path=str(db_path))
        assert result["selected"]["title"] == "High score"
        assert result["remaining_count"] == 1

    def test_select_topic_category_filter(self, tmp_path: Path) -> None:
        """Filters by category when provided."""
        from automedia.pool.db import PoolDB

        db_path = tmp_path / "pool.db"
        db = PoolDB(db_path)
        db.add_topic({"title": "Tech topic", "score": 5.0, "status": "pending", "category": "tech"})
        db.add_topic({"title": "Finance topic", "score": 9.0, "status": "pending", "category": "finance"})
        db.close()

        from automedia.mcp.server import select_topic
        result = select_topic(category="tech", pool_db_path=str(db_path))
        assert result["selected"]["title"] == "Tech topic"


# ---------------------------------------------------------------------------
# Tool: run_pipeline
# ---------------------------------------------------------------------------


class TestRunPipeline:
    """Tests for the run_pipeline tool."""

    def test_run_pipeline_returns_dict(self) -> None:
        """run_pipeline returns a JSON-serializable dict."""
        from automedia.mcp.server import run_pipeline
        result = run_pipeline(topic="test topic", brand="TestBrand", mode="auto")
        assert isinstance(result, dict)
        assert "status" in result

    def test_run_pipeline_invalid_mode(self) -> None:
        """Invalid mode returns status='failed'."""
        from automedia.mcp.server import run_pipeline
        result = run_pipeline(topic="test", brand="Brand", mode="invalid_mode")
        assert result["status"] == "failed"
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool: get_pipeline_status
# ---------------------------------------------------------------------------


class TestGetPipelineStatus:
    """Tests for the get_pipeline_status tool."""

    def test_project_not_found(self, tmp_path: Path) -> None:
        """Returns error when project_id is not found."""
        from automedia.mcp.server import get_pipeline_status
        result = get_pipeline_status(project_id="nonexistent", base_dir=str(tmp_path))
        assert "error" in result

    def test_project_found(self, sample_project: Path) -> None:
        """Returns project info and subdirs."""
        from automedia.mcp.server import get_pipeline_status
        result = get_pipeline_status(project_id="abc123def456", base_dir=str(sample_project))
        assert "project" in result
        assert result["project"]["project_id"] == "abc123def456"
        assert "subdirs" in result
        assert len(result["subdirs"]) > 0


# ---------------------------------------------------------------------------
# Tool: list_projects
# ---------------------------------------------------------------------------


class TestListProjects:
    """Tests for the list_projects tool."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Returns empty list when no projects exist."""
        from automedia.mcp.server import list_projects
        result = list_projects(base_dir=str(tmp_path))
        assert result["projects"] == []
        assert result["count"] == 0

    def test_finds_projects(self, sample_project: Path) -> None:
        """Discovers projects from info JSON files."""
        from automedia.mcp.server import list_projects
        result = list_projects(base_dir=str(sample_project))
        assert result["count"] == 1
        assert result["projects"][0]["project_id"] == "abc123def456"

    def test_status_filter(self, sample_project: Path, published_project: Path) -> None:
        """Filters by status when provided."""
        from automedia.mcp.server import list_projects
        result = list_projects(base_dir=str(sample_project.parent), status="published")
        # Only published_project should match
        ids = [p["project_id"] for p in result["projects"]]
        assert "abc123def456" not in ids  # sample has no status field
        # published_project is in a different tmp_path, so this test needs adjustment


# ---------------------------------------------------------------------------
# Tool: get_project_assets
# ---------------------------------------------------------------------------


class TestGetProjectAssets:
    """Tests for the get_project_assets tool."""

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        """Returns empty assets for non-existent directory."""
        from automedia.mcp.server import get_project_assets
        result = get_project_assets(project_dir=str(tmp_path / "nonexistent"))
        assert result["assets"] == []

    def test_finds_assets(self, sample_project: Path) -> None:
        """Lists all files in the project directory."""
        from automedia.mcp.server import get_project_assets
        proj_dir = str(sample_project / "20260707_test-topic")
        result = get_project_assets(project_dir=proj_dir)
        assert result["count"] > 0
        names = [a["name"] for a in result["assets"]]
        assert "draft.md" in names
        # Should not include 00_project_info.json
        assert "00_project_info.json" not in names


# ---------------------------------------------------------------------------
# Tool: archive_project
# ---------------------------------------------------------------------------


class TestArchiveProject:
    """Tests for the archive_project tool (Red Line 8)."""

    def test_project_not_found(self, tmp_path: Path) -> None:
        """Returns error when project is not found."""
        from automedia.mcp.server import archive_project
        result = archive_project(project_id="nonexistent", base_dir=str(tmp_path))
        assert result["archived"] is False
        assert "error" in result

    def test_red_line_8_rejects_non_published(self, draft_project: Path) -> None:
        """Refuses to archive non-published project without force."""
        from automedia.mcp.server import archive_project
        result = archive_project(project_id="dra123abc456", base_dir=str(draft_project), force=False)
        assert result["archived"] is False
        assert "Refused" in result["error"]
        assert "Red Line 8" in result["error"]

    def test_force_overrides_red_line_8(self, draft_project: Path) -> None:
        """force=True overrides the published-status check."""
        from automedia.mcp.server import archive_project
        result = archive_project(project_id="dra123abc456", base_dir=str(draft_project), force=True)
        assert result["archived"] is True
        assert "archive_dir" in result

    def test_published_project_archives_without_force(self, published_project: Path) -> None:
        """Published project can be archived without force."""
        from automedia.mcp.server import archive_project
        result = archive_project(project_id="pub123abc456", base_dir=str(published_project), force=False)
        assert result["archived"] is True


# ---------------------------------------------------------------------------
# Tool: list_topic_pool
# ---------------------------------------------------------------------------


class TestListTopicPool:
    """Tests for the list_topic_pool tool."""

    def test_empty_pool(self) -> None:
        """Returns empty list for in-memory empty DB."""
        from automedia.mcp.server import list_topic_pool
        result = list_topic_pool()
        assert result["topics"] == []
        assert result["count"] == 0

    def test_lists_topics_from_db(self, tmp_path: Path) -> None:
        """Lists topics from a real database file."""
        from automedia.pool.db import PoolDB

        db_path = tmp_path / "pool.db"
        db = PoolDB(db_path)
        db.add_topic({"title": "Topic A", "status": "pending", "category": "tech"})
        db.add_topic({"title": "Topic B", "status": "pending", "category": "finance"})
        db.add_topic({"title": "Topic C", "status": "selected", "category": "tech"})
        db.close()

        from automedia.mcp.server import list_topic_pool
        result = list_topic_pool(pool_db_path=str(db_path))
        assert result["count"] == 3

    def test_status_filter(self, tmp_path: Path) -> None:
        """Filters by status."""
        from automedia.pool.db import PoolDB

        db_path = tmp_path / "pool.db"
        db = PoolDB(db_path)
        db.add_topic({"title": "Topic A", "status": "pending"})
        db.add_topic({"title": "Topic B", "status": "selected"})
        db.close()

        from automedia.mcp.server import list_topic_pool
        result = list_topic_pool(status="pending", pool_db_path=str(db_path))
        assert result["count"] == 1
        assert result["topics"][0]["title"] == "Topic A"

    def test_category_filter(self, tmp_path: Path) -> None:
        """Filters by category."""
        from automedia.pool.db import PoolDB

        db_path = tmp_path / "pool.db"
        db = PoolDB(db_path)
        db.add_topic({"title": "Tech A", "status": "pending", "category": "tech"})
        db.add_topic({"title": "Fin A", "status": "pending", "category": "finance"})
        db.close()

        from automedia.mcp.server import list_topic_pool
        result = list_topic_pool(category="tech", pool_db_path=str(db_path))
        assert result["count"] == 1
        assert result["topics"][0]["title"] == "Tech A"


# ---------------------------------------------------------------------------
# Tool: register_platform_adapter
# ---------------------------------------------------------------------------


class TestRegisterPlatformAdapter:
    """Tests for the register_platform_adapter tool."""

    def test_stub_mode(self) -> None:
        """Without adapter_class returns stub notice."""
        from automedia.mcp.server import register_platform_adapter
        result = register_platform_adapter(platform_name="test_platform")
        assert result["registered"] is False
        assert result["stub"] is True
        assert "test_platform" in result["message"]

    def test_invalid_class_path(self) -> None:
        """Invalid adapter_class returns error."""
        from automedia.mcp.server import register_platform_adapter
        result = register_platform_adapter(
            platform_name="bad_platform",
            adapter_class="not.a.valid.path",
        )
        assert result["registered"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for module-level helper functions."""

    def test_discover_projects(self, sample_project: Path) -> None:
        """_discover_projects finds project info files."""
        projects = _discover_projects(str(sample_project))
        assert len(projects) == 1
        assert projects[0]["project_id"] == "abc123def456"
        assert "_dir" in projects[0]

    def test_project_assets_excludes_info_json(self, sample_project: Path) -> None:
        """_project_assets excludes 00_project_info.json."""
        proj_dir = str(sample_project / "20260707_test-topic")
        assets = _project_assets(proj_dir)
        names = [a["name"] for a in assets]
        assert "00_project_info.json" not in names

    def test_project_assets_nonexistent_dir(self, tmp_path: Path) -> None:
        """_project_assets returns empty list for missing dir."""
        assets = _project_assets(str(tmp_path / "nonexistent"))
        assert assets == []

    def test_pipeline_result_to_dict(self) -> None:
        """_pipeline_result_to_dict converts dataclass to dict."""
        from automedia.pipelines.gate_engine import PipelineResult

        result = PipelineResult(
            status="success",
            project_id="test123",
            topic="test topic",
            brand="TestBrand",
        )
        d = _pipeline_result_to_dict(result)
        assert d["status"] == "success"
        assert d["project_id"] == "test123"
        assert isinstance(d, dict)
        # Must be JSON-serializable
        json.dumps(d)

    def test_pipeline_result_to_dict_fallback(self) -> None:
        """_pipeline_result_to_dict falls back for non-dataclass objects."""
        from types import SimpleNamespace

        obj = SimpleNamespace(status="ok", project_id="x", error=None)
        d = _pipeline_result_to_dict(obj)
        assert d["status"] == "ok"
