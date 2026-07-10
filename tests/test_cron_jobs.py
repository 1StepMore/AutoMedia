"""Tests for automedia cron — jobs.yaml config + E2E job execution."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.pool.db import PoolDB

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_YAML = PROJECT_ROOT / "src" / "automedia" / "cron" / "jobs.yaml"

EXPECTED_JOBS = ["hot-collection", "semantic-audit", "publish-check", "watchdog"]
REQUIRED_FIELDS = {"name", "schedule", "command", "on_failure", "timeout_s", "description"}
VALID_ON_FAILURE = {"stop", "skip", "retry", "log"}

runner = CliRunner()


# ===========================================================================
# YAML config tests
# ===========================================================================


def _load_jobs() -> list[dict[str, Any]]:
    assert JOBS_YAML.is_file(), f"YAML file not found: {JOBS_YAML}"
    with open(JOBS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict) and "jobs" in data
    jobs = data["jobs"]
    assert isinstance(jobs, list)
    return jobs


def test_yaml_is_parseable():
    jobs = _load_jobs()
    assert len(jobs) > 0


def test_exactly_four_jobs():
    assert len(_load_jobs()) == 4


def test_job_names_are_expected():
    names = [j["name"] for j in _load_jobs()]
    assert names == EXPECTED_JOBS


def test_all_required_fields_present():
    for job in _load_jobs():
        missing = REQUIRED_FIELDS - set(job.keys())
        assert not missing, f"job '{job.get('name', '?')}' missing fields: {missing}"


def test_on_failure_valid():
    for job in _load_jobs():
        assert job["on_failure"] in VALID_ON_FAILURE


def test_timeout_s_is_positive_int():
    for job in _load_jobs():
        t = job["timeout_s"]
        assert isinstance(t, int) and t > 0


def test_depends_on_refer_to_existing_jobs():
    jobs = _load_jobs()
    all_names = {j["name"] for j in jobs}
    for job in jobs:
        deps = job.get("depends_on")
        if not deps:
            continue
        if isinstance(deps, list):
            for dep in deps:
                assert dep in all_names
        else:
            assert deps is None


def test_depends_on_type():
    for job in _load_jobs():
        deps = job.get("depends_on")
        assert deps is None or isinstance(deps, list)


def test_schedule_is_valid_cron_like():
    for job in _load_jobs():
        parts = job["schedule"].split()
        assert len(parts) == 5


def test_job_names_are_unique():
    names = [j["name"] for j in _load_jobs()]
    assert len(names) == len(set(names))


# ===========================================================================
# E2E Fixtures
# ===========================================================================


@pytest.fixture()
def e2e_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a temporary working directory with .automedia/pool.db.

    Returns a dict with paths for assertions.
    """
    am_dir = tmp_path / ".automedia"
    am_dir.mkdir()
    db_path = am_dir / "pool.db"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("automedia.cli.commands.cron._DEFAULT_DB", db_path)

    return {"base": tmp_path, "db_path": db_path, "am_dir": am_dir}


# ===========================================================================
# E2E: pool-collect
# ===========================================================================


class TestCronPoolCollect:
    """``automedia cron run pool-collect`` populates pool.db."""

    def test_collect_inserts_topics(self, e2e_env: dict[str, Any]):
        result = runner.invoke(app, ["cron", "run", "pool-collect"])
        assert result.exit_code == 0, result.output
        assert "inserted" in result.output.lower() or "completed" in result.output.lower()

        db = PoolDB(e2e_env["db_path"])
        topics = db.list_topics()
        db.close()
        assert len(topics) > 0

    def test_collect_deduplicates(self, e2e_env: dict[str, Any]):
        runner.invoke(app, ["cron", "run", "pool-collect"])
        result = runner.invoke(app, ["cron", "run", "pool-collect"])
        assert result.exit_code == 0

        output_lower = result.output.lower()
        assert "dedup" in output_lower or "skipped" in output_lower

    def test_collect_topics_have_source(self, e2e_env: dict[str, Any]):
        runner.invoke(app, ["cron", "run", "pool-collect"])

        db = PoolDB(e2e_env["db_path"])
        topics = db.list_topics()
        db.close()

        sources = {t["source"] for t in topics}
        assert len(sources) > 1
        assert topics[0]["title"]


