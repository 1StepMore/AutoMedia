"""AutoMedia configuration loader with 6-layer priority merging.

Layer priority (lowest → highest):
    1. Built-in ``automedia/manifests/defaults.yaml``
    2. Project ``.automedia/`` directory (or explicit *config_dir*)
    3. User ``~/.automedia/`` directory
    4. ``~/.automedia/overrides/rules/*.yaml``
    5. ``~/.automedia/overrides/prompts/*.j2``
    6. ``AUTOMEDIA_*`` environment variables, then *overrides* parameter
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "manifests" / "defaults.yaml"
_ENV_PREFIX = "AUTOMEDIA_"


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*.

    * Dict values are merged recursively.
    * All other values (scalars, lists) are overwritten by *override*.
    * Neither input is mutated.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# File / directory loaders
# ---------------------------------------------------------------------------

def _load_yaml_file(path: Path) -> dict:
    """Load a single YAML file and return its contents as a dict.

    Returns an empty dict when the file does not exist or is empty.
    """
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _load_yaml_dir(dir_path: str) -> dict:
    """Load every ``*.yaml`` / ``*.yml`` file in *dir_path* and merge them.

    Files are processed in sorted order so the result is deterministic.
    Returns an empty dict when the directory does not exist.
    """
    if not os.path.isdir(dir_path):
        return {}
    merged: dict = {}
    for entry in sorted(os.listdir(dir_path)):
        if entry.endswith((".yaml", ".yml")):
            file_path = Path(dir_path) / entry
            if file_path.is_file():
                merged = deep_merge(merged, _load_yaml_file(file_path))
    return merged


def _load_j2_dir(dir_path: str) -> dict:
    """Load all ``*.j2`` template files as prompt strings.

    Each file's content is stored under ``prompts[<stem>]`` where *stem* is
    the filename without the ``.j2`` extension.

    Returns an empty dict when the directory does not exist.
    """
    if not os.path.isdir(dir_path):
        return {}
    prompts: dict[str, str] = {}
    for entry in sorted(os.listdir(dir_path)):
        if entry.endswith(".j2"):
            file_path = Path(dir_path) / entry
            if file_path.is_file():
                stem = entry[:-3]  # strip ".j2"
                with open(file_path, encoding="utf-8") as fh:
                    prompts[stem] = fh.read()
    return {"prompts": prompts} if prompts else {}


# ---------------------------------------------------------------------------
# Environment variable loader
# ---------------------------------------------------------------------------

def _env_to_config() -> dict:
    """Convert ``AUTOMEDIA_*`` environment variables into a nested config dict.

    Convention:
    * The ``AUTOMEDIA_`` prefix is stripped.
    * The remaining key is split on ``_`` and each segment is lowercased.
    * Each segment becomes a level of nesting in the resulting dict.

    Example::

        AUTOMEDIA_LLM_API_KEY=sk-xxx
        → {"llm": {"api": {"key": "sk-xxx"}}}
    """
    result: dict = {}
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        parts = key[len(_ENV_PREFIX) :].lower().split("_")
        if not parts or not parts[0]:
            continue
        node = result
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(
    *,
    config_dir: str | None = None,
    overrides: dict | None = None,
) -> dict:
    """Load and merge configuration from six layers (lowest → highest priority).

    Parameters
    ----------
    config_dir:
        Explicit path to the project-level ``.automedia/`` directory.
        When *None*, ``$CWD/.automedia/`` is used.
    overrides:
        Highest-priority key/value pairs (e.g. from CLI ``--override`` flags).

    Returns
    -------
    dict
        The fully-merged configuration dictionary.
    """
    # Layer 1 – built-in defaults
    config = _load_yaml_file(_DEFAULTS_PATH)

    # Layer 2 – project .automedia/
    project_dir = (
        config_dir
        if config_dir is not None
        else os.path.join(os.getcwd(), ".automedia")
    )
    config = deep_merge(config, _load_yaml_dir(project_dir))

    # Layer 3 – user ~/.automedia/
    user_dir = os.path.join(os.path.expanduser("~"), ".automedia")
    config = deep_merge(config, _load_yaml_dir(user_dir))

    # Layer 4 – ~/.automedia/overrides/rules/*.yaml
    rules_dir = os.path.join(user_dir, "overrides", "rules")
    config = deep_merge(config, _load_yaml_dir(rules_dir))

    # Layer 5 – ~/.automedia/overrides/prompts/*.j2
    prompts_dir = os.path.join(user_dir, "overrides", "prompts")
    config = deep_merge(config, _load_j2_dir(prompts_dir))

    # Layer 6a – environment variables
    config = deep_merge(config, _env_to_config())

    # Layer 6b – explicit overrides (highest priority)
    if overrides:
        config = deep_merge(config, overrides)

    return config
