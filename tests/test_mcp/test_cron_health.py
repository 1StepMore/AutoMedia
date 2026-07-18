"""Tests for the MCP cron health check tool.

Covers get_cron_health with various jobs.yaml states.
All tests use temporary YAML files — zero production data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jobs_yaml(
    path: Path,
    *,
    pipeline_schedules: list[dict[str, object]] | None = None,
    static_jobs: list[dict[str, object]] | None = None,
) -> Path:
    """Create a jobs.yaml with optional pipeline_schedules and jobs."""
    data: dict[str, object] = {}
    if pipeline_schedules is not None:
        data["pipeline_schedules"] = pipeline_schedules
    if static_jobs is not None:
        data["jobs"] = static_jobs
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def jobs_yaml_path(tmp_path: Path) -> Path:
    """Create an empty jobs.yaml in a temp directory."""
    return _make_jobs_yaml(tmp_path / "jobs.yaml")


@pytest.fixture(autouse=True)
def _patch_jobs_yaml_path(
    jobs_yaml_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect tools._get_jobs_yaml_path to the test path."""
    import automedia.mcp.tools as tools_mod

    monkeypatch.setattr(tools_mod, "_get_jobs_yaml_path", lambda: jobs_yaml_path)


# ---------------------------------------------------------------------------
# Tests: get_cron_health
# ---------------------------------------------------------------------------


class TestGetCronHealth:
    """Tests for get_cron_health."""

    def test_missing_file(self, tmp_path: Path) -> None:
        """Missing jobs.yaml returns not-found result."""
        import automedia.mcp.tools as tools_mod

        # Point to a non-existent path
        missing = tmp_path / "nonexistent.yaml"
        tools_mod._get_jobs_yaml_path = lambda: missing  # type: ignore[method-assign]

        from automedia.mcp.tools import get_cron_health

        result = get_cron_health()
        assert result["jobs_valid"] is False
        assert result["schedule_count"] == 0
        assert result["job_count"] == 0
        assert "not found" in result["note"]

    def test_empty_file(self) -> None:
        """Empty jobs.yaml returns valid with zeros."""
        from automedia.mcp.tools import get_cron_health

        result = get_cron_health()
        assert result["jobs_valid"] is True
        assert result["schedule_count"] == 0
        assert result["job_count"] == 0
        assert result["valid_expressions"] == 0
        assert result["invalid_expressions"] == 0
        assert result["static_jobs"] == []

    def test_with_pipeline_schedules(self) -> None:
        """Pipeline schedules are counted and expressions validated."""
        from automedia.mcp.tools import add_cron_schedule, get_cron_health

        add_cron_schedule(name="job-a", expression="0 8 * * *")
        add_cron_schedule(name="job-b", expression="30 9 * * *")
        add_cron_schedule(name="job-c", expression="*/15 * * * *")

        result = get_cron_health()
        assert result["jobs_valid"] is True
        assert result["schedule_count"] == 3
        assert result["valid_expressions"] == 3
        assert result["invalid_expressions"] == 0
        assert result["job_count"] == 0  # no static jobs defined

    def test_invalid_expressions(self) -> None:
        """Invalid cron expressions are reported (manually crafted YAML)."""
        import automedia.mcp.tools as tools_mod

        path = tools_mod._get_jobs_yaml_path()
        data = {
            "pipeline_schedules": [
                {"name": "good", "expression": "0 8 * * *"},
                {"name": "bad", "expression": "0 8 * *"},  # only 4 fields
            ],
        }
        path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        from automedia.mcp.tools import get_cron_health

        result = get_cron_health()
        assert result["schedule_count"] == 2
        assert result["valid_expressions"] == 1
        assert result["invalid_expressions"] == 1

    def test_with_static_jobs(self) -> None:
        """Static job definitions are reported."""
        import automedia.mcp.tools as tools_mod

        path = tools_mod._get_jobs_yaml_path()
        data = {
            "jobs": [
                {
                    "name": "hot-collection",
                    "schedule": "0 8 * * *",
                    "command": "automedia cron run pool-collect",
                    "description": "Daily hot topic collection",
                },
                {
                    "name": "watchdog",
                    "schedule": "30 9 * * *",
                    "command": "automedia cron check-health",
                    "description": "Daily health check",
                },
            ],
        }
        path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        from automedia.mcp.tools import get_cron_health

        result = get_cron_health()
        assert result["jobs_valid"] is True
        assert result["job_count"] == 2
        assert len(result["static_jobs"]) == 2
        names = [j["name"] for j in result["static_jobs"]]
        assert "hot-collection" in names
        assert "watchdog" in names

    def test_both_schedules_and_jobs(self) -> None:
        """Both pipeline_schedules and static jobs are reported."""
        import automedia.mcp.tools as tools_mod

        data = {
            "pipeline_schedules": [
                {"name": "sched-1", "expression": "0 8 * * *"},
            ],
            "jobs": [
                {"name": "job-1", "schedule": "30 9 * * *", "description": "Test job"},
            ],
        }
        path = tools_mod._get_jobs_yaml_path()
        path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        from automedia.mcp.tools import get_cron_health

        result = get_cron_health()
        assert result["schedule_count"] == 1
        assert result["job_count"] == 1
        assert result["valid_expressions"] == 1

    def test_parse_error(self) -> None:
        """Malformed YAML returns parse error."""
        import automedia.mcp.tools as tools_mod

        path = tools_mod._get_jobs_yaml_path()
        path.write_text("{invalid: yaml: *\n", encoding="utf-8")

        from automedia.mcp.tools import get_cron_health

        result = get_cron_health()
        assert result["jobs_valid"] is False
        assert "parse error" in result["note"]


# ---------------------------------------------------------------------------
# Tests: server registration
# ---------------------------------------------------------------------------


class TestServerRegistration:
    """Tests that get_cron_health is registered in the MCP server."""

    def test_tool_is_registered(self) -> None:
        """get_cron_health appears in the server's tool list."""
        from automedia.mcp.server import create_server

        server = create_server()
        tool_names = server._tool_manager._tools.keys()

        assert "get_cron_health" in tool_names

    def test_can_be_called_via_server_import(self) -> None:
        """get_cron_health works when called through server imports."""
        from automedia.mcp.server import get_cron_health

        result = get_cron_health()
        assert "jobs_valid" in result
        assert "schedule_count" in result
        assert "static_jobs" in result
        assert "note" in result
