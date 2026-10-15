"""Tests for LLM connectivity check in doctor."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from automedia.core.doctor import Doctor

_HEALTHY_CONFIG: dict[str, Any] = {
    "llm": {
        "text_generation": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "sk-test",
            "base_url": "https://api.deepseek.com/v1",
        }
    }
}


class TestDoctorLlmConnectivity:
    """Doctor.check_dependencies() must include an LLM API check."""

    def test_doctor_results_include_llm_api(self) -> None:
        """Doctor results must include an entry for 'llm_api'."""
        d = Doctor()
        results = d.check_dependencies()
        names = [r["name"] for r in results]
        assert "llm_api" in names

    # NOTE: Mock targets use automedia.core.llm_client.llm_complete because
    # doctor.py imports it via a local import (inside _check_llm_api).
    # Patching at the module where the function is defined (not where it's
    # called) ensures the mock intercepts the local import correctly.
    #
    # ``load_config`` is patched as well (issue #208): the assertions below are
    # about the probe's verdict on a *known* config, not about whatever the
    # host's real ``~/.automedia/model_config.yaml`` happens to contain.

    @patch("automedia.core.config_loader.load_config")
    @patch("automedia.core.llm_client.llm_complete")
    def test_llm_connectivity_reports_installed(
        self, mock_llm: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """When LLM responds, llm_api shows installed=True."""
        mock_load_config.return_value = _HEALTHY_CONFIG
        mock_llm.return_value = "OK"
        d = Doctor()
        results = d.check_dependencies()
        llm_result = next(r for r in results if r["name"] == "llm_api")
        assert llm_result["installed"] is True
        assert llm_result["version"] == "API reachable"

    @patch("automedia.core.config_loader.load_config")
    @patch("automedia.core.llm_client.llm_complete")
    def test_llm_connectivity_reports_missing_on_error(
        self, mock_llm: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """When LLM call fails, llm_api shows installed=False with error detail."""
        from automedia.core.llm_client import LLMError

        mock_load_config.return_value = _HEALTHY_CONFIG
        mock_llm.side_effect = LLMError("API key not found")
        d = Doctor()
        results = d.check_dependencies()
        llm_result = next(r for r in results if r["name"] == "llm_api")
        assert llm_result["installed"] is False
        assert "API key" in (llm_result["version"] or "")

    @patch("automedia.core.llm_client.llm_complete")
    def test_llm_timeout_is_not_fatal(self, mock_llm: MagicMock) -> None:
        """When LLM call times out, llm_api shows installed=False, doctor doesn't crash."""
        mock_llm.side_effect = TimeoutError("connection timed out")
        d = Doctor()
        results = d.check_dependencies()
        llm_result = next(r for r in results if r["name"] == "llm_api")
        assert llm_result["installed"] is False

    @patch("automedia.core.llm_client.llm_complete")
    def test_llm_connectivity_does_not_block_other_checks(self, mock_llm: MagicMock) -> None:
        """An LLM check failure must not crash or block other dependency checks."""
        mock_llm.side_effect = Exception("network failure")
        d = Doctor()
        results = d.check_dependencies()
        # All entries present
        names = [r["name"] for r in results]
        assert "python" in names
        assert "ffmpeg" in names
        assert "llm_api" in names