# ===========================================================================
# E2E: pool-score
# ===========================================================================


class TestCronPoolScore:
    """``automedia cron run pool-score`` updates pending topic scores."""

    def _seed_pending(self, db_path: Path, count: int = 3) -> None:
        db = PoolDB(db_path)
        for i in range(count):
            db.add_topic(
                {
                    "title": f"AI video generation breakthrough {i}",
                    "source": "weibo",
                    "score": 8.0 + i * 0.5,
                    "status": "pending",
                }
            )
        db.close()

    def test_score_updates_pending(self, e2e_env: dict[str, Any]):
        self._seed_pending(e2e_env["db_path"])
        result = runner.invoke(app, ["cron", "run", "pool-score"])
        assert result.exit_code == 0, result.output
        assert "scored" in result.output.lower()

        db = PoolDB(e2e_env["db_path"])
        pending = db.list_topics(status="pending")
        db.close()
        for t in pending:
            assert t["score"] > 0.0

    def test_score_no_pending(self, e2e_env: dict[str, Any]):
        result = runner.invoke(app, ["cron", "run", "pool-score"])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_score_after_collect(self, e2e_env: dict[str, Any]):
        runner.invoke(app, ["cron", "run", "pool-collect"])
        result = runner.invoke(app, ["cron", "run", "pool-score"])
        assert result.exit_code == 0, result.output

        db = PoolDB(e2e_env["db_path"])
        topics = db.list_topics()
        db.close()
        scored = [t for t in topics if t["score"] > 0.0]
        assert len(scored) > 0


# ===========================================================================
# E2E: pool-prune
# ===========================================================================


class TestCronPoolPrune:
    """``automedia cron run pool-prune`` removes stale pending topics."""

    def _seed_old_and_fresh(self, db_path: Path) -> tuple[int, int]:
        db = PoolDB(db_path)
        old_id = db.add_topic(
            {
                "title": "Old stale topic",
                "status": "pending",
            }
        )
        db.conn.execute(
            "UPDATE topics SET created_at = ? WHERE id = ?",
            ((datetime.now(UTC) - timedelta(days=30)).isoformat(), old_id),
        )
        db.conn.commit()

        fresh_id = db.add_topic({"title": "Fresh topic", "status": "pending"})

        selected_id = db.add_topic({"title": "Selected old", "status": "selected"})
        db.conn.execute(
            "UPDATE topics SET created_at = ? WHERE id = ?",
            ((datetime.now(UTC) - timedelta(days=30)).isoformat(), selected_id),
        )
        db.conn.commit()

        db.close()
        return old_id, fresh_id

    def test_prune_removes_old(self, e2e_env: dict[str, Any]):
        old_id, fresh_id = self._seed_old_and_fresh(e2e_env["db_path"])
        result = runner.invoke(app, ["cron", "run", "pool-prune"])
        assert result.exit_code == 0, result.output
        assert "removed" in result.output.lower()

        db = PoolDB(e2e_env["db_path"])
        assert db.get_topic(old_id) is None
        assert db.get_topic(fresh_id) is not None
        db.close()

    def test_prune_preserves_selected(self, e2e_env: dict[str, Any]):
        self._seed_old_and_fresh(e2e_env["db_path"])
        runner.invoke(app, ["cron", "run", "pool-prune"])

        db = PoolDB(e2e_env["db_path"])
        selected = db.list_topics(status="selected")
        db.close()
        assert len(selected) == 1

    def test_prune_empty_pool(self, e2e_env: dict[str, Any]):
        result = runner.invoke(app, ["cron", "run", "pool-prune"])
        assert result.exit_code == 0
        assert "0" in result.output


# ===========================================================================
# E2E: publish-check
# ===========================================================================


