"""AutoMedia configuration loader with 6-layer priority merging.

Layer priority (lowest → highest):
    1. Built-in ``automedia/manifests/defaults.yaml``
    2. Project ``.automedia/`` directory (or explicit *config_dir*)
    3. User config root — ``~/.automedia/``, or the directory named by
       ``AUTOMEDIA_CONFIG_DIR`` when set (#478)
    4. ``<user config root>/overrides/rules/*.yaml``
    5. ``<user config root>/overrides/prompts/*.j2``
    6. ``AUTOMEDIA_*`` environment variables (with the lazy ``.env`` overlay
       beneath them), then *overrides* parameter
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from automedia.core.env_overlay import dotenv_overlay
from automedia.core.paths import get_user_config_dir
from automedia.exceptions import ConfigError

_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "manifests" / "defaults.yaml"
_ENV_PREFIX = "AUTOMEDIA_"


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
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


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a single YAML file and return its contents as a dict.

    Returns an empty dict when the file does not exist or is empty.
    """
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _load_yaml_dir(dir_path: str) -> dict[str, Any]:
    """Load every ``*.yaml`` / ``*.yml`` file in *dir_path* and merge them.

    Files are processed in sorted order so the result is deterministic.
    Returns an empty dict when the directory does not exist.
    """
    if not os.path.isdir(dir_path):
        return {}
    merged: dict[str, Any] = {}
    for entry in sorted(os.listdir(dir_path)):
        if entry.endswith((".yaml", ".yml")):
            file_path = Path(dir_path) / entry
            if file_path.is_file():
                merged = deep_merge(merged, _load_yaml_file(file_path))
    return merged


def _load_j2_dir(dir_path: str) -> dict[str, Any]:
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


def _env_to_config() -> dict[str, Any]:
    """Convert ``AUTOMEDIA_*`` environment variables into a nested config dict.

    Convention:
    * The ``AUTOMEDIA_`` prefix is stripped.
    * The remaining key is split on ``_`` and each segment is lowercased.
    * Each segment becomes a level of nesting in the resulting dict.

    Special LLM keys are remapped to the correct ``llm.text_generation.*``
    path for compatibility with the LLM client:

        AUTOMEDIA_LLM_PROVIDER  → llm.text_generation.provider
        AUTOMEDIA_LLM_MODEL     → llm.text_generation.model
        AUTOMEDIA_LLM_BASE_URL  → llm.text_generation.base_url
        AUTOMEDIA_LLM_API_KEY   → llm.text_generation.api_key
        AUTOMEDIA_LLM_TEMPERATURE → llm.text_generation.temperature
        AUTOMEDIA_LLM_MAX_TOKENS → llm.text_generation.max_tokens

    Generically-split keys (e.g. ``AUTOMEDIA_FOO_BAR=z`` → ``{"foo": {"bar": "z"}}``)
    remain the fallback.

    The source mapping is ``{**dotenv_overlay(), **os.environ}``: keys present
    in the real environment win over the ``.env`` overlay, per key.  That keeps
    the documented priority ``environment variables > .env > file config >
    built-in defaults`` for every ``AUTOMEDIA_*`` config key.  ``.env`` is read
    lazily — importing this module never mutates ``os.environ``.
    """
    result: dict[str, Any] = {}

    # Special LLM key remapping
    _llm_key_map: dict[str, list[str]] = {
        "llm_provider": ["llm", "text_generation", "provider"],
        "llm_model": ["llm", "text_generation", "model"],
        "llm_base_url": ["llm", "text_generation", "base_url"],
        "llm_api_key": ["llm", "text_generation", "api_key"],
        "llm_temperature": ["llm", "text_generation", "temperature"],
        "llm_max_tokens": ["llm", "text_generation", "max_tokens"],
    }

    # Non-LLM special key remapping (flatter nesting than generic split)
    _extra_key_map: dict[str, list[str]] = {
        "tavily_api_key": ["tavily", "api_key"],
        # #414: the video engine's degrade switch is a single underscore key;
        # the generic split would nest it as allow/degrade. Spelled out so
        # AUTOMEDIA_ENGINES_VIDEO_HYPERFRAMES_ALLOW_DEGRADE lands exactly on
        # engines.video.hyperframes.allow_degrade.
        "engines_video_hyperframes_allow_degrade": [
            "engines",
            "video",
            "hyperframes",
            "allow_degrade",
        ],
    }

    for key, value in {**dotenv_overlay(), **os.environ}.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        suffix = key[len(_ENV_PREFIX) :]
        # Check for special remapped keys first
        mapped = _llm_key_map.get(suffix.lower())
        if mapped is not None:
            node = result
            for part in mapped[:-1]:
                node = node.setdefault(part, {})
            # Convert numeric fields to proper types
            last_key = mapped[-1]
            if last_key in ("max_tokens", "temperature"):
                try:
                    typed_value: int | float = (
                        int(value) if last_key == "max_tokens" else float(value)
                    )
                except ValueError:
                    typed_value = value  # type: ignore[assignment]  # value is str; typed_value expects int|float but fallback keeps str type
                node[last_key] = typed_value
                continue
            node[last_key] = value
            continue

        # Check for extra remapped keys (non-LLM, cleaner nesting)
        extra_mapped = _extra_key_map.get(suffix.lower())
        if extra_mapped is not None:
            node = result
            for part in extra_mapped[:-1]:
                node = node.setdefault(part, {})
            node[extra_mapped[-1]] = value
            continue

        # Generic split-key fallback
        parts = suffix.lower().split("_")
        if not parts or not parts[0]:
            continue
        node = result
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return result


