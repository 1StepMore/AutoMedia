"""Tests for remote-ComfyUI endpoint awareness in Doctor (#357).

``automedia doctor`` used to hard-probe ``127.0.0.1:8188``. It must probe the
endpoint configured at ``engines.image.comfyui.{host, port, protocol}`` so a
remote (or Dockerized) ComfyUI is checked where it actually lives — the image
engine already honors that config, and the doctor used to disagree with it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from automedia.core.doctor import Doctor

_CONFIG_LOADER = "automedia.core.config_loader.load_config"


def _config_with_comfyui(endpoint: dict[str, Any]) -> dict[str, Any]:
    return {"engines": {"image": {"comfyui": endpoint}}}


class TestComfyuiEndpointConfig:
    """_comfyui_endpoint_config maps merged config onto probe kwargs."""

    def test_reads_host_port_protocol(self) -> None:
        config = _config_with_comfyui({"host": "10.0.0.5", "port": 9200, "protocol": "https"})
        with patch(_CONFIG_LOADER, return_value=config):
            assert Doctor._comfyui_endpoint_config() == {
                "host": "10.0.0.5",
                "port": "9200",
                "protocol": "https",
            }

    def test_partial_config_only_maps_present_keys(self) -> None:
        config = _config_with_comfyui({"host": "comfy.internal"})
        with patch(_CONFIG_LOADER, return_value=config):
            assert Doctor._comfyui_endpoint_config() == {"host": "comfy.internal"}

    def test_empty_config_maps_nothing(self) -> None:
        with patch(_CONFIG_LOADER, return_value={}):
            assert Doctor._comfyui_endpoint_config() == {}

    def test_unavailable_config_falls_back_to_probe_defaults(self) -> None:
        """When load_config raises, the doctor keeps working with defaults."""
        with patch(_CONFIG_LOADER, side_effect=RuntimeError("no config")):
            assert Doctor._comfyui_endpoint_config() == {}

    def test_env_override_reaches_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOMEDIA_ENGINES_IMAGE_COMFYUI_* env vars (highest config layer)
        must be honored — this is the no-file remote switch."""
        monkeypatch.setenv("AUTOMEDIA_ENGINES_IMAGE_COMFYUI_HOST", "192.168.1.20")
        monkeypatch.setenv("AUTOMEDIA_ENGINES_IMAGE_COMFYUI_PORT", "9200")
        monkeypatch.setenv("AUTOMEDIA_ENGINES_IMAGE_COMFYUI_PROTOCOL", "https")
        endpoint = Doctor._comfyui_endpoint_config()
        assert endpoint["host"] == "192.168.1.20"
        assert endpoint["port"] == "9200"
        assert endpoint["protocol"] == "https"


class TestCheckDependenciesUsesEndpoint:
    """check_dependencies threads the configured endpoint into the probe."""

    def test_probe_receives_remote_endpoint(self) -> None:
        config = _config_with_comfyui({"host": "comfy.internal", "port": 9200})
        captured: dict[str, Any] = {}

        def fake_probe(host: str = "127.0.0.1", port: int | str = 8188, **_: Any):
            captured.update(host=host, port=port)
            return True, "ComfyUI reachable"

        with (
            patch(_CONFIG_LOADER, return_value=config),
            patch.object(Doctor, "_resolve_path", return_value="/usr/bin/ok"),
            patch.object(Doctor, "_get_version", return_value="1.0"),
            patch.object(Doctor, "_check_comfyui_http", side_effect=fake_probe),
            patch.object(Doctor, "_check_comfyui_upscale_model", return_value=(True, "present")),
            patch.object(Doctor, "_check_llm_api", return_value=(True, "ok")),
            patch.object(Doctor, "_check_chrome_headless", return_value=(True, None)),
            patch.object(Doctor, "_hyperframes_browser_path", return_value=None),
        ):
            Doctor().check_dependencies()

        assert captured == {"host": "comfy.internal", "port": "9200"}
