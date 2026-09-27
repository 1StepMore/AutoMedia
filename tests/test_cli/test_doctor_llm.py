"""Tests for ``automedia doctor`` LLM/fallback configuration warnings (issue #83).

WAVE-1: only the doctor command surfaces the warnings. The writers that
consume the ``fallback`` chain are handled by later waves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.core.doctor import Doctor

runner = CliRunner()

# ===================================================================
# Shared fixtures / helpers
# ===================================================================

ALL_INSTALLED: list[dict[str, Any]] = [
    {"name": "python", "installed": True, "version": "Python 3.11.4", "path": "/usr/bin/python3"},
    {"name": "bun", "installed": True, "version": "bun 1.2.3", "path": "/usr/bin/bun"},
    {"name": "ffmpeg", "installed": True, "version": "ffmpeg 7.0", "path": "/usr/bin/ffmpeg"},
    {"name": "whisper", "installed": True, "version": "1.0", "path": "/usr/bin/whisper"},
    {"name": "edge-tts", "installed": True, "version": "1.0", "path": "/usr/bin/edge-tts"},
    {"name": "hyperframes", "installed": True, "version": "1.0", "path": "/usr/bin/hyperframes"},
    {
        "name": "chrome",
        "installed": True,
        "version": None,
        "path": "/usr/bin/google-chrome",
        "headless_ok": True,
        "headless_message": None,
    },
    {"name": "comfyui", "installed": True, "version": "ComfyUI reachable", "path": None},
    {"name": "llm_api", "installed": True, "version": "API reachable", "path": None},
]

NO_FALLBACK_MSG = (
    "No LLM fallback chain configured. If the primary provider fails, calls fail "
    "immediately. Re-run `automedia onboard --step llm` to add a backup provider, "
    "or edit model_config.yaml."
)


def _write_model_config(tmp_path: Path, content: str) -> Path:
    """Write ``model_config.yaml`` into *tmp_path* and return its path."""
    path = tmp_path / "model_config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _stub_all_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub Doctor.check_dependencies so every dependency reports installed."""
    monkeypatch.setattr(Doctor, "check_dependencies", lambda self: ALL_INSTALLED)


