"""Windows guard for the validation-scenario suite.

Every scenario in this package drives the product through POSIX shell steps —
``python3 -c ...``, ``/tmp/...`` paths, bash stub executables.  On Windows those
steps fail with ``WinError 193`` (the stub is not a valid Win32 executable) and
``ModuleNotFoundError: No module named 'automedia'``, i.e. the suite reports
product failures that are really "this shell does not exist here".

CI already runs this package on Linux only: the Windows job
(``.github/workflows/ci.yml`` → ``test-windows-smoke``) exercises a curated
subset and does not include ``tests/test_validation``.  This guard makes a
local Windows ``pytest tests/`` behave the same way instead of drowning the
real signal in environment noise.
"""

from __future__ import annotations

import sys

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip every validation scenario on Windows (POSIX shell required)."""
    if sys.platform != "win32":
        return
    skip = pytest.mark.skip(
        reason="validation scenarios shell out to POSIX tools; run them on Linux (see ci.yml)"
    )
    for item in items:
        if "test_validation" in str(item.fspath):
            item.add_marker(skip)
