"""Tests for ``automedia cron run --due`` and the pool→pipeline bridge.

The unattended contract is ``automedia cron run --due`` (external systemd/crond
calls it hourly).  It must dispatch exactly the schedule entries that are due at
an *injectable* clock instant, keep ``cron run <job>`` working, and — for a due
``kind == "pipeline"`` entry — reach :func:`run_scheduled_pipeline`, which
selects a pending topic from the pool and calls the pipeline (the pool→pipeline
bridge).

Every test monkeypatches the config directory to ``tmp_path`` — nothing here
touches the real ``~/.automedia/`` or the package ``cron/jobs.yaml``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.pool.db import PoolDB

runner = CliRunner()

#: The fixed "now" injected into the CLI for deterministic due checks.
FIXED_NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the canonical schedule store to *tmp_path* for hermetic I/O."""
    import automedia.mcp.tools._shared as shared

    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
    # Keep the legacy-migration probe away from the real package file.
    monkeypatch.setattr(
        shared,
        "_get_package_jobs_yaml_path",
        lambda: tmp_path / "legacy_jobs.yaml",
        raising=False,
    )
    return tmp_path


def _write_store(
    config_dir: Path,
    *,
    jobs: list[dict[str, Any]] | None = None,
    schedules: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a canonical ``pipeline_schedules.yaml`` with jobs + schedules."""
    path = config_dir / "pipeline_schedules.yaml"
    payload: dict[str, Any] = {"pipeline_schedules": schedules or []}
    if jobs is not None:
        payload["jobs"] = jobs
    path.write_text(yaml.dump(payload, default_flow_style=False), encoding="utf-8")
    return path


def _static_job(name: str, schedule: str, command: str) -> dict[str, Any]:
    return {
        "name": name,
        "schedule": schedule,
        "command": command,
        "on_failure": "log",
        "timeout_s": 60,
        "description": name,
    }


def _pipeline_schedule(name: str, expression: str, *, kind: str = "pipeline") -> dict[str, Any]:
    return {
        "name": name,
        "expression": expression,
        "brand": "brand",
        "category": "",
        "count": 1,
        "platform": "",
        "mode": "auto",
        "kind": kind,
    }


def _recorder(monkeypatch: pytest.MonkeyPatch, attr: str) -> MagicMock:
    """Replace a module-level handler on ``cron.py`` with a recording mock."""
    from automedia.cli.commands import cron as cron_mod

    mock = MagicMock(return_value=None)
    monkeypatch.setattr(cron_mod, attr, mock)
    return mock


def _inject_now(monkeypatch: pytest.MonkeyPatch, now: datetime = FIXED_NOW) -> None:
    from automedia.cli.commands import cron as cron_mod

    monkeypatch.setattr(cron_mod, "_utcnow", lambda: now, raising=False)


# ---------------------------------------------------------------------------
# --due dispatch
# ---------------------------------------------------------------------------


class TestDueDispatch:
    def test_due_dispatches_exactly_the_due_entries(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One fixed clock → only the 08:00 entries run, and the process exits 0."""
        _write_store(
            config_dir,
            jobs=[
                _static_job("hot-collection", "0 8 * * *", "automedia cron run pool-collect"),
                _static_job("semantic-audit", "5 8 * * *", "automedia cron run pool-score"),
                _static_job("watchdog", "30 9 * * *", "automedia cron check-health"),
            ],
            schedules=[
                _pipeline_schedule("due-pipeline", "0 8 * * *"),
                {
                    **_pipeline_schedule("due-distribute", "0 8 * * *", kind="distribute"),
                    "command": "automedia distribute proj-1 --platforms wechat",
                    "project_id": "proj-1",
                    "platforms": "wechat",
                },
                _pipeline_schedule("later-pipeline", "0 9 * * *"),
            ],
        )
        _inject_now(monkeypatch)

        collect = _recorder(monkeypatch, "_job_pool_collect")
        score = _recorder(monkeypatch, "_job_pool_score")
        check_health = _recorder(monkeypatch, "cron_check_health")
        run_pipeline = MagicMock(return_value={"status": "success"})
        monkeypatch.setattr("automedia.cron.runner.run_scheduled_pipeline", run_pipeline)
        subprocess_run = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr("automedia.cli.commands.cron.subprocess.run", subprocess_run)

        result = runner.invoke(app, ["cron", "run", "--due"])

        assert result.exit_code == 0, result.output
        collect.assert_called_once()
        score.assert_not_called()
        check_health.assert_not_called()
        run_pipeline.assert_called_once()
        assert run_pipeline.call_args.args[0]["name"] == "due-pipeline"
        subprocess_run.assert_called_once()
        assert subprocess_run.call_args.args[0] == "automedia distribute proj-1 --platforms wechat"

    def test_no_due_entries_exits_zero_with_zero_runs(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing due → exit 0 and no handler runs."""
        _write_store(
            config_dir,
            jobs=[_static_job("watchdog", "30 9 * * *", "automedia cron check-health")],
            schedules=[_pipeline_schedule("later-pipeline", "0 9 * * *")],
        )
        _inject_now(monkeypatch)

        check_health = _recorder(monkeypatch, "cron_check_health")
        run_pipeline = MagicMock(return_value={"status": "success"})
        monkeypatch.setattr("automedia.cron.runner.run_scheduled_pipeline", run_pipeline)

        result = runner.invoke(app, ["cron", "run", "--due"])

        assert result.exit_code == 0, result.output
        check_health.assert_not_called()
        run_pipeline.assert_not_called()

    def test_due_covers_the_systemd_randomized_delay_window(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An 08:00 job is still due at 08:04 (RandomizedDelaySec=300)."""
        _write_store(
            config_dir,
            jobs=[_static_job("hot-collection", "0 8 * * *", "automedia cron run pool-collect")],
        )
        _inject_now(monkeypatch, datetime(2026, 9, 17, 8, 4, tzinfo=UTC))

        collect = _recorder(monkeypatch, "_job_pool_collect")

        result = runner.invoke(app, ["cron", "run", "--due"])

        assert result.exit_code == 0, result.output
        collect.assert_called_once()

    def test_due_ignores_entries_beyond_the_grace_window(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An 08:00 job is no longer due at 08:30 (two timers have passed)."""
        _write_store(
            config_dir,
            jobs=[_static_job("hot-collection", "0 8 * * *", "automedia cron run pool-collect")],
        )
        _inject_now(monkeypatch, datetime(2026, 9, 17, 8, 30, tzinfo=UTC))

        collect = _recorder(monkeypatch, "_job_pool_collect")

        result = runner.invoke(app, ["cron", "run", "--due"])

        assert result.exit_code == 0, result.output
        collect.assert_not_called()

    def test_due_skips_unknown_command_without_crashing(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A due static job whose command maps to no handler is skipped, exit 0."""
        _write_store(
            config_dir,
            jobs=[_static_job("mystery", "0 8 * * *", "some-other-tool --do-thing")],
        )
        _inject_now(monkeypatch)

        result = runner.invoke(app, ["cron", "run", "--due"])

        assert result.exit_code == 0, result.output
        assert "mystery" in result.output


# ---------------------------------------------------------------------------
# Backwards compatibility
# ---------------------------------------------------------------------------


class TestNamedJobStillWorks:
    def test_named_job_dispatches_without_due_flag(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``cron run <job>`` remains the explicit single-job path."""
        prune = _recorder(monkeypatch, "_job_pool_prune")

        result = runner.invoke(app, ["cron", "run", "pool-prune"])

        assert result.exit_code == 0, result.output
        prune.assert_called_once()

    def test_no_job_and_no_due_flag_is_an_error(self) -> None:
        """Bare ``cron run`` must not silently do nothing — it needs a target."""
        result = runner.invoke(app, ["cron", "run"])

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Pool → pipeline bridge
# ---------------------------------------------------------------------------


class TestPoolToPipelineBridge:
    def test_run_scheduled_pipeline_selects_pending_topic_and_calls_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A kind=="pipeline" entry selects the top pending topic and runs it."""
        db_path = tmp_path / "pool.db"
        db = PoolDB(db_path)
        db.add_topic({"title": "Low score topic", "status": "pending", "score": 3.0})
        db.add_topic({"title": "High score topic", "status": "pending", "score": 9.0})
        db.close()

        run_mock = MagicMock(
            return_value=MagicMock(status="success", project_id="pid-1", project_dir="")
        )
        monkeypatch.setattr("automedia.cron.runner.run_full_pipeline", run_mock)

        from automedia.cron.runner import run_scheduled_pipeline

        entry = _pipeline_schedule("bridge", "0 9 * * *")
        result = run_scheduled_pipeline(entry, pool_db_path=str(db_path))

        assert result["status"] == "success"
        assert result["topic"] == "High score topic"
        run_mock.assert_called_once_with(topic="High score topic", brand="brand", mode="auto")

        db = PoolDB(db_path)
        selected = db.list_topics(status="selected")
        pending = db.list_topics(status="pending")
        db.close()
        assert [t["title"] for t in selected] == ["High score topic"]
        assert [t["title"] for t in pending] == ["Low score topic"]

    def test_due_pipeline_entry_reaches_the_bridge(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``cron run --due`` calls run_scheduled_pipeline for a due pipeline entry."""
        _write_store(config_dir, schedules=[_pipeline_schedule("bridge", "0 8 * * *")])
        _inject_now(monkeypatch)

        run_pipeline = MagicMock(return_value={"status": "success"})
        monkeypatch.setattr("automedia.cron.runner.run_scheduled_pipeline", run_pipeline)

        result = runner.invoke(app, ["cron", "run", "--due"])

        assert result.exit_code == 0, result.output
        run_pipeline.assert_called_once()
        assert run_pipeline.call_args.args[0]["kind"] == "pipeline"


# ---------------------------------------------------------------------------
# Deployment contract
# ---------------------------------------------------------------------------


class TestSystemdContract:
    def test_service_execstart_matches_due_contract(self) -> None:
        """The shipped systemd unit must call the canonical --due command."""
        repo_root = Path(__file__).resolve().parents[2]
        service = (repo_root / "deploy" / "systemd" / "automedia-cron.service").read_text(
            encoding="utf-8"
        )

        assert "ExecStart=python -m automedia cron run --due" in service
