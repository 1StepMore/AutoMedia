"""Cron must park at H0 instead of blocking the scheduled run (issue #108).

An external crond fires ``automedia cron run --due`` with nobody at the
terminal.  If the pipeline hits the H0 review gate it must return at once with
``status="awaiting_review"`` — never wait out the review budget, and never
publish a run that a human has not approved.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from structlog.testing import capture_logs

from automedia.cron.runner import run_scheduled_pipeline
from automedia.pool.db import PoolDB


def _seed_pool(tmp_path: Path) -> str:
    """Create a pool DB with one pending topic and return its path."""
    db_path = tmp_path / "pool.db"
    db = PoolDB(db_path)
    db.add_topic({"title": "parked topic", "status": "pending", "score": 9.0})
    db.close()
    return str(db_path)


def _pipeline_result(status: str, *, project_dir: str = "") -> MagicMock:
    """Stand-in for ``PipelineResult`` with the fields the runner reads."""
    return MagicMock(status=status, project_id="pid-1", project_dir=project_dir)


def _entry() -> dict[str, Any]:
    return {"name": "scheduled", "brand": "brand", "mode": "auto"}


class TestParkedJob:
    def test_reports_awaiting_review_without_waiting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A parked pipeline is passed through as ``awaiting_review`` at once."""
        db_path = _seed_pool(tmp_path)
        run_mock = MagicMock(
            return_value=_pipeline_result("awaiting_review", project_dir=str(tmp_path))
        )
        monkeypatch.setattr("automedia.cron.runner.run_full_pipeline", run_mock)

        start = time.monotonic()
        result = run_scheduled_pipeline(_entry(), pool_db_path=db_path)
        elapsed = time.monotonic() - start

        assert result["status"] == "awaiting_review"
        assert elapsed < 1.0, "cron blocked instead of parking the job"
        run_mock.assert_called_once_with(
            topic="parked topic",
            brand="brand",
            mode="auto",
            block_on_hitl=False,
        )

    def test_parked_job_is_not_published(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A run awaiting review must never be published unattended."""
        db_path = _seed_pool(tmp_path)
        run_mock = MagicMock(
            return_value=_pipeline_result("awaiting_review", project_dir=str(tmp_path))
        )
        monkeypatch.setattr("automedia.cron.runner.run_full_pipeline", run_mock)
        pub_mock = MagicMock(return_value={})
        monkeypatch.setattr("automedia.cron.runner._publish_to_all_platforms", pub_mock)

        result = run_scheduled_pipeline(_entry(), pool_db_path=db_path)

        assert result["status"] == "awaiting_review"
        assert "publish_results" not in result
        pub_mock.assert_not_called()

    def test_awaiting_review_is_logged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The operator must see the park in cron output, not a silent success."""
        db_path = _seed_pool(tmp_path)
        run_mock = MagicMock(
            return_value=_pipeline_result("awaiting_review", project_dir=str(tmp_path))
        )
        monkeypatch.setattr("automedia.cron.runner.run_full_pipeline", run_mock)

        with capture_logs() as cap:
            run_scheduled_pipeline(_entry(), pool_db_path=db_path)

        events = [e for e in cap if "awaiting_review" in str(e.get("event", ""))]
        assert events, "no awaiting_review log event emitted for a parked cron job"


class TestSuccessStillPublishes:
    def test_success_job_publishes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The existing success path still publishes via the all-platforms path."""
        db_path = _seed_pool(tmp_path)
        run_mock = MagicMock(return_value=_pipeline_result("success", project_dir=str(tmp_path)))
        monkeypatch.setattr("automedia.cron.runner.run_full_pipeline", run_mock)
        pub_mock = MagicMock(return_value={"wechat": {"status": "published"}})
        monkeypatch.setattr("automedia.cron.runner._publish_to_all_platforms", pub_mock)

        result = run_scheduled_pipeline(_entry(), pool_db_path=db_path)

        assert result["status"] == "success"
        assert result["publish_results"] == {"wechat": {"status": "published"}}
        pub_mock.assert_called_once()
