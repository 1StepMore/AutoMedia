"""Write-safety guards for ``model_config.yaml`` (issue #208).

Split out of :mod:`automedia.manifests.model_config_schema` so the guards
form their own unit: the writer merges, these decide whether the merge may
land at all.

An automated flow once overwrote a real ``~/.automedia/model_config.yaml``:
``provider`` became ``''``, the header comments were lost, and no backup
existed.  The three refusals below make that shape impossible:

1. an explicit empty ``provider`` (or ``base_url``) in the update —
   :func:`validate_model_config_updates` rejects it before anything is
   touched;
2. a target inside the real user config directory — blocked unless the
   caller passes ``allow_user_scope=True`` (user-driven surfaces do; tests
   and scripts isolate with ``AUTOMEDIA_CONFIG_DIR`` instead);
3. an overwrite without a backup — :func:`backup_model_config` copies the
   previous file to ``model_config.yaml.bak-<UTC timestamp>`` first, and a
   failed backup aborts the write.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from automedia.core.paths import get_user_config_dir

# LLM task slots carried by a ``model_config.yaml`` update.  Validation
# walks every slot present in the update, not just the primary one.
_TASK_SLOTS = ("text_generation", "vision", "subtitle_proofread", "translation")

# Keys that must never be written as an empty/whitespace-only string.
_NON_EMPTY_SLOT_KEYS = ("provider", "base_url")


def _slot_sections(updates: dict) -> list[tuple[str, dict]]:
    """Return ``(slot, section)`` pairs for every LLM slot in *updates*."""
    llm = updates.get("llm")
    if not isinstance(llm, dict):
        return []
    return [
        (slot, section)
        for slot, section in llm.items()
        if isinstance(section, dict) and slot in _TASK_SLOTS
    ]


def validate_model_config_updates(updates: dict) -> None:
    """Reject an update that would write a blank ``provider`` / ``base_url``.

    Only keys the update *explicitly* provides are checked, so an update
    that omits ``provider`` (e.g. a ``model``-only change) still merges.

    Raises
    ------
    ValueError
        When an explicit slot value is empty or whitespace-only.
    """
    for slot, section in _slot_sections(updates):
        for key in _NON_EMPTY_SLOT_KEYS:
            if key not in section:
                continue
            value = section[key]
            if isinstance(value, str) and not value.strip():
                raise ValueError(
                    f"Refusing to write an empty llm.{slot}.{key}: a blank value "
                    "is not a valid configuration and resolves silently at runtime "
                    "(issue #208). Pass a real value, or omit the key to keep the "
                    "existing one."
                )


def backup_model_config(path: str | Path) -> Path | None:
    """Copy an existing ``model_config.yaml`` to a timestamped backup.

    The backup lands next to the original as
    ``model_config.yaml.bak-<UTC timestamp>``; the caller must abort the
    write when this raises, so that no overwrite can happen without one.

    Returns
    -------
    Path | None
        The backup path, or ``None`` when there is nothing to back up.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = file_path.with_name(f"{file_path.name}.bak-{stamp}")
    shutil.copy2(file_path, backup_path)
    return backup_path


def _real_user_config_dir() -> Path | None:
    """Return the real ``~/.automedia`` directory, or ``None`` when unknown.

    ``None`` means the host has no resolvable home directory, so no write
    can be attributed to a real user config directory.
    """
    try:
        return (Path.home() / ".automedia").resolve()
    except (RuntimeError, OSError):
        return None


def targets_real_user_config_dir(file_path: Path) -> bool:
    """Report whether *file_path* resolves inside the real user config dir.

    ``AUTOMEDIA_CONFIG_DIR`` pointing anywhere else — the tests/CI
    isolation escape hatch — makes this ``False``.
    """
    real_dir = _real_user_config_dir()
    if real_dir is None:
        return False
    if get_user_config_dir().resolve() != real_dir:
        return False
    try:
        file_path.resolve().relative_to(real_dir)
    except ValueError:
        return False
    return True


__all__ = [
    "backup_model_config",
    "targets_real_user_config_dir",
    "validate_model_config_updates",
]
