"""Windows guard for the validation-scenario suite.

Most scenarios in this package still drive the product through POSIX shell
steps — ``python3 -c ...``, ``/tmp/...`` paths, bash stub executables.  On
Windows those steps fail with ``WinError 193`` (the stub is not a valid Win32
executable) and ``ModuleNotFoundError: No module named 'automedia'``, i.e. the
suite reports product failures that are really "this shell does not exist
here".

CI already runs this package on Linux only: the Windows job
(``.github/workflows/ci.yml`` → ``test-windows-smoke``) exercises a curated
subset and does not include ``tests/test_validation``.  This guard makes a
local Windows ``pytest tests/`` behave the same way instead of drowning the
real signal in environment noise.

Exception: modules whose scenarios have been rewritten portable (no /tmp pins,
no bash-isms — #564) stay collectable on Windows so the portability keeps a
local regression guard.  Add a module there only after its scenarios truly
run on win32.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PORTABLE_MODULES = {
    "test_rollback_behavior.py",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip non-portable validation scenarios on Windows (POSIX shell required)."""
    if sys.platform != "win32":
        return
    skip = pytest.mark.skip(
        reason="validation scenarios shell out to POSIX tools; run them on Linux (see ci.yml)"
    )
    for item in items:
        if "test_validation" not in str(item.fspath):
            continue
        if Path(str(item.fspath)).name in _PORTABLE_MODULES:
            continue
        item.add_marker(skip)