# ---------------------------------------------------------------------------
# Merged-config validation (C2)
# ---------------------------------------------------------------------------
#
# Curated known keys are type-checked, but ONLY when present: a missing
# optional key is never rejected. Malformed shapes (a present scalar where a
# mapping is required) fail fast with :class:`ConfigError`.


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _is_number(value: object) -> bool:
    """Return ``True`` for ``int``/``float``, excluding ``bool`` (an int subclass)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_int(value: object) -> bool:
    """Return ``True`` for ``int``, excluding ``bool`` (an int subclass)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


# (key path, expected-type label, predicate)
_SCALAR_RULES: tuple[tuple[tuple[str, ...], str, Callable[[object], bool]], ...] = (
    (("llm", "text_generation", "provider"), "str", _is_str),
    (("llm", "text_generation", "model"), "str", _is_str),
    (("llm", "text_generation", "api_key"), "str", _is_str),
    (("llm", "text_generation", "temperature"), "int or float", _is_number),
    (("llm", "text_generation", "timeout"), "int or float", _is_number),
    (("llm", "text_generation", "max_tokens"), "int", _is_int),
    (("content", "min_title_length"), "int", _is_int),
    (("content", "max_title_length"), "int", _is_int),
    (("project", "name"), "str", _is_str),
    (("gate_engine", "hitl_timeout_s"), "int or float", _is_number),
    (("gate_engine", "hitl_on_timeout"), "str", _is_str),
)


def _resolve(config: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, object]:
    """Resolve *path* inside *config* and report whether it is present.

    Returns ``(False, None)`` when any segment is absent. A :class:`ConfigError`
    is raised when a present intermediate segment is not a mapping — that is a
    malformed config shape, not a missing optional key.
    """
    node: object = config
    for depth, part in enumerate(path):
        if not isinstance(node, dict):
            offending = ".".join(path[:depth])
            raise ConfigError(
                f"Invalid config shape at '{offending}': expected dict, got {type(node).__name__}"
            )
        if part not in node:
            return False, None
        node = node[part]
    return True, node


def _validate_str_map(config: dict[str, Any], key: str) -> None:
    present, section = _resolve(config, (key,))
    if not present:
        return
    if not isinstance(section, dict):
        raise ConfigError(
            f"Invalid config shape at '{key}': expected dict, got {type(section).__name__}"
        )
    for child_key, child_value in section.items():
        if not isinstance(child_value, str):
            raise ConfigError(
                f"Invalid config value at '{key}.{child_key}': "
                f"expected str, got {type(child_value).__name__} ({child_value!r})"
            )


def _validate_platforms(config: dict[str, Any]) -> None:
    present, platforms = _resolve(config, ("platforms",))
    if not present:
        return
    if not isinstance(platforms, dict):
        raise ConfigError(
            f"Invalid config shape at 'platforms': expected dict, got {type(platforms).__name__}"
        )
    for name, entry in platforms.items():
        if not isinstance(entry, dict):
            raise ConfigError(
                f"Invalid config shape at 'platforms.{name}': "
                f"expected dict, got {type(entry).__name__}"
            )
        if "enabled" in entry and not _is_bool(entry["enabled"]):
            raise ConfigError(
                f"Invalid config value at 'platforms.{name}.enabled': "
                f"expected bool, got {type(entry['enabled']).__name__} ({entry['enabled']!r})"
            )


def validate_config(config: dict[str, Any]) -> None:
    """Fail-fast validation of the fully-merged configuration.

    Only curated known keys are checked, and only when they are present in
    *config* — a missing optional key is never rejected. A type or shape
    violation raises :class:`~automedia.exceptions.ConfigError` naming the
    offending key path and the expected-vs-actual type.

    Pure function: no I/O and no mutation of *config*.
    """
    for path, expected, predicate in _SCALAR_RULES:
        present, value = _resolve(config, path)
        if present and not predicate(value):
            raise ConfigError(
                f"Invalid config value at '{'.'.join(path)}': "
                f"expected {expected}, got {type(value).__name__} ({value!r})"
            )
    _validate_str_map(config, "paths")
    _validate_platforms(config)


# ---------------------------------------------------------------------------
# Empty-provider probe (issue #208 / #467)
# ---------------------------------------------------------------------------

