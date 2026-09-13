"""Non-LLM external-tool stub seam for the validation harness (gap T-21).

``AUTOMEDIA_VALIDATION_STUB_BIN`` names a committed fixture directory holding
stand-in executables (``ffmpeg``, ``ffprobe``, ``whisper``, ``edge-tts``,
``bun``, ``hyperframes``).  When the variable is set,
:func:`apply_stub_bin_to_path` prepends that directory to this process's
``PATH``, so a subsequently dispatched pipeline run resolves the stubs instead
of the real tools and a machine with none of the external binaries installed
can still exercise a mode journey.

The prepend runs once per process and is idempotent.  It covers both surfaces
the engine uses: ``subprocess`` runs inherit ``os.environ``, and in-process
``shutil.which`` checks read the same ``PATH``.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

STUB_BIN_ENV = "AUTOMEDIA_VALIDATION_STUB_BIN"
"""Env var naming the committed stub-bin fixture directory (gap T-21)."""


def apply_stub_bin_to_path(
    environ: MutableMapping[str, str] | None = None,
) -> str | None:
    """Prepend the stub-bin directory to ``PATH``; return it, or None.

    Unset or empty ``AUTOMEDIA_VALIDATION_STUB_BIN`` is a no-op returning
    ``None`` (the real ``PATH`` is untouched).  A directory already on
    ``PATH`` is not duplicated, so repeated calls are idempotent.
    """
    env = os.environ if environ is None else environ
    raw = env.get(STUB_BIN_ENV, "").strip()
    if not raw:
        return None
    stub_dir = str(Path(raw).expanduser())
    parts = [part for part in env.get("PATH", "").split(os.pathsep) if part]
    if stub_dir in parts:
        return stub_dir
    env["PATH"] = os.pathsep.join([stub_dir, *parts])
    return stub_dir
