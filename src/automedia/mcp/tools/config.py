"""MCP tools for configuration — get_config, update_engine_config."""

from __future__ import annotations

from typing import Any

import yaml
from structlog import get_logger

from automedia.core.paths import get_user_config_dir
from automedia.exceptions import ConfigError
from automedia.mcp.server_types import EngineModality
from automedia.mcp.tools._shared import (
    MCPErrorCode,
    _deep_get,
    _has_secret_keyword,
    _redact_secrets,
    error_response,
    success_response,
)

log = get_logger(__name__)


def get_config(key: str = "") -> dict[str, Any]:
    """Return merged configuration settings (excluding secrets).

    When *key* is empty, returns all non-secret config keys.  When *key*
    is specified, returns the value for that specific config key using
    dot-notation traversal (e.g. ``llm.temperature``).

    Parameters
    ----------
    key:
        Dot-notation config key to look up.  Empty string returns all config.

    Returns
    -------
    dict
        ``{"config": {...}}`` with secrets redacted, or
        ``{"value": ...}`` for a specific key lookup, or
        ``{"error": {"code": "NOT_FOUND", "message": "config key '...' not found"}}``, or
        ``{"error": {"code": "ALLOWLIST_DENIED",
        "message": "secret key not exposed"}}`` when the key is secret.
    """
    try:
        from automedia.core.config_loader import load_config

        config = load_config()

        if not key:
            return success_response({"config": _redact_secrets(config)})

        # Reject direct access to secret keys
        if _has_secret_keyword(key.split(".")[-1]):
            return error_response(MCPErrorCode.ALLOWLIST_DENIED, "secret key not exposed")

        value = _deep_get(config, key)
        if value is None:
            return error_response(
                MCPErrorCode.NOT_FOUND,
                f"config key '{key}' not found",
                "Check config key name",
            )

        # Redact any sub-values if the result is a dict
        if isinstance(value, dict):
            value = _redact_secrets(value)

        return success_response({"value": value})
    except ConfigError as exc:
        return error_response(
            MCPErrorCode.CONFIG_MISSING,
            f"Configuration load failed: {exc}",
        )
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))


def update_engine_config(
    modality: EngineModality,
    setting: str,
    value: str,
) -> dict[str, Any]:
    """Update an engine configuration setting.

    Writes a YAML override file to ``~/.automedia/overrides/rules/``.
    The change takes effect on the next config load (pipeline run).

    Parameters
    ----------
    modality:
        Engine modality: ``"tts"``, ``"asr"``, ``"image"``, or ``"video"``.
    setting:
        Setting name within the modality (e.g. ``"default"``, ``"voice"``,
        ``"host"``, ``"port"``, ``"model"``).
    value:
        Setting value (string). Numeric values will be auto-converted.

    Returns
    -------
    dict
        ``{"status": "ok", "modality": str, "setting": str, "value": str, "file": str}``
        or ``{"error": {"code": ..., "message": ..., "resolution": ...}}`` on failure.
    """
    from datetime import UTC, datetime

    valid_modalities = {"tts", "asr", "image", "video"}

    if modality not in valid_modalities:
        valid_str = ", ".join(sorted(valid_modalities))
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"Invalid modality '{modality}'. Valid: {valid_str}",
        )

    try:
        overrides_dir = get_user_config_dir() / "overrides" / "rules"
        overrides_dir.mkdir(parents=True, exist_ok=True)

        override_data = {
            "engines": {
                modality: {
                    setting: value,
                },
            },
        }

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        filename = f"engine-override-{modality}-{ts}.yaml"
        filepath = overrides_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(override_data, f, default_flow_style=False)

        return success_response(
            {
                "status": "ok",
                "modality": modality,
                "setting": setting,
                "value": value,
                "file": str(filepath),
            }
        )
    except OSError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"File I/O error writing override: {exc}")
    except yaml.YAMLError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}")
