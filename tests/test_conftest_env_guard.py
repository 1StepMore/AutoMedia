"""Pin the env-leak guard's watchlist against silent shrinkage.

``tests/conftest.py`` guards the session against import-time ``os.environ``
mutations.  The watchlist only works while it lists the variable classes the
suite actually asserts on — #518 was exactly the class that slipped through
(``MCP_ALLOWED_DIRECTORIES``, read by the Omni MCP adapters' ``validate_env``).
This module loads the conftest by path (``tests/`` is not a package) and pins
the members that guard real test assertions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_CONFTEST_PATH = Path(__file__).resolve().parent / "conftest.py"


def _load_conftest() -> Any:
    """Load ``tests/conftest.py`` as a standalone module (tests/ is not a package)."""
    spec = importlib.util.spec_from_file_location("conftest_under_test", _CONFTEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_watchlist_still_covers_the_original_automedia_vars() -> None:
    module = _load_conftest()
    for name in (
        "AUTOMEDIA_MASTER_KEY",
        "AUTOMEDIA_FAKE_LLM",
        "AUTOMEDIA_LLM_API_KEY",
        "AUTOMEDIA_CONFIG_DIR",
    ):
        assert name in module._ENV_WATCHLIST


def test_watchlist_covers_the_omni_mcp_allowed_directories_class() -> None:
    """> #518: the Omni MCP adapters read these in ``validate_env()``."""
    module = _load_conftest()
    for name in (
        "MCP_ALLOWED_DIRECTORIES",
        "OL_MCP_ALLOWED_DIRS",
        "OPP_MCP_ALLOWED_DIRS",
        "ORF_MCP_ALLOWED_DIRS",
    ):
        assert name in module._ENV_WATCHLIST
