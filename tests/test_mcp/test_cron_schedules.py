"""Tests for the MCP cron schedule management tools.

Covers add_cron_schedule, list_cron_schedules, and remove_cron_schedule.
All tests use temporary YAML files — zero production data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jobs_yaml(path: Path, schedules: list[dict] | None = None) -> Path:
    """Create a jobs.yaml with pipeline_schedules."""
    data: dict = {}
    if schedules is not None:
        data["pipeline_schedules"] = schedules
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
# Tests: add_cron_schedule
# ---------------------------------------------------------------------------


class TestAddCronSchedule:
    """Tests for add_cron_schedule."""

    def test_add_valid_schedule(self) -> None:
        """Add a schedule with valid cron expression."""
        from automedia.mcp.tools import add_cron_schedule

        result = add_cron_schedule(
            name="test-job",
            expression="0 8 * * *",
            brand="my-brand",
            category="tech",
            count=1,
        )
        assert result["added"] is True
        assert result["name"] == "test-job"

    def test_add_duplicate_name(self) -> None:
        """Duplicate name returns error."""
        from automedia.mcp.tools import add_cron_schedule

        add_cron_schedule(name="dup-job", expression="0 8 * * *")
        result = add_cron_schedule(name="dup-job", expression="30 9 * * *")
        assert "error" in result
        assert "already exists" in result["error"]

    def test_invalid_cron_expression(self) -> None:
        """Invalid cron expression (wrong field count) returns error."""
        from automedia.mcp.tools import add_cron_schedule

        result = add_cron_schedule(name="bad", expression="0 8 * *")  # only 4 fields
        assert "error" in result
        assert "Invalid cron expression" in result["error"]

    def test_invalid_cron_expression_six_fields(self) -> None:
        """Six-field cron expression returns error."""
        from automedia.mcp.tools import add_cron_schedule

        result = add_cron_schedule(name="bad6", expression="0 8 * * * *")  # 6 fields
        assert "error" in result
        assert "Invalid cron expression" in result["error"]

    def test_add_with_defaults(self) -> None:
        """Adding with only name and expression uses defaults."""
        from automedia.mcp.tools import add_cron_schedule

        result = add_cron_schedule(name="minimal", expression="*/5 * * * *")
        assert result["added"] is True
        assert result["name"] == "minimal"


# ---------------------------------------------------------------------------
# Tests: list_cron_schedules
# ---------------------------------------------------------------------------


class TestListCronSchedules:
    """Tests for list_cron_schedules."""

    def test_empty_list(self) -> None:
        """Returns empty list when no schedules exist."""
        from automedia.mcp.tools import list_cron_schedules

        result = list_cron_schedules()
        assert result["schedules"] == []
        assert result["count"] == 0

    def test_lists_schedules(self) -> None:
        """Returns all schedules sorted by name."""
        from automedia.mcp.tools import add_cron_schedule, list_cron_schedules

        add_cron_schedule(name="b-job", expression="30 9 * * *", brand="b-brand")
        add_cron_schedule(name="a-job", expression="0 8 * * *", brand="a-brand")

        result = list_cron_schedules()
        assert result["count"] == 2
        names = [s["name"] for s in result["schedules"]]
        assert names == ["a-job", "b-job"]  # sorted by name

    def test_fields_in_list(self) -> None:
        """Listed schedules include all fields."""
        from automedia.mcp.tools import add_cron_schedule, list_cron_schedules

        add_cron_schedule(
            name="full-job",
            expression="0 8 * * *",
            brand="my-brand",
            category="tech",
            count=3,
        )

        result = list_cron_schedules()
        entry = result["schedules"][0]
        assert entry["name"] == "full-job"
        assert entry["expression"] == "0 8 * * *"
        assert entry["brand"] == "my-brand"
        assert entry["category"] == "tech"
        assert entry["count"] == 3


# ---------------------------------------------------------------------------
# Tests: remove_cron_schedule
# ---------------------------------------------------------------------------


class TestRemoveCronSchedule:
    """Tests for remove_cron_schedule."""

    def test_remove_existing(self) -> None:
        """Remove an existing schedule."""
        from automedia.mcp.tools import add_cron_schedule, list_cron_schedules, remove_cron_schedule

        add_cron_schedule(name="remove-me", expression="0 8 * * *")
        result = remove_cron_schedule(name="remove-me")
        assert result["removed"] is True
        assert result["name"] == "remove-me"

        # Verify it's gone
        listed = list_cron_schedules()
        assert listed["count"] == 0

    def test_remove_nonexistent(self) -> None:
        """Remove a non-existent schedule returns error."""
        from automedia.mcp.tools import remove_cron_schedule

        result = remove_cron_schedule(name="i-dont-exist")
        assert "error" in result
        assert "not found" in result["error"]

    def test_remove_one_of_many(self) -> None:
        """Removing one schedule leaves others intact."""
        from automedia.mcp.tools import add_cron_schedule, list_cron_schedules, remove_cron_schedule

        add_cron_schedule(name="keep-a", expression="0 8 * * *")
        add_cron_schedule(name="remove-this", expression="30 9 * * *")
        add_cron_schedule(name="keep-b", expression="*/5 * * * *")

        remove_cron_schedule(name="remove-this")

        result = list_cron_schedules()
        assert result["count"] == 2
        names = [s["name"] for s in result["schedules"]]
        assert "keep-a" in names
        assert "keep-b" in names
        assert "remove-this" not in names


# ---------------------------------------------------------------------------
# Integration: add → list → remove → list
# ---------------------------------------------------------------------------


class TestCronScheduleIntegration:
    """End-to-end add → list → remove → list flow."""

    def test_full_lifecycle(self) -> None:
        """Add, verify with list, remove, verify with list."""
        from automedia.mcp.tools import add_cron_schedule, list_cron_schedules, remove_cron_schedule

        # Add
        add_result = add_cron_schedule(
            name="lifecycle-job",
            expression="0 8 * * *",
            brand="test-brand",
            category="tech",
            count=2,
        )
        assert add_result["added"] is True

        # List and verify
        list1 = list_cron_schedules()
        assert list1["count"] == 1
        assert list1["schedules"][0]["name"] == "lifecycle-job"
        assert list1["schedules"][0]["expression"] == "0 8 * * *"
        assert list1["schedules"][0]["brand"] == "test-brand"

        # Remove
        remove_result = remove_cron_schedule(name="lifecycle-job")
        assert remove_result["removed"] is True

        # List and verify gone
        list2 = list_cron_schedules()
        assert list2["count"] == 0

    def test_yaml_persistence(self, jobs_yaml_path: Path) -> None:
        """Schedule data persists correctly in YAML."""
        from automedia.mcp.tools import add_cron_schedule, remove_cron_schedule

        add_cron_schedule(
            name="persist-job",
            expression="0 8 * * *",
            brand="persist-brand",
            category="news",
            count=5,
        )

        # Read YAML directly to verify
        with open(jobs_yaml_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        schedules = data.get("pipeline_schedules", [])
        assert len(schedules) == 1
        assert schedules[0]["name"] == "persist-job"
        assert schedules[0]["expression"] == "0 8 * * *"
        assert schedules[0]["brand"] == "persist-brand"
        assert schedules[0]["category"] == "news"
        assert schedules[0]["count"] == 5

        # Remove and verify YAML is updated
        remove_cron_schedule(name="persist-job")
        with open(jobs_yaml_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data.get("pipeline_schedules", []) == []

    def test_preserves_existing_jobs(self, jobs_yaml_path: Path) -> None:
        """Adding pipeline_schedules preserves existing jobs key."""
        # Write initial YAML with jobs
        import yaml

        initial_data = {
            "jobs": [
                {"name": "existing-job", "schedule": "0 8 * * *", "command": "echo hello"},
            ]
        }
        with open(jobs_yaml_path, "w", encoding="utf-8") as fh:
            yaml.dump(initial_data, fh, default_flow_style=False)

        from automedia.mcp.tools import add_cron_schedule

        add_cron_schedule(name="new-schedule", expression="30 9 * * *")

        # Read back and verify both keys exist
        with open(jobs_yaml_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        assert "jobs" in data
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["name"] == "existing-job"

        assert "pipeline_schedules" in data
        assert len(data["pipeline_schedules"]) == 1
        assert data["pipeline_schedules"][0]["name"] == "new-schedule"


# ---------------------------------------------------------------------------
# Tests: server registration
# ---------------------------------------------------------------------------


class TestServerRegistration:
    """Tests that cron schedule tools are registered in the MCP server."""

    def test_tools_are_registered(self) -> None:
        """Cron schedule tools appear in the server's tool list."""
        from automedia.mcp.server import create_server

        server = create_server()
        tool_names = server._tool_manager._tools.keys()

        assert "add_cron_schedule" in tool_names
        assert "list_cron_schedules" in tool_names
        assert "remove_cron_schedule" in tool_names

    def test_can_be_called_via_server(self) -> None:
        """Cron schedule tools work when called through server imports."""
        from automedia.mcp.server import (
            add_cron_schedule,
            list_cron_schedules,
            remove_cron_schedule,
        )

        add_cron_schedule(name="via-server", expression="0 8 * * *")

        listed = list_cron_schedules()
        assert listed["count"] == 1
        assert listed["schedules"][0]["name"] == "via-server"

        removed = remove_cron_schedule(name="via-server")
        assert removed["removed"] is True

        listed2 = list_cron_schedules()
        assert listed2["count"] == 0
