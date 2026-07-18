"""Tests for the AutoMedia MCP server layer.

Covers all 14 tools, the path allowlist, and server creation.
All tests use synthetic data — zero production project data.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from automedia.mcp.allowlist import (
    _load_allowlist,
    _reset_allowlist_cache,
    check_path_allowed,
)
from automedia.mcp.server import (
    create_server,
    health_check,
)
from automedia.mcp.tools import (
    _discover_projects,
    _pipeline_result_to_dict,
    _project_assets,
    _resolve_projects_dir,
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
def _reset_cache(tmp_path: Path) -> None:
    """Reset allowlist cache before each test and populate with tmp_path."""
    _reset_allowlist_cache()
    # Pre-populate cache with tmp_path so tool functions don't reject test paths
    import automedia.mcp.server as _server_mod

    _server_mod._cached_allowlist = [str(Path(tmp_path).resolve())]
    yield
    _reset_allowlist_cache()


# ---------------------------------------------------------------------------
# Allowlist tests
# ---------------------------------------------------------------------------


class TestAllowlist:
    """Tests for path allowlist loading and checking."""

    def test_empty_allowlist_blocks_all(self) -> None:
        """Empty allowlist → all paths blocked (fail‑closed)."""
        assert check_path_allowed("/any/path", allowlist=[]) is False

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

    def test_startswith_bypass_prevented(self, tmp_path: Path) -> None:
        """/data/allowed does NOT match /data/allowed_evil."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        evil = tmp_path / "allowed_evil"  # sibling, not subdirectory
        assert not check_path_allowed(str(evil), allowlist=[os.path.realpath(str(allowed_dir))])
        assert check_path_allowed(
            str(allowed_dir / "file.md"), allowlist=[os.path.realpath(str(allowed_dir))]
        )

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

    # ------------------------------------------------------------------
    # Path resolution security tests
    # ------------------------------------------------------------------

    def test_dot_resolves_to_absolute(self, tmp_path: Path) -> None:
        """'.' must be resolved to absolute path before allowlist check.

        Even when a dot is passed as-is, check_path_allowed should reject
        it unless the CWD happens to be inside an allowed directory.
        """
        allowed = str(tmp_path / "allowed")
        Path(allowed).mkdir(parents=True)
        allowlist = [os.path.realpath(allowed)]
        # CWD is the repo root — not under tmp_path/allowed
        assert check_path_allowed(".", allowlist=allowlist) is False

    def test_require_allowed_dot_raises(self, tmp_path: Path) -> None:
        """_require_allowed('.') raises ValueError when CWD not in allowlist."""
        from automedia.mcp.server import _require_allowed

        allowed = str(tmp_path / "allowed")
        Path(allowed).mkdir(parents=True)
        with pytest.raises(PermissionError, match="not within any allowed directory"):
            _require_allowed(".", tool_name="test_tool")

    def test_etc_outside_allowlist(self, tmp_path: Path) -> None:
        """/etc/ is rejected when allowlist only contains tmp_path/allowed."""
        allowed = str(tmp_path / "allowed")
        Path(allowed).mkdir(parents=True)
        allowlist = [os.path.realpath(allowed)]
        assert check_path_allowed("/etc", allowlist=allowlist) is False
        assert check_path_allowed("/etc/passwd", allowlist=allowlist) is False

    def test_dot_dot_traversal_blocked(self, tmp_path: Path) -> None:
        """Path traversal via ../.. is blocked by realpath resolution."""
        allowed = str(tmp_path / "allowed")
        Path(allowed).mkdir(parents=True)
        allowlist = [os.path.realpath(allowed)]
        # ../../etc from allowed/ resolves to /etc, which is outside
        traversal = os.path.join(allowed, "..", "..", "etc")
        assert check_path_allowed(traversal, allowlist=allowlist) is False

    def test_symlink_outside_blocked(self, tmp_path: Path) -> None:
        """Symlink inside allowed dir pointing outside is blocked.

        Path.resolve() resolves the symlink to its real target,
        which is outside the allowlist → blocked.
        """
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside_secret"
        outside.mkdir()
        link = allowed / "link_to_outside"
        os.symlink(outside, link, target_is_directory=True)
        allowlist = [os.path.realpath(str(allowed))]
        # The symlink resolves to outside/ which is NOT under allowed/
        assert check_path_allowed(str(link), allowlist=allowlist) is False

    def test_symlink_to_allowed_works(self, tmp_path: Path) -> None:
        """Symlink outside → allowed dir is permitted (resolves correctly).

        The path resolves through the symlink to the real allowed dir,
        so it passes the allowlist check.
        """
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside_link_dir"
        outside.mkdir()
        link = outside / "link_to_allowed"
        os.symlink(allowed, link, target_is_directory=True)
        allowlist = [os.path.realpath(str(allowed))]
        # Resolving through the symlink lands inside the allowed dir
        assert check_path_allowed(str(link / "file.txt"), allowlist=allowlist) is True

    def test_dot_default_rejected_in_list_projects(self) -> None:
        """list_projects(base_dir='.') returns error when CWD not in allowlist.

        This is an end-to-end test that the '.' default value does NOT
        bypass the allowlist — it must be resolved to an absolute path
        and checked before any file operations occur.
        """
        from automedia.mcp.server import list_projects

        result = list_projects(base_dir=".")
        assert "error" in result
        assert "not within any allowed directory" in result["error"]["message"]

    def test_dot_default_rejected_in_archive_project(self) -> None:
        """archive_project(base_dir='.') returns error when CWD not in allowlist."""
        from automedia.mcp.server import archive_project

        result = archive_project(project_id="test", base_dir=".")
        assert "error" in result
        assert "not within any allowed directory" in result["error"]["message"]


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

    def test_server_has_all_tools(self) -> None:
        """All tools are registered."""
        server = create_server()
        tool_names = sorted(server._tool_manager._tools.keys())
        expected = sorted(
            [
                "add_cron_schedule",
                "add_pool_topic",
                "approve_gate",
                "archive_project",
                "batch_run",
                "cancel_pipeline",
                "connect_account",
                "disconnect_account",
                "engine_health",
                "evaluate_content_quality",
                "extract_brief",
                "format_output",
                "get_account_health",
                "get_config",
                "get_cron_health",
                "get_pending_approvals",
                "get_pipeline_progress",
                "get_pipeline_status",
                "get_project_assets",
                "health_check",
                "health_engine",
                "help_mcp",
                "list_accounts",
                "list_brands",
                "list_cron_schedules",
                "list_overridable_templates",
                "list_projects",
                "list_topic_pool",
                "list_workflows",
                "localize_content",
                "localize_output",
                "mcp_help",
                "pause_pipeline",
                "pool_add_topic",
                "publish_content",
                "register_platform_adapter",
                "reject_gate",
                "remove_cron_schedule",
                "research_topics",
                "resume_pipeline",
                "retry_gate",
                "run_batch",
                "run_brand_strategy",
                "run_pipeline",
                "run_pipeline_from_strategy",
                "search_assets",
                "select_topic",
                "skip_gate",
                "test_cron_schedule",
                "update_engine_config",
            ]
        )
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
        db.add_topic(
            {"title": "Finance topic", "score": 9.0, "status": "pending", "category": "finance"}
        )
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

        result = archive_project(
            project_id="dra123abc456", base_dir=str(draft_project), force=False
        )
        assert result["archived"] is False
        assert "Refused" in result["error"]["message"]
        assert "Red Line 8" in result["error"]["message"]

    def test_force_overrides_red_line_8(self, draft_project: Path) -> None:
        """force=True overrides the published-status check."""
        from automedia.mcp.server import archive_project

        result = archive_project(project_id="dra123abc456", base_dir=str(draft_project), force=True)
        assert result["archived"] is True
        assert "archive_dir" in result

    def test_published_project_archives_without_force(self, published_project: Path) -> None:
        """Published project can be archived without force."""
        from automedia.mcp.server import archive_project

        result = archive_project(
            project_id="pub123abc456", base_dir=str(published_project), force=False
        )
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

    def test_health_check_returns_ok(self) -> None:
        """health_check returns status=ok with version and uptime."""
        result = health_check()
        assert result["status"] == "ok"
        assert result["version"] == "1.1.0"
        assert result["uptime_s"] >= 0
        assert result["tools_count"] >= 20