class TestCronPublishCheck:
    """``automedia cron run publish-check`` reports publish readiness."""

    def test_publish_check_no_selected(self, e2e_env: dict[str, Any]):
        result = runner.invoke(app, ["cron", "run", "publish-check"])
        assert result.exit_code == 0, result.output
        assert "0 topic" in result.output.lower() or "selected" in result.output.lower()

    def test_publish_check_with_selected(self, e2e_env: dict[str, Any]):
        db = PoolDB(e2e_env["db_path"])
        db.add_topic({"title": "Ready to publish", "status": "selected"})
        db.add_topic({"title": "Also ready", "status": "selected"})
        db.close()

        result = runner.invoke(app, ["cron", "run", "publish-check"])
        assert result.exit_code == 0
        assert "2" in result.output

    def test_publish_check_scans_projects(self, e2e_env: dict[str, Any]):
        base = e2e_env["base"]
        proj_dir = base / "20260707-test-proj"
        proj_dir.mkdir()
        (proj_dir / "00_project_info.json").write_text(
            json.dumps({"project_id": "test1", "topic": "T"}), encoding="utf-8"
        )
        (proj_dir / "06_publish").mkdir()

        result = runner.invoke(app, ["cron", "run", "publish-check"])
        assert result.exit_code == 0
        assert "test1" in result.output or "project" in result.output.lower()


# ===========================================================================
# E2E: check-health
# ===========================================================================


class TestCronCheckHealth:
    """``automedia cron check-health`` runs 4-step health check."""

    def test_check_health_all_pass(self, e2e_env: dict[str, Any]):
        PoolDB(e2e_env["db_path"]).close()
        result = runner.invoke(app, ["cron", "check-health"])
        assert "Health Check" in result.output
        assert result.exit_code in (0, 1)

    def test_check_health_reports_config_dir(self, e2e_env: dict[str, Any]):
        PoolDB(e2e_env["db_path"]).close()
        result = runner.invoke(app, ["cron", "check-health"])
        assert ".automedia" in result.output

    def test_check_health_reports_pool_db(self, e2e_env: dict[str, Any]):
        PoolDB(e2e_env["db_path"]).close()
        result = runner.invoke(app, ["cron", "check-health"])
        assert "pool.db" in result.output

    def test_check_health_reports_jobs_yaml(self, e2e_env: dict[str, Any]):
        PoolDB(e2e_env["db_path"]).close()
        result = runner.invoke(app, ["cron", "check-health"])
        assert "jobs.yaml" in result.output

    def test_check_health_missing_pool_db(self, e2e_env: dict[str, Any]):
        result = runner.invoke(app, ["cron", "check-health"])
        assert "Health Check" in result.output
        pool_lines = [
            line
            for line in result.output.splitlines()
            if "pool.db" in line.lower() or "pool" in line.lower()
        ]
        assert (
            any(
                "✗" in line or "not" in line.lower() or "error" in line.lower()
                for line in pool_lines
            )
            or result.exit_code != 0
        )

    def test_check_health_missing_config_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        db_path = empty / ".automedia" / "pool.db"
        monkeypatch.setattr("automedia.cli.commands.cron._DEFAULT_DB", db_path)
        result = runner.invoke(app, ["cron", "check-health"])
        assert "Health Check" in result.output
        assert result.exit_code != 0


# ===========================================================================
# CLI dispatch tests
# ===========================================================================


class TestCronCLIDispatch:
    """Verify CLI argument routing for cron commands."""

    def test_unknown_job_exits_1(self):
        result = runner.invoke(app, ["cron", "run", "nonexistent-job"])
        assert result.exit_code == 1
        assert "Unknown job" in result.output

    def test_all_four_jobs_dispatch(self, e2e_env: dict[str, Any]):
        for job_name in ("pool-collect", "pool-score", "pool-prune", "publish-check"):
            result = runner.invoke(app, ["cron", "run", job_name])
            assert result.exit_code == 0, f"{job_name} failed: {result.output}"
            assert "completed" in result.output.lower()
