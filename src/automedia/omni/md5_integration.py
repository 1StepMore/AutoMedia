"""MD5 file tracking for the Omni pipeline (OPP→OL→ORF).

Writes to pipeline_md5.json with per-section keys:
- omni_inputs      — raw files fed into the pipeline
- omni_extraction  — OPP extraction outputs
- omni_translation — OL translation outputs
- omni_orf_outputs — ORF format conversion outputs
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from structlog import get_logger

log = get_logger(__name__)

OMNI_MD5_FILENAME = "pipeline_md5.json"

_OMNI_SECTIONS = ("omni_inputs", "omni_extraction", "omni_translation", "omni_orf_outputs")


def _default_state_dir() -> Path:
    """Return the default state directory (``~/.automedia``)."""
    return Path.home() / ".automedia"


def compute_md5(file_path: str | Path) -> str:
    """Compute MD5 hex digest of a file."""
    h = hashlib.md5()  # noqa: S324 — integrity checksum
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _state_path(state_dir: str | Path | None = None) -> Path:
    """Resolve the path to the pipeline_md5.json state file.

    Args:
        state_dir: Optional directory override.  Falls back to
            ``_default_state_dir()`` when not provided.

    Returns:
        The absolute ``Path`` to the state file.
    """
    if state_dir is not None:
        return Path(state_dir) / OMNI_MD5_FILENAME
    return _default_state_dir() / OMNI_MD5_FILENAME


def _ensure_sections(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure all four omni_* sections exist in state."""
    for section in _OMNI_SECTIONS:
        state.setdefault(section, {})
    return state


def load_state(state_dir: str | Path | None = None) -> dict[str, Any]:
    """Load pipeline_md5.json. Returns empty dict if file missing."""
    path = _state_path(state_dir)
    if not path.is_file():
        return {}
    with open(path) as f:
        return json.load(f)


def save_state(state: dict[str, Any], state_dir: str | Path | None = None) -> None:
    """Save state dict to disk, ensuring omni_* sections."""
    path = _state_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = _ensure_sections(state)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _find_key(state: dict[str, Any], key: str) -> tuple[str | None, dict[str, Any] | None]:
    """Search for *key* across all omni_* sections.

    Returns (section_name, section_dict) or (None, None).
    """
    for section in _OMNI_SECTIONS:
        section_data = state.get(section, {})
        if key in section_data:
            return section, section_data
    return None, None


def get_md5(file_path: str | Path, state_dir: str | Path | None = None) -> str | None:
    """Retrieve stored MD5 for a file. Returns None if not tracked."""
    state = load_state(state_dir)
    state = _ensure_sections(state)
    key = str(Path(file_path).resolve())
    _, section_data = _find_key(state, key)
    if section_data is None:
        return None
    entry = section_data.get(key)
    if entry is None:
        return None
    return entry.get("md5")


def set_md5(
    file_path: str | Path, state_dir: str | Path | None = None, section: str = "omni_extraction"
) -> str:
    """Compute and store MD5 for a file under *section*. Returns the digest."""
    state = load_state(state_dir)
    state = _ensure_sections(state)
    key = str(Path(file_path).resolve())
    digest = compute_md5(file_path)
    state.setdefault(section, {})[key] = {"md5": digest}
    save_state(state, state_dir)
    return digest


def has_changed(file_path: str | Path, state_dir: str | Path | None = None) -> bool:
    """Check if file has changed since last tracking. True if untracked or modified."""
    if not Path(file_path).is_file():
        return True
    current = compute_md5(file_path)
    stored = get_md5(file_path, state_dir)
    return stored is None or current != stored
