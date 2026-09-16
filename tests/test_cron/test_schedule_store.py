"""Tests for the canonical pipeline-schedule store and its ``kind`` discriminator.

The single canonical source for scheduled jobs is the user-level
``pipeline_schedules.yaml`` resolved by
``automedia.mcp.tools._shared._get_jobs_yaml_path``.  Every schedule entry
carries a ``kind`` field (``"pipeline"`` | ``"distribute"``); an entry that
omits ``kind`` is treated as ``"pipeline"``.

All tests monkeypatch the config directory to ``tmp_path`` — nothing here
touches the real ``~/.automedia/`` or the package ``cron/jobs.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.mcp.tools._shared import _read_pipeline_schedules

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the user config dir to *tmp_path* for hermetic schedule I/O."""
    import automedia.mcp.tools._shared as shared

    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
    # Keep the legacy-migration probe away from the real package file unless
    # a test explicitly opts in by writing ``legacy_jobs.yaml``.
    monkeypatch.setattr(
        shared,
        "_get_package_jobs_yaml_path",
        lambda: tmp_path / "legacy_jobs.yaml",
        raising=False,
    )
    return tmp_path


def _store_path(config_dir: Path) -> Path:
    return config_dir / "pipeline_schedules.yaml"


def _write_store(config_dir: Path, entries: list[dict[str, Any]]) -> Path:
    path = _store_path(config_dir)
    path.write_text(
        yaml.dump({"pipeline_schedules": entries}, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def _read_store(config_dir: Path) -> list[dict[str, Any]]:
    path = _store_path(config_dir)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("pipeline_schedules", [])


def _distribute_entry(
    name: str = "distribute-proj-1", project_id: str = "proj-1"
) -> dict[str, Any]:
    return {
        "name": name,
        "expression": "0 8 * * *",
        "command": f"automedia distribute {project_id} --platforms wechat",
        "project_id": project_id,
        "platforms": "wechat",
        "kind": "distribute",
    }


def _pipeline_entry(name: str = "pipeline-a") -> dict[str, Any]:
    return {
        "name": name,
        "expression": "0 9 * * *",
        "brand": "brand",
        "category": "tech",
        "count": 1,
        "platform": "",
        "mode": "auto",
        "kind": "pipeline",
    }


# ---------------------------------------------------------------------------
# Canonical store + cross-surface write/read
# ---------------------------------------------------------------------------


class TestCanonicalStore:
    def test_distribute_schedule_lands_in_canonical_store_with_kind(self, config_dir: Path) -> None:
        """``distribute --cron`` writes to the canonical store with kind=distribute."""
        result = runner.invoke(
            app,
            ["distribute", "proj-1", "--cron", "0 8 * * *", "--platforms", "wechat"],
        )
        assert result.exit_code == 0, result.output

        assert _store_path(config_dir).is_file(), "canonical store was not created"
        raw = _read_store(config_dir)
        assert len(raw) == 1
        assert raw[0]["name"] == "distribute-proj-1"
        assert raw[0]["kind"] == "distribute"
        assert raw[0]["project_id"] == "proj-1"
        assert raw[0]["platforms"] == "wechat"

        # Cross-surface: the read helper sees the same canonical entry.
        schedules = _read_pipeline_schedules()
        assert [s["name"] for s in schedules] == ["distribute-proj-1"]
        assert schedules[0].get("kind") == "distribute"

    def test_migration_is_idempotent_and_tags_kinds(self, config_dir: Path) -> None:
        """Legacy package entries migrate once, tagged, and a second read is stable."""
        legacy = config_dir / "legacy_jobs.yaml"
        legacy.write_text(
            yaml.dump(
                {
                    "pipeline_schedules": [
                        {
                            "name": "distribute-proj",
                            "expression": "0 8 * * *",
                            "command": "automedia distribute proj --platforms wechat",
                            "project_id": "proj",
                            "platforms": "wechat",
                        },
                        {
                            "name": "pipeline-a",
                            "expression": "0 9 * * *",
                            "brand": "brand",
                            "category": "tech",
                            "count": 1,
                            "platform": "",
                            "mode": "auto",
                        },
                    ]
                },
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

        first = _read_pipeline_schedules()
        assert {e["name"]: e.get("kind") for e in first} == {
            "distribute-proj": "distribute",
            "pipeline-a": "pipeline",
        }

        canonical = _store_path(config_dir)
        assert canonical.is_file(), "migration did not create the canonical store"
        after_first = canonical.read_text(encoding="utf-8")

        second = _read_pipeline_schedules()
        assert second == first
        assert canonical.read_text(encoding="utf-8") == after_first

    def test_missing_store_returns_empty_without_raise(self, config_dir: Path) -> None:
        """No canonical file and no legacy file -> empty list, no exception."""
        assert _read_pipeline_schedules() == []

    def test_entry_without_kind_defaults_to_pipeline(self, config_dir: Path) -> None:
        """A raw entry that omits ``kind`` is treated as ``"pipeline"``."""
        _write_store(
            config_dir,
            [
                {
                    "name": "legacy-pipeline",
                    "expression": "0 9 * * *",
                    "brand": "brand",
                    "category": "",
                    "count": 1,
                    "platform": "",
                    "mode": "auto",
                }
            ],
        )

        schedules = _read_pipeline_schedules()
        assert schedules[0]["name"] == "legacy-pipeline"
        assert schedules[0].get("kind") == "pipeline"


# ---------------------------------------------------------------------------
# Job-level kind selection
# ---------------------------------------------------------------------------


class TestJobKindSelection:
    def test_job_run_pipeline_ignores_distribute_entries(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """run-pipeline must not feed distribute entries to run_scheduled_pipeline."""
        from automedia.cli.commands import cron as cron_mod

        _write_store(config_dir, [_distribute_entry()])
        runner_mock = MagicMock(return_value={"status": "success"})
        monkeypatch.setattr("automedia.cron.runner.run_scheduled_pipeline", runner_mock)

        cron_mod._job_run_pipeline()

        runner_mock.assert_not_called()
        assert "No pipeline schedules" in capsys.readouterr().out

    def test_job_run_pipeline_runs_entries_without_kind(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An entry with no ``kind`` is a pipeline entry and must run."""
        from automedia.cli.commands import cron as cron_mod

        _write_store(
            config_dir,
            [
                {
                    "name": "legacy-pipeline",
                    "expression": "0 9 * * *",
                    "brand": "brand",
                    "category": "",
                    "count": 1,
                    "platform": "",
                    "mode": "auto",
                }
            ],
        )
        runner_mock = MagicMock(
            return_value={"status": "success", "topic": "t", "project_id": "pid"}
        )
        monkeypatch.setattr("automedia.cron.runner.run_scheduled_pipeline", runner_mock)

        cron_mod._job_run_pipeline()

        runner_mock.assert_called_once()
        passed = runner_mock.call_args.args[0]
        assert passed["name"] == "legacy-pipeline"

    def test_job_run_distribute_ignores_pipeline_entries(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """run-distribute must not execute pipeline entries."""
        from automedia.cli.commands import cron as cron_mod

        _write_store(config_dir, [_pipeline_entry()])
        run_mock = MagicMock()
        monkeypatch.setattr(cron_mod.subprocess, "run", run_mock)

        cron_mod._job_run_distribute()

        run_mock.assert_not_called()
        assert "No scheduled distributions" in capsys.readouterr().out

    def test_job_run_distribute_runs_distribute_entries(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run-distribute executes the command of a kind=distribute entry."""
        from automedia.cli.commands import cron as cron_mod

        _write_store(config_dir, [_distribute_entry()])
        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(cron_mod.subprocess, "run", run_mock)

        cron_mod._job_run_distribute()

        run_mock.assert_called_once()
        assert run_mock.call_args.args[0] == "automedia distribute proj-1 --platforms wechat"


# ---------------------------------------------------------------------------
# MCP write surface
# ---------------------------------------------------------------------------


class TestMcpScheduleKind:
    def test_add_cron_schedule_writes_pipeline_kind(self, config_dir: Path) -> None:
        """The MCP add tool tags its entry as ``kind="pipeline"``."""
        from automedia.mcp.tools import add_cron_schedule

        result = add_cron_schedule(name="mcp-pipeline", expression="0 8 * * *", brand="brand")
        assert result["added"] is True

        raw = _read_store(config_dir)
        assert len(raw) == 1
        assert raw[0]["name"] == "mcp-pipeline"
        assert raw[0]["kind"] == "pipeline"
