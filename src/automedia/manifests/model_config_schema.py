"""Model configuration schema — dataclass and loader for ``model_config.yaml``.

Public API
----------
- ``ProviderConfig`` dataclass
- ``ModelConfig`` dataclass
- ``load_model_config(path) -> ModelConfig``
- ``save_model_config(path, updates) -> None``
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from automedia.core.credential_loader import load_credential

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

_TASK_SLOTS = ("text_generation", "vision", "subtitle_proofread", "translation")


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


def save_model_config(path: str | Path, updates: dict) -> None:
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

    Notes
    -----
    If the file exists and parses to a mapping it is used as the merge base;
    otherwise (missing, empty, unparseable, or non-mapping content) the base
    is ``{}``. The file is written with owner-only permissions (``0o600``).
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

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