def _invoke_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Run ``automedia --json doctor`` with deps stubbed and config dir isolated."""
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
    _stub_all_installed(monkeypatch)
    result = runner.invoke(app, ["--json", "doctor"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ===================================================================
# Tests
# ===================================================================


class TestDoctorLlmJson:
    """JSON mode LLM/fallback warnings."""

    def test_json_llm_warning_when_no_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No fallback chain -> no-fallback warning, config path, status ok."""
        cfg = _write_model_config(
            tmp_path,
            "llm:\n  text_generation:\n    provider: deepseek\n    model: deepseek-chat\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert data["llm"]["model_config"] == str(cfg)
        assert NO_FALLBACK_MSG in data["llm"]["warnings"]

    def test_json_warns_incomplete_fallback_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fallback entry with no resolvable api_key -> incomplete-entry warning."""
        _write_model_config(
            tmp_path,
            "llm:\n"
            "  text_generation:\n"
            "    provider: deepseek\n"
            "    model: deepseek-chat\n"
            "    base_url: https://api.deepseek.com/v1\n"
            "    fallback:\n"
            "      - provider: provider-with-no-key-abc\n"
            "        model: some-model\n"
            "        base_url: https://example.invalid/v1\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert any(
            "fallback entry 1" in warning and "usable api_key" in warning
            for warning in data["llm"]["warnings"]
        )

    def test_json_no_warning_when_fallback_key_resolvable_via_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reported bug: key kept in the environment must not warn as incomplete."""
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-from-env")
        _write_model_config(
            tmp_path,
            "llm:\n"
            "  text_generation:\n"
            "    provider: deepseek\n"
            "    model: deepseek-chat\n"
            "    base_url: https://api.deepseek.com/v1\n"
            "    fallback:\n"
            "      - provider: openai\n"
            "        model: gpt-4o\n"
            "        base_url: https://api.openai.com/v1\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert not any("fallback entry 1" in warning for warning in data["llm"]["warnings"])

    def test_json_no_warning_when_fallback_inherits_base_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fallback without base_url inherits the primary's -> no warning."""
        _write_model_config(
            tmp_path,
            "llm:\n"
            "  text_generation:\n"
            "    provider: deepseek\n"
            "    model: deepseek-chat\n"
            "    base_url: https://api.deepseek.com/v1\n"
            "    fallback:\n"
            "      - provider: openai\n"
            "        model: gpt-4o\n"
            "        api_key: sk-test\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert not any("fallback entry 1" in warning for warning in data["llm"]["warnings"])

    def test_json_warns_when_fallback_key_unresolvable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key that resolves nowhere (env, config, store) -> warning."""
        _write_model_config(
            tmp_path,
            "llm:\n"
            "  text_generation:\n"
            "    provider: deepseek\n"
            "    model: deepseek-chat\n"
            "    base_url: https://api.deepseek.com/v1\n"
            "    fallback:\n"
            "      - provider: no-such-provider-xyz\n"
            "        model: some-model\n"
            "        base_url: https://example.invalid/v1\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert any(
            "fallback entry 1" in warning and "usable api_key" in warning
            for warning in data["llm"]["warnings"]
        )

    def test_json_warns_on_unexpanded_api_key_placeholder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A literal ${VAR} api_key is not expanded by the loader -> warning."""
        _write_model_config(
            tmp_path,
            "llm:\n"
            "  text_generation:\n"
            "    provider: deepseek\n"
            "    model: deepseek-chat\n"
            "    base_url: https://api.deepseek.com/v1\n"
            "    fallback:\n"
            "      - provider: openai\n"
            "        model: gpt-4o\n"
            '        api_key: "${OPENAI_API_KEY}"\n'
            "        base_url: https://api.openai.com/v1\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert any(
            "fallback entry 1" in warning and "unexpanded" in warning
            for warning in data["llm"]["warnings"]
        )

    def test_json_warns_fallback_entry_without_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An entry without provider is skipped by the runtime -> warning."""
        _write_model_config(
            tmp_path,
            "llm:\n"
            "  text_generation:\n"
            "    provider: deepseek\n"
            "    model: deepseek-chat\n"
            "    base_url: https://api.deepseek.com/v1\n"
            "    fallback:\n"
            "      - model: gpt-4o\n"
            "        api_key: sk-test\n"
            "        base_url: https://api.openai.com/v1\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert any(
            "fallback entry 1" in warning and "skipped" in warning
            for warning in data["llm"]["warnings"]
        )

    def test_json_warns_model_base_url_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Official deepseek model pointed at a proxy host -> mismatch warning."""
        _write_model_config(
            tmp_path,
            "llm:\n"
            "  text_generation:\n"
            "    provider: deepseek\n"
            "    model: deepseek-chat\n"
            "    base_url: https://my-proxy.example/v1\n"
            "    fallback:\n"
            "      - provider: openai\n"
            "        model: gpt-4o\n"
            "        api_key: sk-test\n"
            "        base_url: https://api.openai.com/v1\n",
        )
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert (
            "Primary model 'deepseek-chat' may not match base_url "
            "'https://my-proxy.example/v1' for provider 'deepseek'." in data["llm"]["warnings"]
        )

    def test_missing_config_no_warnings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No model_config.yaml -> null config, empty warnings, status ok."""
        data = _invoke_json(monkeypatch, tmp_path)

        assert data["status"] == "ok"
        assert data["llm"]["model_config"] is None
        assert data["llm"]["warnings"] == []


class TestDoctorLlmText:
    """Text mode LLM/fallback warnings."""

    def test_text_mode_warns_and_keeps_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Warnings print in text mode without touching the final summary."""
        _write_model_config(
            tmp_path,
            "llm:\n  text_generation:\n    provider: deepseek\n    model: deepseek-chat\n",
        )
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        _stub_all_installed(monkeypatch)

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "LLM Configuration:" in result.output
        assert f"  ⚠ {NO_FALLBACK_MSG}" in result.output
        assert "All dependencies satisfied." in result.output
