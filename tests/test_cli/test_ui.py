"""Tests for the minimal local web UI (#358).

FastAPI TestClient only — no server is ever started; the CLI surface test
asserts ``automedia ui --help`` stays loopback-documented.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.cli.commands.ui import _run_state, create_app


@pytest.fixture(autouse=True)
def _reset_run_state() -> Any:
    """Keep the module-global run state isolated between tests."""
    _run_state.update(running=False, finished=True, status="", progress={})
    _run_state.pop("tracker", None)
    yield
    for _ in range(100):
        if not _run_state["running"]:
            break
        time.sleep(0.01)
    _run_state.update(running=False, finished=True, status="", progress={})
    _run_state.pop("tracker", None)


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

    def test_config_redacts_nested_secrets(self, client: Any) -> None:
        cfg = {
            "mode": "x",
            "llm": {"text_generation": {"api_key": "sk-secret", "model": "m"}},
            "list": [{"token": "t"}],
        }
        with (
            patch("automedia.core.config_loader.load_config", return_value=cfg),
            patch("automedia.core.doctor.Doctor.check_dependencies", return_value=[]),
        ):
            data = client.get("/api/config").json()
        assert data["config"]["llm"]["text_generation"]["api_key"] == "…"
        assert data["config"]["list"][0]["token"] == "…"
        assert data["config"]["llm"]["text_generation"]["model"] == "m"
        assert data["config"]["mode"] == "x"


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

    def test_accounts_without_master_key(self, client: Any) -> None:
        with patch(
            "automedia.accounts.registry.AccountRegistry",
            side_effect=ValueError("AUTOMEDIA_MASTER_KEY environment variable must be set"),
        ):
            resp = client.get("/api/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["accounts"] == []
        assert data["warning"]


class TestRunRoute:
    def test_run_starts_background_worker(self, client: Any) -> None:
        fake_result = MagicMock()
        fake_result.status = "published"
        calls: list[dict[str, Any]] = []

        def fake_run(**kwargs: Any) -> Any:
            calls.append(kwargs)
            return fake_result

        with patch("automedia.run_full_pipeline", side_effect=fake_run):
            resp = client.post("/api/run", json={"topic": "T", "mode": "text_only", "brand": ""})
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

    def test_progress_updates_while_running(self, client: Any) -> None:
        def fake_run(**kwargs: Any) -> Any:
            progress = kwargs["progress"]
            progress.set_gate_names(["G0", "G1"])
            progress.on_gate_start("G0")
            progress.on_gate_end("G0", True, 0.1)
            time.sleep(0.2)
            result = MagicMock()
            result.status = "published"
            return result

        with patch("automedia.run_full_pipeline", side_effect=fake_run):
            resp = client.post("/api/run", json={"topic": "T", "mode": "text_only"})
            assert resp.json()["started"] is True

            deadline = time.time() + 1.0
            data: dict[str, Any] = {}
            while time.time() < deadline:
                data = client.get("/api/run/progress").json()
                if data["progress"].get("gates_done"):
                    break
                time.sleep(0.01)

        assert data["finished"] is False  # observed mid-run, not after completion
        assert data["progress"]["gates_done"] == ["G0"]
        assert data["progress"]["total_gates"] == 2

    def test_second_run_conflicted(self, client: Any) -> None:
        _run_state.update(running=True, finished=False)
        try:
            resp = client.post("/api/run", json={"topic": "T", "mode": "text_only"})
            assert resp.status_code == 409
        finally:
            _run_state.update(running=False, finished=True)


class TestPlatformsRoute:
    def test_lists_platforms_with_media_specs(self, client: Any) -> None:
        data = client.get("/api/platforms").json()
        by_name = {p["name"]: p for p in data["platforms"]}
        assert by_name["douyin"] == {
            "name": "douyin",
            "width": 1080,
            "height": 1920,
            "aspect_ratio": "9:16",
        }
        # a notifier has no media spec, so it is not a run target here
        assert "feishu" not in by_name


class TestRunPlatforms:
    """#494: the platform picked in the UI must reach the SDK call."""

    def _post_and_wait(self, client: Any, payload: dict[str, Any]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        fake_result = MagicMock()
        fake_result.status = "published"

        def fake_run(**kwargs: Any) -> Any:
            calls.append(kwargs)
            return fake_result

        with patch("automedia.run_full_pipeline", side_effect=fake_run):
            resp = client.post("/api/run", json=payload)
            assert resp.json()["started"] is True
            deadline = time.time() + 2.0
            while time.time() < deadline and not _run_state["finished"]:
                time.sleep(0.01)
        assert _run_state["finished"] is True
        return calls

    def test_selected_platforms_are_forwarded(self, client: Any) -> None:
        calls = self._post_and_wait(
            client, {"topic": "T", "mode": "video_only", "platforms": ["douyin"]}
        )
        assert calls[0]["platforms"] == ["douyin"]

    def test_short_video_without_selection_targets_douyin(self, client: Any) -> None:
        calls = self._post_and_wait(client, {"topic": "T", "mode": "short-video"})
        assert calls[0]["platforms"] == ["douyin"]

    def test_text_run_without_selection_leaves_platforms_unset(self, client: Any) -> None:
        calls = self._post_and_wait(client, {"topic": "T", "mode": "text_only"})
        assert calls[0]["platforms"] is None

    def test_unknown_platform_is_rejected_before_starting(self, client: Any) -> None:
        with patch("automedia.run_full_pipeline") as fake_run:
            resp = client.post(
                "/api/run",
                json={"topic": "T", "mode": "short-video", "platforms": ["nope"]},
            )
        assert resp.status_code == 422
        assert "nope" in resp.json()["detail"]
        fake_run.assert_not_called()