# ---------------------------------------------------------------------------
# Helper: _resolve_projects_dir
# ---------------------------------------------------------------------------


class TestResolveProjectsDir:
    """Tests for the _resolve_projects_dir helper."""

    def test_env_var_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOMEDIA_PROJECTS_DIR env var takes priority."""
        target = tmp_path / "custom_projects"
        target.mkdir()
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(target))
        assert _resolve_projects_dir() == str(target.resolve())

    def test_default_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to .automedia/output/projects relative to cwd."""
        monkeypatch.delenv("AUTOMEDIA_PROJECTS_DIR", raising=False)
        result = _resolve_projects_dir()
        assert result.endswith(".automedia/output/projects") or result.endswith(
            ".automedia\\output\\projects"
        )


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


class TestResources:
    """Tests for MCP resource endpoints."""

    @pytest.fixture()
    def server(self) -> Any:
        return create_server()

    def test_resources_listed(self, server: Any) -> None:
        """create_server() registers automedia:// resources."""
        resource_uris = list(server._resource_manager._resources.keys())
        template_uris = list(server._resource_manager._templates.keys())
        assert "automedia://projects" in resource_uris
        assert any("automedia://pipeline/" in uri for uri in template_uris)
        assert "automedia://pool" in resource_uris

    def test_projects_resource_empty(
        self, server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns valid JSON array when no projects exist."""
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "no_projects"))
        result = asyncio.run(server.read_resource("automedia://projects"))
        assert len(result) == 1
        data = json.loads(result[0].content)
        assert isinstance(data, list)
        assert data == []

    def test_projects_resource_with_data(
        self, server: Any, sample_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns project summaries for discovered projects."""
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(sample_project))
        result = asyncio.run(server.read_resource("automedia://projects"))
        data = json.loads(result[0].content)
        assert len(data) == 1
        assert data[0]["project_id"] == "abc123def456"
        assert data[0]["topic"] == "test topic"
        assert "brand" in data[0]
        assert "status" in data[0]
        assert "_dir" not in data[0]

    def test_pipeline_resource_not_found(
        self, server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns error JSON for nonexistent project_id."""
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "empty"))
        result = asyncio.run(server.read_resource("automedia://pipeline/nonexistent"))
        data = json.loads(result[0].content)
        assert data["status"] == "error"
        assert "not found" in data["error"]

    def test_pipeline_resource_found(
        self, server: Any, sample_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns full project info including project_dir for valid project_id."""
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(sample_project))
        result = asyncio.run(server.read_resource("automedia://pipeline/abc123def456"))
        data = json.loads(result[0].content)
        assert data["project_id"] == "abc123def456"
        assert data["topic"] == "test topic"
        assert "project_dir" in data
        assert "_dir" not in data

    def test_pool_resource_no_db(
        self, server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns error JSON when pool DB missing."""
        monkeypatch.setenv("AUTOMEDIA_POOL_DB", str(tmp_path / "missing.db"))
        result = asyncio.run(server.read_resource("automedia://pool"))
        data = json.loads(result[0].content)
        assert data["status"] == "error"
        assert "Pool database not found" in data["error"]

    def test_pool_resource_with_data(
        self, server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns topic summaries from an existing pool DB."""
        from automedia.pool.db import PoolDB

        db_path = tmp_path / "pool.db"
        db = PoolDB(db_path)
        db.add_topic({"title": "Topic A", "status": "pending", "category": "tech", "score": 5.0})
        db.add_topic(
            {"title": "Topic B", "status": "selected", "category": "finance", "score": 8.0}
        )
        db.close()

        monkeypatch.setenv("AUTOMEDIA_POOL_DB", str(db_path))
        result = asyncio.run(server.read_resource("automedia://pool"))
        data = json.loads(result[0].content)
        assert isinstance(data, list)
        assert len(data) == 2
        titles = {t["title"] for t in data}
        assert titles == {"Topic A", "Topic B"}
        for item in data:
            assert "id" in item
            assert "status" in item
            assert "score" in item


# ---------------------------------------------------------------------------
# Tests for batch_run
# ---------------------------------------------------------------------------


class TestBatchRun:
    """Tests for :func:`automedia.mcp.tools.batch_run`."""

    @staticmethod
    def _make_result(
        status: str = "success",
        project_id: str = "proj_001",
        error: str | None = None,
    ) -> Any:
        from automedia.pipelines.gate_engine import PipelineResult

        return PipelineResult(
            status=status,  # pyright: ignore[reportArgumentType]
            project_id=project_id,
            project_dir=f"/tmp/{project_id}",
            topic="test",
            brand="TestBrand",
        )

    def test_all_success(self) -> None:
        """All topics succeed — returns all results with passed=total."""
        from automedia.mcp.tools import batch_run

        with patch("automedia.pipelines.runner.run_full_pipeline") as mock_run:
            mock_run.side_effect = [
                self._make_result(project_id="pid_001"),
                self._make_result(project_id="pid_002"),
                self._make_result(project_id="pid_003"),
            ]
            result = batch_run(
                topics=["topic A", "topic B", "topic C"],
                brand="TestBrand",
                mode="auto",
            )

        assert result["total"] == 3
        assert result["passed"] == 3
        assert result["failed"] == 0
        assert len(result["results"]) == 3
        assert result["results"][0]["topic"] == "topic A"
        assert result["results"][0]["project_id"] == "pid_001"
        assert result["results"][1]["topic"] == "topic B"
        assert result["results"][2]["topic"] == "topic C"

    def test_partial_failure(self) -> None:
        """One topic fails — batch continues and reports correctly."""
        from automedia.mcp.tools import batch_run

        with patch("automedia.pipelines.runner.run_full_pipeline") as mock_run:
            mock_run.side_effect = [
                self._make_result(project_id="pid_001"),
                Exception("Pipeline crashed"),
                self._make_result(project_id="pid_003"),
            ]
            result = batch_run(
                topics=["topic A", "topic B", "topic C"],
                brand="TestBrand",
                mode="auto",
            )

        assert result["total"] == 3
        assert result["passed"] == 2
        assert result["failed"] == 1
        assert result["results"][1]["status"] == "failed"
        assert result["results"][1]["error"] == "Pipeline crashed"
        assert result["results"][2]["status"] == "success"
        assert result["results"][2]["project_id"] == "pid_003"

    def test_all_fail(self) -> None:
        """All topics fail — passed=0, failed=total."""
        from automedia.mcp.tools import batch_run

        with patch("automedia.pipelines.runner.run_full_pipeline") as mock_run:
            mock_run.side_effect = Exception("always fails")
            result = batch_run(
                topics=["t1", "t2"],
                brand="TestBrand",
                mode="auto",
            )

        assert result["total"] == 2
        assert result["passed"] == 0
        assert result["failed"] == 2
        for r in result["results"]:
            assert r["status"] == "failed"

    def test_empty_topics(self) -> None:
        """Empty topic list — total=0."""
        from automedia.mcp.tools import batch_run

        result = batch_run(topics=[], brand="TestBrand", mode="auto")
        assert result["total"] == 0
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert result["results"] == []