#: LLM task slots whose ``provider`` must never be an explicitly empty string
#: (same slots the doctor flags in the resolved config).
_LLM_TASK_SLOTS: tuple[str, ...] = (
    "text_generation",
    "vision",
    "subtitle_proofread",
    "translation",
)


def explicitly_empty_llm_provider_slot() -> tuple[str, str] | None:
    """Return ``(slot, path)`` for the first file-layer model config that writes
    an explicit empty ``provider`` for an LLM task slot.

    Issue #208's corruption is written into ``model_config.yaml``; issue #467
    showed the doctor's resolved-config check can be bypassed when the
    ``AUTOMEDIA_LLM_*`` environment layer overrides the provider — the file
    stays clobbered either way, and the guard's job is to name it.  Only
    *explicit* emptiness counts (``provider: ''``); a slot that omits the key
    entirely is the runtime default and is not corruption.

    Scans the user config dir's ``model_config.yaml`` — the same file the
    ``automedia run`` precheck requires.

    Returns:
        ``(slot, file_path)`` or ``None`` when no file layer carries an
        explicitly blank provider (missing/invalid file included).
    """
    path = get_user_config_dir() / "model_config.yaml"
    try:
        if not path.is_file():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    llm = data.get("llm")
    if not isinstance(llm, dict):
        return None
    for slot in _LLM_TASK_SLOTS:
        slot_cfg = llm.get(slot)
        if isinstance(slot_cfg, dict) and "provider" in slot_cfg:
            provider = slot_cfg["provider"]
            if isinstance(provider, str) and not provider.strip():
                return slot, str(path)
    return None


def load_config(
    *,
    config_dir: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    # Snapshot default engines for backward-compat detection
    _engines_default = config.get("engines", {})

    # Layer 2 – project .automedia/
    project_dir = config_dir if config_dir is not None else os.path.join(os.getcwd(), ".automedia")
    config = deep_merge(config, _load_yaml_dir(project_dir))

    # Layer 3 – user config root.  Resolved through paths.get_user_config_dir(),
    # which honours AUTOMEDIA_CONFIG_DIR (#478) — ``automedia demo`` (and any
    # CI/container isolation) points that env var at a private dir and every
    # user-config layer must follow it, not the hardcoded ``~/.automedia``.
    # A nonexistent dir is simply an empty config layer: built-in defaults
    # apply, nothing is created, nothing errors.
    user_dir = str(get_user_config_dir())
    config = deep_merge(config, _load_yaml_dir(user_dir))

    # Layer 4 – <user config root>/overrides/rules/*.yaml
    rules_dir = os.path.join(user_dir, "overrides", "rules")
    config = deep_merge(config, _load_yaml_dir(rules_dir))

    # Layer 5 – <user config root>/overrides/prompts/*.j2
    prompts_dir = os.path.join(user_dir, "overrides", "prompts")
    config = deep_merge(config, _load_j2_dir(prompts_dir))

    # Layer 6a – environment variables
    config = deep_merge(config, _env_to_config())

    # Layer 6b – explicit overrides (highest priority)
    if overrides:
        config = deep_merge(config, overrides)

    # ------------------------------------------------------------------
    # ComfyUI config migration: pipeline.image.comfyui.* → engines.image.comfyui.*
    #
    # The engine abstraction layer moved ComfyUI settings from
    # ``pipeline.image.comfyui.*`` to ``engines.image.comfyui.*``.
    # This block auto-migrates old values as long as the user hasn't
    # explicitly configured the new path.  Users should update their
    # project config (~/.automedia/ or .automedia/) to use the new keys.
    #
    # ``defaults.yaml`` no longer ships a ``pipeline.image.comfyui`` block,
    # so on a default install ``old_comfyui`` is None and this is a no-op.
    # It fires only when a project/user config still sets the legacy path.
    #
    # Deprecated since: engine-abstraction-layer (July 2026)
    # Removal target: engine-abstraction-layer+3 months
    # ------------------------------------------------------------------
    old_comfyui = config.get("pipeline", {}).get("image", {}).get("comfyui")
    if old_comfyui:
        new_comfyui = config.get("engines", {}).get("image", {}).get("comfyui")
        default_comfyui = _engines_default.get("image", {}).get("comfyui")
        # Identity check: if new_comfyui is still the same object as the default,
        # the user hasn't explicitly configured the new path — migrate old values.
        if new_comfyui is default_comfyui:
            warnings.warn(
                "pipeline.image.comfyui.* is deprecated, use engines.image.comfyui.*",
                DeprecationWarning,
                stacklevel=2,
            )
            # Merge rather than replace: the legacy block carries only the keys
            # that existed when the path was deprecated. Replacing wholesale
            # would drop every key added to ``engines.image.comfyui`` since
            # (e.g. base_size, upscale_model), leaving the engine to fall back
            # to its in-code defaults instead of the declared ones.
            config["engines"]["image"]["comfyui"] = deep_merge(
                dict(default_comfyui or {}), dict(old_comfyui)
            )

    validate_config(config)
    return config
