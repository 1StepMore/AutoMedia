"""Model configuration schema — dataclass and loader for ``model_config.yaml``.

Public API
----------
- ``ProviderConfig`` dataclass
- ``ModelConfig`` dataclass
- ``load_model_config(path) -> ModelConfig``
- ``save_model_config(path, updates, *, allow_user_scope=False) -> None``
- ``validate_model_config_updates(updates) -> None``
- ``backup_model_config(path) -> Path | None``

Write safety (issue #208)
------------------------
An automated flow once overwrote a real ``~/.automedia/model_config.yaml``:
``provider`` became ``''``, the header comments were lost, and no backup
existed.  ``save_model_config`` therefore validates the update, refuses the
real user config directory unless ``allow_user_scope=True``, and backs the
existing file up to ``model_config.yaml.bak-<UTC timestamp>`` before
writing; a failed backup aborts the write.  The guards themselves live in
:mod:`automedia.manifests.model_config_write_guard`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from automedia.core.credential_loader import load_credential
from automedia.manifests.model_config_write_guard import (
    backup_model_config,
    targets_real_user_config_dir,
    validate_model_config_updates,
)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider/task slot.

    ``api_key`` is resolved via the credential loader when not provided
    explicitly in the YAML.
    """

    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""


@dataclass
class ModelConfig:
    """Top-level model configuration with four task slots.

    Each slot (``text_generation``, ``vision``, ``subtitle_proofread``,
    ``translation``) maps to a :class:`ProviderConfig`.
    """

    text_generation: ProviderConfig = field(default_factory=ProviderConfig)
    vision: ProviderConfig = field(default_factory=ProviderConfig)
    subtitle_proofread: ProviderConfig = field(default_factory=ProviderConfig)
    translation: ProviderConfig = field(default_factory=ProviderConfig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_provider(raw: dict | None) -> ProviderConfig:
    """Parse a single provider dict into a :class:`ProviderConfig`.

    When ``api_key`` is missing or empty in the YAML, the credential loader
    is consulted using the ``provider`` name as the key.
    """
    if not isinstance(raw, dict):
        return ProviderConfig()

    provider_name = str(raw.get("provider", ""))
    api_key = str(raw.get("api_key", ""))

    # Resolve missing API key via credential loader
    if not api_key and provider_name:
        resolved = load_credential(provider_name, provider=provider_name)
        if resolved:
            api_key = resolved

    return ProviderConfig(
        provider=provider_name,
        model=str(raw.get("model", "")),
        base_url=str(raw.get("base_url", "")),
        api_key=api_key,
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_model_config(path: str) -> ModelConfig:
    """Load a ``model_config.yaml`` file and return a :class:`ModelConfig`.

    Parameters
    ----------
    path:
        Filesystem path to the ``model_config.yaml`` file.

    Returns
    -------
    ModelConfig
        A populated config with defaults for missing task slots.

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    ValueError
        When the YAML content is not a mapping.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Model config not found: {path}")

    with open(file_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(f"Model config must be a YAML mapping, got {type(data).__name__}")

    return ModelConfig(
        text_generation=_parse_provider(data.get("text_generation")),
        vision=_parse_provider(data.get("vision")),
        subtitle_proofread=_parse_provider(data.get("subtitle_proofread")),
        translation=_parse_provider(data.get("translation")),
    )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, updates: dict) -> dict:
    """Recursively merge *updates* into *base*, returning a new dict.

    Dict values are merged key-by-key; every other value (including lists
    such as ``fallback``) is replaced wholesale when the update provides it.
    """
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def save_model_config(path: str | Path, updates: dict, *, allow_user_scope: bool = False) -> None:
    """Merge *updates* into an existing ``model_config.yaml`` and write it back.

    Parameters
    ----------
    path:
        Filesystem path to the ``model_config.yaml`` file. The parent
        directory is created if missing.
    updates:
        Mapping shaped ``{"llm": {"<slot>": {...}}}``. Provided keys replace
        existing values; absent keys (e.g. ``fallback``) are preserved. Slots
        not present in *updates* are left untouched.
    allow_user_scope:
        Opt in to writing inside the real user config directory
        (``~/.automedia`` when ``AUTOMEDIA_CONFIG_DIR`` is unset or points
        there).  User-driven surfaces pass ``True``; library callers,
        tests and scripts leave it ``False`` and isolate with
        ``AUTOMEDIA_CONFIG_DIR`` instead.

    Raises
    ------
    ValueError
        When *updates* explicitly writes a blank ``provider`` or
        ``base_url``, or when the target is the real user config directory
        and *allow_user_scope* is ``False``.
    OSError
        When the pre-write backup cannot be created — the write is aborted.

    Notes
    -----
    Order of operations is deliberate: validate the update, check the
    write scope, then back up the existing file, and only then write.
    A failed backup aborts the write instead of overwriting unbacked.

    If the file exists and parses to a mapping it is used as the merge base;
    otherwise (missing, empty, unparseable, or non-mapping content) the base
    is ``{}``. The file is written with owner-only permissions (``0o600``).
    """
    file_path = Path(path)

    validate_model_config_updates(updates)

    if not allow_user_scope and targets_real_user_config_dir(file_path):
        raise ValueError(
            f"Refusing to write {file_path}: it is inside the real user config "
            "directory. Automated/library callers must isolate first — set "
            "AUTOMEDIA_CONFIG_DIR to a temporary directory (what tests and CI do) "
            "— or pass allow_user_scope=True when a human explicitly asked for "
            "this write."
        )

    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        backup_model_config(file_path)
    except OSError as exc:
        raise OSError(
            f"Refusing to overwrite {file_path}: the pre-write backup could not "
            f"be created ({exc}). The file was left untouched."
        ) from exc

    base: dict = {}
    if file_path.is_file():
        try:
            with open(file_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                base = data
        except yaml.YAMLError:
            base = {}

    merged = _deep_merge(base, updates)

    with open(file_path, "w", encoding="utf-8") as fh:
        yaml.dump(
            merged,
            fh,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    os.chmod(file_path, 0o600)
