"""Tests for ComfyUIImageEngine — image generation via ComfyUI HTTP API.

Covers:
    - Class attributes (engine_name, modality)
    - check_available() with mocked httpx (success, failure, missing module)
    - Auto-registration in EngineRegistry
    - Constructor with config dict
    - generate() full HTTP flow: POST /prompt → poll → download
    - generate() error paths: all raise EngineExecutionError (NO PIL fallback)
    - Registry isolation via clear()
"""

from __future__ import annotations

import builtins
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.engines import EngineExecutionError
from automedia.engines.implementations.image_comfyui import ComfyUIImageEngine
from automedia.engines.registry import EngineRegistry

# =========================================================================
# Class attribute tests
# =========================================================================


class TestComfyUIImageEngineAttributes:
    """engine_name and modality class-level attributes."""

    def teardown_method(self) -> None:
        EngineRegistry().clear()
        EngineRegistry().register("comfyui", ComfyUIImageEngine, modality="image")

    def test_engine_name(self) -> None:
        assert ComfyUIImageEngine.engine_name == "comfyui"

    def test_modality(self) -> None:
        assert ComfyUIImageEngine.modality == "image"


# =========================================================================
# Constructor tests
# =========================================================================


class TestComfyUIImageEngineConstructor:
    """Constructor with and without config dict."""

    def teardown_method(self) -> None:
        EngineRegistry().clear()
        EngineRegistry().register("comfyui", ComfyUIImageEngine, modality="image")

    def test_default_config_is_empty(self) -> None:
        """No-arg constructor stores empty dict."""
        engine = ComfyUIImageEngine()
        assert engine._config == {}

    def test_with_config(self) -> None:
        """Constructor stores provided config."""
        config = {"host": "10.0.0.1", "port": 8288, "timeout": 60}
        engine = ComfyUIImageEngine(engine_config=config)
        assert engine._config["host"] == "10.0.0.1"
        assert engine._config["port"] == 8288
        assert engine._config["timeout"] == 60


# =========================================================================
# check_available tests
# =========================================================================


class TestComfyUIImageEngineCheckAvailable:
    """check_available() with mocked httpx."""

    def teardown_method(self) -> None:
        EngineRegistry().clear()
        EngineRegistry().register("comfyui", ComfyUIImageEngine, modality="image")

    @patch("httpx.Client")
    def test_returns_true_when_reachable(
        self, mock_client_cls: MagicMock
    ) -> None:
        """HTTP GET succeeds → available is True."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        # raise_for_status on a MagicMock does not raise → success
        engine = ComfyUIImageEngine()
        available, msg = engine.check_available()

        assert available is True
        assert "reachable" in msg.lower()
        mock_client.get.assert_called_once()

    @patch("httpx.Client")
    def test_returns_false_when_unreachable(
        self, mock_client_cls: MagicMock
    ) -> None:
        """HTTP GET raises → available is False."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = ConnectionError("Connection refused")

        engine = ComfyUIImageEngine()
        available, msg = engine.check_available()

        assert available is False
        assert "not reachable" in msg.lower()

    def test_returns_false_when_httpx_missing(self) -> None:
        """httpx import fails → available is False."""
        engine = ComfyUIImageEngine()
        original_import = builtins.__import__

        def _mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "httpx":
                raise ImportError("No module named 'httpx'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            available, msg = engine.check_available()

        assert available is False
        assert "httpx not installed" in msg

    @patch("httpx.Client")
    def test_uses_default_url(self, mock_client_cls: MagicMock) -> None:
        """Default host/port/protocol produce http://127.0.0.1:8188."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        engine = ComfyUIImageEngine()
        engine.check_available()

        call_url = mock_client.get.call_args[0][0]
        assert call_url == "http://127.0.0.1:8188"

    @patch("httpx.Client")
    def test_uses_custom_url_from_config(
        self, mock_client_cls: MagicMock
    ) -> None:
        """Custom host/port/protocol from config are used."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        engine = ComfyUIImageEngine(
            engine_config={
                "host": "192.168.1.100",
                "port": 8288,
                "protocol": "https",
            },
        )
        engine.check_available()

        call_url = mock_client.get.call_args[0][0]
        assert call_url == "https://192.168.1.100:8288"


# =========================================================================
# Auto-registration tests
# =========================================================================


class TestComfyUIImageEngineAutoRegistration:
    """Engine auto-registers in EngineRegistry on module import."""

    def teardown_method(self) -> None:
        EngineRegistry().clear()
        EngineRegistry().register("comfyui", ComfyUIImageEngine, modality="image")

    def test_registered_in_engine_registry(self) -> None:
        """ComfyUIImageEngine appears in the registry under 'image' modality."""
        assert "comfyui" in EngineRegistry()
        assert "comfyui" in EngineRegistry().list_by_modality("image")

    def test_registry_clear_removes_engine(self) -> None:
        """EngineRegistry().clear() removes all registrations."""
        assert "comfyui" in EngineRegistry()
        EngineRegistry().clear()
        assert "comfyui" not in EngineRegistry()

    def test_registered_class_is_correct(self) -> None:
        """Registry returns ComfyUIImageEngine class."""
        cls = EngineRegistry().get("comfyui")
        assert cls is ComfyUIImageEngine


