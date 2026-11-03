"""Tests for the minimal local web UI (#358).

FastAPI TestClient only — no server is ever started; the CLI surface test
asserts ``automedia ui --help`` stays loopback-documented.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.cli.commands.ui import _run_state, create_app


@pytest.fixture()
def client() -> Any:
    from fastapi.testclient import TestClient

    return TestClient(create_app())


class TestIndex:
    def test_index_serves_single_page(self, client: Any) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "AutoMedia" in resp.text
        # loopback warning is part of the page chrome
        assert "loopback" in resp.text

    def test_docs_disabled(self, client: Any) -> None:
        """No Swagger UI on the local, unauthenticated server."""
        assert client.get("/docs").status_code == 404


class TestConfigRoute:
    def test_config_redacts_secrets(self, client: Any) -> None:
        fake_doc = [{"name": "ffmpeg", "installed": True}, {"name": "bun", "installed": False}]
        with (
            patch(
                "automedia.core.config_loader.load_config",
                return_value={"llm_api_key": "sk-secret", "mode": "text_only"},
            ),
            patch("automedia.core.doctor.Doctor.check_dependencies", return_value=fake_doc),
        ):
            data = client.get("/api/config").json()
        assert data["dependencies"] == fake_doc
        assert data["config"]["llm_api_key"] == "…"  # redacted
        assert data["config"]["mode"] == "text_only"  # non-secret passes through


class TestProjectsRoute:
    def test_projects_scan(
        self, client: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proj = tmp_path / "proj-1"
        proj.mkdir()
        (proj / "00_project_info.json").write_text(
            json.dumps({"project_id": "p1", "status": "published", "topic": "T"}), encoding="utf-8"
        )
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path))
        data = client.get("/api/projects").json()
        assert data["projects"][0]["id"] == "p1"

        detail = client.get("/api/projects/p1").json()
        assert detail["topic"] == "T"
        assert client.get("/api/projects/missing").status_code == 404


class TestAccountsRoute:
    def test_accounts_metadata_only(self, client: Any) -> None:
        registry = MagicMock()
        registry.list.return_value = [
            {
                "account_id": "acc_x",
                "platform": "zhihu",
                "label": "L",
                "auth_type": "api_key",
                "status": "active",
            }
        ]
        with patch("automedia.accounts.registry.AccountRegistry", return_value=registry):
            data = client.get("/api/accounts").json()
        assert data["accounts"][0]["account_id"] == "acc_x"
        assert "credentials" not in json.dumps(data)


class TestRunRoute:
    def test_run_starts_background_worker(self, client: Any) -> None:
        fake_result = MagicMock()
        fake_result.status = "published"
        calls: list[dict[str, Any]] = []

        def fake_run(**kwargs: Any) -> Any:
            calls.append(kwargs)
            return fake_result

        with patch("automedia.run_full_pipeline", side_effect=fake_run):
            resp = client.post(
                "/api/run", json={"topic": "T", "mode": "text_only", "brand": ""}
            )
            assert resp.json()["started"] is True
            # wait for the worker thread
            import time

            for _ in range(50):
                if _run_state["finished"]:
                    break
                time.sleep(0.05)
            progress = client.get("/api/run/progress").json()

        assert calls[0]["topic"] == "T" and calls[0]["mode"] == "text_only"
        assert calls[0]["brand"] == "default"  # empty brand -> default
        assert progress["finished"] is True
        assert progress["status"] == "published"

    def test_second_run_conflicted(self, client: Any) -> None:
        _run_state.update(running=True, finished=False)
        try:
            resp = client.post("/api/run", json={"topic": "T", "mode": "text_only"})
            assert resp.status_code == 409
        finally:
            _run_state.update(running=False, finished=True)
