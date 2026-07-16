"""Omni configuration — dataclass and loader for ``omni_config.yaml``.

Public API
----------
- ``OmniConfig`` dataclass
- ``load_omni_config(path) -> OmniConfig``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from structlog import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class OmniConfig:
    """Top-level omni configuration.

    Attributes
    ----------
    integration_mode:
        How adapters integrate with the host process (e.g. ``"sdk"``, ``"subprocess"``).
    max_auto_extract_mb:
        Maximum file size (in MB) for automatic content extraction.
    """

    integration_mode: str = "sdk"
    max_auto_extract_mb: int = 50


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_omni_config(config_path: Path | None = None) -> OmniConfig:
    """Load an ``omni_config.yaml`` file and return an :class:`OmniConfig`.

    When *config_path* is ``None`` the default location
    ``~/.automedia/omni_config.yaml`` is used.  If the file does not exist a
    default :class:`OmniConfig` is returned (graceful degradation).

    Parameters
    ----------
    config_path:
        Explicit path to the YAML config file.  ``None`` means default path.

    Returns
    -------
    OmniConfig
        A populated config with defaults for missing keys.
    """
    path = (
        config_path if config_path is not None else Path.home() / ".automedia" / "omni_config.yaml"
    )

    if not path.is_file():
        return OmniConfig()

    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(f"omni_config must be a YAML mapping, got {type(data).__name__}")

    return OmniConfig(
        integration_mode=str(data.get("integration_mode", "sdk")),
        max_auto_extract_mb=int(data.get("max_auto_extract_mb", 50)),
    )