# =========================================================================
# generate() — success path
# =========================================================================


class TestComfyUIImageEngineGenerate:
    """generate() complete happy-path with mocked httpx."""

    def teardown_method(self) -> None:
        EngineRegistry().clear()
        EngineRegistry().register("comfyui", ComfyUIImageEngine, modality="image")

    @patch("httpx.Client")
    def test_full_flow_creates_output_file(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """Full HTTP flow: POST → poll → download → file written."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # POST /prompt → success with prompt_id
        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "test-prompt-abc"}
        mock_client.post.return_value = post_resp

        # History response (shared between poll and history refetch)
        history_resp = MagicMock()
        history_resp.json.return_value = {
            "test-prompt-abc": {
                "status": {"completed": True},
                "outputs": {
                    "3": {"images": [{"filename": "comfy_output.png"}]},
                },
            },
        }

        # Download response
        download_resp = MagicMock()
        download_resp.content = b"fake-image-content"

        # 1st GET = _poll_comfyui, 2nd GET = history refetch, 3rd GET = /view
        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        engine = ComfyUIImageEngine()
        output_path = str(tmp_path / "output.png")
        result = engine.generate("test prompt", 1024, 768, output_path)

        assert os.path.isfile(output_path)
        with open(output_path, "rb") as f:
            assert f.read() == b"fake-image-content"
        assert result == os.path.abspath(output_path)

    @patch("httpx.Client")
    def test_uses_correct_http_endpoints(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """Verify the correct ComfyUI HTTP endpoints are called."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "test-123"}
        mock_client.post.return_value = post_resp

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "test-123": {
                "status": {"completed": True},
                "outputs": {"1": {"images": [{"filename": "out.png"}]}},
            },
        }
        download_resp = MagicMock()
        download_resp.content = b"data"
        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        engine = ComfyUIImageEngine()
        engine.generate("p", 512, 512, str(tmp_path / "out.png"))

        # POST to /prompt
        mock_client.post.assert_called_once()
        post_url = mock_client.post.call_args[0][0]
        assert post_url.endswith("/prompt")

        # At least one GET to /history/ and one to /view
        get_urls = [call[0][0] for call in mock_client.get.call_args_list]
        assert any("/history/" in u for u in get_urls), (
            f"No /history/ call in {get_urls}"
        )
        assert any("/view" in u for u in get_urls), (
            f"No /view call in {get_urls}"
        )

    @patch("httpx.Client")
    def test_returns_absolute_path(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """Return value is an absolute path to the output file."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "abs-path-test"}
        mock_client.post.return_value = post_resp

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "abs-path-test": {
                "status": {"completed": True},
                "outputs": {"1": {"images": [{"filename": "out.png"}]}},
            },
        }
        download_resp = MagicMock()
        download_resp.content = b"abc"
        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        engine = ComfyUIImageEngine()
        result = engine.generate(
            "p", 512, 512, str(tmp_path / "nested" / "out.png"),
        )
        assert os.path.isabs(result)
        assert result.endswith("out.png")

    @patch("httpx.Client")
    def test_passes_workflow_in_post_body(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """POST body contains a 'prompt' key with the workflow data."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "body-test"}
        mock_client.post.return_value = post_resp

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "body-test": {
                "status": {"completed": True},
                "outputs": {"1": {"images": [{"filename": "out.png"}]}},
            },
        }
        download_resp = MagicMock()
        download_resp.content = b"abc"
        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        engine = ComfyUIImageEngine()
        engine.generate("my prompt", 800, 600, str(tmp_path / "out.png"))

        call_kwargs = mock_client.post.call_args[1]
        assert "json" in call_kwargs
        body = call_kwargs["json"]
        assert "prompt" in body
        workflow = body["prompt"]
        # Workflow is a valid ComfyUI node graph
        assert isinstance(workflow, dict)
        assert "6" in workflow  # CLIPTextEncode node
        assert workflow["6"]["inputs"]["text"] == "my prompt"
        assert "5" in workflow  # EmptyLatentImage node
        assert workflow["5"]["inputs"]["width"] == 800
        assert workflow["5"]["inputs"]["height"] == 600

    @patch("httpx.Client")
    def test_uses_config_host_port(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """Custom host/port from engine config are used in URLs."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "cfg-test"}
        mock_client.post.return_value = post_resp

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "cfg-test": {
                "status": {"completed": True},
                "outputs": {"1": {"images": [{"filename": "out.png"}]}},
            },
        }
        download_resp = MagicMock()
        download_resp.content = b"abc"
        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        engine = ComfyUIImageEngine(
            engine_config={
                "host": "comfyui.internal",
                "port": 9090,
                "protocol": "https",
            },
        )
        engine.generate("p", 512, 512, str(tmp_path / "out.png"))

        post_url = mock_client.post.call_args[0][0]
        assert "https://comfyui.internal:9090" in post_url

        get_urls = [call[0][0] for call in mock_client.get.call_args_list]
        assert all("https://comfyui.internal:9090" in u for u in get_urls)


# =========================================================================
# generate() — error paths (all raise EngineExecutionError, NO PIL fallback)
# =========================================================================


class TestComfyUIImageEngineGenerateErrors:
    """generate() raises EngineExecutionError on any failure."""

    def teardown_method(self) -> None:
        EngineRegistry().clear()
        EngineRegistry().register("comfyui", ComfyUIImageEngine, modality="image")

    def test_httpx_not_installed_raises(self, tmp_path: Any) -> None:
        """ImportError for httpx raises EngineExecutionError."""
        engine = ComfyUIImageEngine()
        original_import = builtins.__import__

        def _mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "httpx":
                raise ImportError("No module named 'httpx'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            with pytest.raises(
                EngineExecutionError,
                match="httpx is required",
            ):
                engine.generate("test", 512, 512, str(tmp_path / "out.png"))

    @patch("httpx.Client")
    def test_connection_error_raises(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """Connection error raises EngineExecutionError."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = ConnectionError("Connection refused")

        engine = ComfyUIImageEngine()
        # Plain ConnectionError → caught by generic `except Exception` handler
        with pytest.raises(
            EngineExecutionError,
            match="Connection refused",
        ):
            engine.generate("test", 512, 512, str(tmp_path / "out.png"))

    @patch("httpx.Client")
    def test_http_error_status_raises(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """HTTP 5xx from POST /prompt raises EngineExecutionError."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.raise_for_status.side_effect = RuntimeError("HTTP 500")
        mock_client.post.return_value = post_resp

        engine = ComfyUIImageEngine()
        with pytest.raises(EngineExecutionError):
            engine.generate("test", 512, 512, str(tmp_path / "out.png"))

    @patch("httpx.Client")
    def test_missing_prompt_id_raises(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """Response without prompt_id raises EngineExecutionError."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"status": "error"}  # no prompt_id
        mock_client.post.return_value = post_resp

        engine = ComfyUIImageEngine()
        with pytest.raises(EngineExecutionError):
            engine.generate("test", 512, 512, str(tmp_path / "out.png"))

    @patch("httpx.Client")
    def test_no_output_image_in_history_raises(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """History with no output images raises EngineExecutionError."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "test-no-img"}
        mock_client.post.return_value = post_resp

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "test-no-img": {
                "status": {"completed": True},
                "outputs": {},  # empty outputs
            },
        }
        mock_client.get.side_effect = [history_resp, history_resp]

        engine = ComfyUIImageEngine()
        with pytest.raises(
            EngineExecutionError,
            match="No output image",
        ):
            engine.generate("test", 512, 512, str(tmp_path / "out.png"))

    @patch("httpx.Client")
    def test_download_http_error_raises(
        self, mock_client_cls: MagicMock, tmp_path: Any
    ) -> None:
        """HTTP error during image download raises EngineExecutionError."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "test-dl-err"}
        mock_client.post.return_value = post_resp

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "test-dl-err": {
                "status": {"completed": True},
                "outputs": {"5": {"images": [{"filename": "out.png"}]}},
            },
        }
        download_resp = MagicMock()
        download_resp.raise_for_status.side_effect = RuntimeError("HTTP 500")

        mock_client.get.side_effect = [history_resp, history_resp, download_resp]

        engine = ComfyUIImageEngine()
        with pytest.raises(EngineExecutionError):
            engine.generate("test", 512, 512, str(tmp_path / "out.png"))

    @patch("httpx.Client")
    @patch("automedia.engines.implementations.image_comfyui.time.monotonic")
    @patch("automedia.engines.implementations.image_comfyui.time.sleep")
    def test_polling_timeout_raises(
        self,
        mock_sleep: MagicMock,
        mock_monotonic: MagicMock,
        mock_client_cls: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Polling loop timeout raises EngineExecutionError."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        post_resp = MagicMock()
        post_resp.json.return_value = {"prompt_id": "slow-prompt"}
        mock_client.post.return_value = post_resp

        pending_resp = MagicMock()
        pending_resp.json.return_value = {
            "slow-prompt": {"status": {"completed": False}},
        }
        mock_client.get.return_value = pending_resp

        # Simulate time advancing past the 1-second timeout:
        # start=0.0, first check=0.0 (0s elapsed → enter loop),
        # second check=5.0 (5s elapsed → exit loop, raise)
        mock_monotonic.side_effect = [0.0, 0.0, 5.0]

        engine = ComfyUIImageEngine(engine_config={"timeout": 1})
        with pytest.raises(
            EngineExecutionError,
            match="did not complete",
        ):
            engine.generate("test", 512, 512, str(tmp_path / "out.png"))
