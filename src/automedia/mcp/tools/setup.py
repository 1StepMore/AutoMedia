"""Setup and onboarding MCP tools — init, configure LLM, onboard."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from structlog import get_logger

from automedia.mcp.tools._shared import (
    MCPErrorCode,
    error_response,
    success_response,
)
from automedia.mcp.tools.brands import add_brand

log = get_logger(__name__)

__all__ = [
    "configure_llm",
    "init_config",
    "onboard",
]


def init_config(project_dir: str = "") -> dict[str, Any]:
    """Initialize AutoMedia configuration with sensible defaults.

    Creates the ``.automedia/`` directory structure and a default
    ``config.yaml`` in the target directory.  If *project_dir* is
    provided, creates there; otherwise uses the current working
    directory.

    Parameters
    ----------
    project_dir:
        Optional path to the project root.  When empty, the current
        working directory is used.

    Returns
    -------
    dict
        ``{"success": True, "config_dir": str, "config_file": str}``
        on success, or an error dict on failure.
    """
    try:
        target = Path(project_dir).resolve() if project_dir else Path.cwd()
        automedia_dir = target / ".automedia"
        automedia_dir.mkdir(parents=True, exist_ok=True)

        # Write a minimal config.yaml if one doesn't already exist
        config_path = automedia_dir / "config.yaml"
        if not config_path.exists():
            config: dict[str, Any] = {
                "project": {"name": target.name},
            }
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False)
            os.chmod(config_path, 0o600)

        return success_response(
            {
                "success": True,
                "config_dir": str(automedia_dir),
                "config_file": str(config_path),
            }
        )
    except OSError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error initializing config: {exc}"),
        }
    except yaml.YAMLError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}"),
        }


def configure_llm(
    provider: str = "",
    model: str = "",
    api_key: str = "",
) -> dict[str, Any]:
    """Configure the LLM provider for AutoMedia.

    Writes LLM configuration (provider, model, optional API key) to
    ``~/.automedia/model_config.yaml`` by reusing path constants from
    the existing CLI ``init`` command.

    .. warning::

       Storing API keys in config files is less secure than using
       environment variables.  Prefer setting ``AUTOMEDIA_LLM_API_KEY``
       in your shell profile, ``.env`` file, or MCP server ``env`` map.

    Parameters
    ----------
    provider:
        LLM provider name (e.g. ``"openai"``, ``"deepseek"``,
        ``"anthropic"``).
    model:
        Model identifier (e.g. ``"gpt-4o-mini"``, ``"deepseek-chat"``).
        When empty, only the provider is set.
    api_key:
        Optional API key.  Logs a warning that env vars are preferred.

    Returns
    -------
    dict
        ``{"success": True, "provider": str, "model": str,
        "config_file": str}`` on success, or an error dict on failure.
    """
    try:
        from automedia.cli.commands.init_cmd import (
            _MODEL_CONFIG_FILE,
            _USER_CFG_DIR,
        )

        if api_key:
            log.warning(
                "configure_llm: API key stored in plaintext. "
                "Prefer AUTOMEDIA_LLM_API_KEY environment variable instead."
            )

        _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)

        llm_config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": provider,
                },
            },
        }
        if model:
            llm_config["llm"]["text_generation"]["model"] = model
        if api_key:
            llm_config["llm"]["text_generation"]["api_key"] = api_key

        with open(_MODEL_CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(llm_config, f, default_flow_style=False)
        os.chmod(_MODEL_CONFIG_FILE, 0o600)

        return success_response(
            {
                "success": True,
                "provider": provider,
                "model": model,
                "config_file": str(_MODEL_CONFIG_FILE),
            }
        )
    except OSError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error writing config: {exc}"),
        }
    except yaml.YAMLError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}"),
        }


def onboard(
    brand_name: str = "",
    llm_provider: str = "",
    llm_key: str = "",
    base_url: str = "",
) -> dict[str, Any]:
    """One-step onboarding: configure LLM and create a brand profile.

    Delegates to the same config-writing logic as the CLI ``automedia onboard``
    wizard (``configure_llm`` for LLM settings, ``add_brand`` for brand) but
    accepts all parameters directly without interactive prompts.

    Parameters
    ----------
    brand_name:
        Brand name to create (optional — skip by leaving empty).
    llm_provider:
        LLM provider name (e.g. ``"openai"``, ``"deepseek"``).
        When empty, LLM configuration is skipped.
    llm_key:
        LLM API key.  Prefer ``AUTOMEDIA_LLM_API_KEY`` env var instead.
    base_url:
        Optional custom API base URL.

    Returns
    -------
    dict
        ``{"success": True, "brand_name": str, "llm_provider": str,
        "config_file": str}`` on success, or an error dict on failure.
    """
    try:
        from automedia.core.paths import get_user_config_dir

        results: dict[str, Any] = {}
        user_cfg_dir = get_user_config_dir()

        # Configure LLM via configure_llm (delegates to CLI init logic)
        if llm_provider:
            llm_result = configure_llm(provider=llm_provider, api_key=llm_key)
            results["llm"] = {
                "provider": llm_provider,
                "config_file": str(user_cfg_dir / "model_config.yaml"),
            }

            # Write base_url separately if provided
            if base_url:
                cfg_path = user_cfg_dir / "model_config.yaml"
                if cfg_path.exists():
                    raw = cfg_path.read_text(encoding="utf-8")
                    data = yaml.safe_load(raw) or {}
                    llm_node = data.setdefault("llm", {}).setdefault(
                        "text_generation", {}
                    )
                    llm_node["base_url"] = base_url
                    cfg_path.write_text(
                        yaml.dump(
                            data, default_flow_style=False, allow_unicode=True
                        ),
                        encoding="utf-8",
                    )

        # Create brand profile via add_brand (delegates to brand profile schema)
        if brand_name:
            brand_result = add_brand(name=brand_name)
            results["brand"] = {
                "brand_name": brand_name,
                "config_file": str(user_cfg_dir / "brand_profiles.yaml"),
            }

        return success_response(
            {
                "success": True,
                "brand_name": brand_name or "",
                "llm_provider": llm_provider or "",
                "config_dir": str(user_cfg_dir),
                **results,
            }
        )
    except Exception as exc:
        # MCP boundary: catch-all for file I/O errors
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }
