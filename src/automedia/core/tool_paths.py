"""Tool resolution with persistence — issue #510 (ffmpeg/ffprobe in own tools dir).

``ffmpeg``/``ffprobe`` may be installed into AutoMedia's *own* tools
directory (``%LOCALAPPDATA%\\automedia-tools\\bin`` on Windows, an XDG data
dir elsewhere) which is not on ``PATH``. Every historical resolution point
used a bare ``shutil.which``, so an installed tool was reported missing, and
each discovery — when it did succeed — was forgotten before the next call.

``find_tool`` resolves a tool in this order:

1. The path pinned in ``<user config dir>/tools.yaml`` (``tool_paths.<name>``),
   resolved through :func:`automedia.core.paths.get_user_config_dir` so it
   honours ``AUTOMEDIA_CONFIG_DIR``. When pinned, the file must exist or
   :class:`ToolPathError` is raised — a stale pin must fail loudly, never
   silently degrade back to a PATH scan (#510).
2. ``shutil.which(name)`` — the classic PATH lookup.
3. The own tools directory (``AUTOMEDIA_TOOLS_DIR`` env override, then the
   platform default above).

A tools-directory hit is written back to ``tools.yaml`` (best effort) so the
absolute path survives PATH changes and future runs skip the scan. PATH hits
are not pinned: PATH-managed entry points move on reinstall, and pinning
them would manufacture stale pins.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from automedia.core.paths import get_user_config_dir

logger = logging.getLogger(__name__)

TOOLS_CONFIG_FILENAME = "tools.yaml"
"""File in the user config dir holding ``tool_paths`` pins (merged at layer 3)."""

TOOLS_DIR_ENV_VAR = "AUTOMEDIA_TOOLS_DIR"
"""Optional override for the own tools directory (absolute path)."""

_PINNABLE_TOOLS = frozenset({"ffmpeg", "ffprobe"})
"""Tools whose discovery is persisted to ``tools.yaml``.

Scoped to the binaries this product ships into its own tools directory
(#510): persisting a pin for every CLI that merely happens to be on PATH
(e.g. ``edge-tts`` from pip) would turn a routine reinstall into a stale-pin
error later.
"""


class ToolPathError(RuntimeError):
    """A pinned tool path is set but no longer exists on disk.

    Raised instead of silently falling back to PATH: the operator pinned an
    absolute path deliberately, and a silent fallback would hide the drift
    between the pin and reality (#510).
    """


def tools_bin_dir() -> Path | None:
    """Return AutoMedia's own tools directory, or ``None`` when undeterminable.

    ``AUTOMEDIA_TOOLS_DIR`` wins when set. The default is
    ``%LOCALAPPDATA%\\automedia-tools\\bin`` on Windows and
    ``$XDG_DATA_HOME/automedia-tools/bin`` (``~/.local/share/...``) elsewhere.
    The directory is not required to exist.
    """
    override = os.environ.get(TOOLS_DIR_ENV_VAR, "")
    if override:
        return Path(os.path.expanduser(override))
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            return None
        return Path(local_app_data) / "automedia-tools" / "bin"
    data_home = os.environ.get("XDG_DATA_HOME", "") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return Path(data_home) / "automedia-tools" / "bin"


def _tools_config_path() -> Path:
    return get_user_config_dir() / TOOLS_CONFIG_FILENAME


def _read_pins() -> dict[str, Any]:
    try:
        with open(_tools_config_path(), encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Could not read %s: %s", _tools_config_path(), exc)
        return {}
    pins = data.get("tool_paths") if isinstance(data, dict) else None
    return pins if isinstance(pins, dict) else {}


def _persist_pin(name: str, path: str) -> None:
    """Write *name*'s absolute path back into ``tools.yaml`` (best effort).

    Failures only warn: persistence is an optimisation, and a read-only
    config dir must not turn a working tool into an error.
    """
    config_path = _tools_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(config_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        pins = data.setdefault("tool_paths", {})
        if not isinstance(pins, dict):
            pins = {}
            data["tool_paths"] = pins
        if pins.get(name) == path:
            return
        pins[name] = path
        with open(config_path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info("Pinned %s -> %s in %s", name, path, config_path)
    except OSError as exc:
        logger.warning("Could not persist %s path to %s: %s", name, config_path, exc)


def find_tool(name: str, *, persist: bool = True) -> str | None:
    """Resolve *name* to an absolute path, or ``None`` when nowhere to be found.

    Resolution order: pinned ``tool_paths.<name>`` (missing file ⇒
    :class:`ToolPathError`) → ``PATH`` → AutoMedia's own tools directory.
    A PATH/tools-directory hit is persisted back into ``tools.yaml`` unless
    *persist* is off (used where writing config is unwanted, e.g. diagnostics).

    Raises
    ------
    ToolPathError
        When a pin exists for *name* but its file is gone.
    """
    pin = _read_pins().get(name)
    if pin:
        pin_str = str(pin)
        if os.path.isfile(pin_str):
            return pin_str
        raise ToolPathError(
            f"Tool '{name}' is pinned to '{pin_str}' in "
            f"{_tools_config_path()} but that file no longer exists. "
            f"Reinstall the tool or remove the stale tool_paths.{name} entry."
        )

    path = shutil.which(name)
    if path:
        # PATH hits are not pinned: PATH-managed entry points move on
        # reinstall (pip/pipx/npm), and freezing them into tools.yaml would
        # manufacture stale pins. Only the own-tools-dir discovery — the one
        # PATH knows nothing about (#510) — is persisted.
        return path

    tools_dir = tools_bin_dir()
    if tools_dir is not None:
        path = shutil.which(name, path=str(tools_dir))
        if path:
            absolute = str(Path(path).resolve())
            if persist and name in _PINNABLE_TOOLS:
                _persist_pin(name, absolute)
            return absolute

    return None
