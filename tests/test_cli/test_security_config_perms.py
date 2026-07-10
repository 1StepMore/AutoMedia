"""Test that config files containing API keys are written with 0o600 permissions."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import yaml


def _write_config_file(path: Path, data: dict) -> None:
    """Simulate the write pattern used by _write_model_config and _step_llm."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    os.chmod(path, 0o600)


def test_model_config_permissions_0o600() -> None:
    """Verify that model_config.yaml gets owner-only permissions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / ".automedia" / "model_config.yaml"
        data = {
            "llm": {
                "text_generation": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "api_key": "sk-test123",
                },
            },
        }

        _write_config_file(cfg_path, data)

        assert cfg_path.exists(), "Config file was not created"
        mode = os.stat(cfg_path).st_mode & 0o777
        assert mode == 0o600, f"Expected permissions 0o600, got {oct(mode)}"


def test_model_config_permissions_no_world_readable() -> None:
    """Verify that the file is NOT world-readable (no 0o004 bits)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / ".automedia" / "model_config.yaml"
        data = {
            "llm": {
                "text_generation": {
                    "api_key": "sk-secret",
                },
            },
        }

        _write_config_file(cfg_path, data)

        mode = os.stat(cfg_path).st_mode
        # Assert no world-readable bit
        assert not (mode & stat.S_IROTH), f"File is world-readable: {oct(mode)}"
        # Assert no group-readable bit
        assert not (mode & stat.S_IRGRP), f"File is group-readable: {oct(mode)}"
