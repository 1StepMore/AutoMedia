"""Structural tests for the decomposed ``automedia.mcp`` package (ADR-004).

PR #55 split the monolithic ``server.py`` into submodules
(``allowlist.py``, ``resources.py``, ``tools/``, ...) with ``server.py`` kept
as a backward-compatible facade re-exporting the public symbols.  This module
locks that facade contract:

1. ``automedia.mcp.server`` must re-export ``check_path_allowed`` (the
   allowlist helper gate) so ``from automedia.mcp.server import
   check_path_allowed`` keeps working for existing callers.
2. The decomposed submodules (``allowlist``, ``resources``, ``tools``) must
   keep their module-level symbols importable.
3. ``server.py`` must remain a facade: ``create_server``, ``main``, and a
   non-empty ``__all__``.

All imports happen inside the test functions (``importlib.import_module`` +
``hasattr``) so a missing facade symbol fails as a single clean assertion
instead of a module-level collection crash.
"""


def test_server_exposes_check_path_allowed():
    """The server facade must re-export the allowlist path-check helper.

    ``check_path_allowed`` lives in :mod:`automedia.mcp.allowlist` but is
    *not* re-exported from :mod:`automedia.mcp.server` (only
    ``_require_allowed`` is).  Callers that import it from the server facade
    therefore break — this assertion is RED until the facade re-export lands.
    """
    import importlib

    server = importlib.import_module("automedia.mcp.server")
    assert hasattr(server, "check_path_allowed"), (
        "automedia.mcp.server does not re-export check_path_allowed; "
        "from automedia.mcp.server import check_path_allowed would raise "
        "ImportError. Add the re-export to server.py's allowlist imports "
        "and __all__."
    )


def test_allowlist_module_symbols_available():
    """allowlist.py must keep both path-gating helpers importable."""
    import importlib

    allowlist = importlib.import_module("automedia.mcp.allowlist")
    assert hasattr(allowlist, "check_path_allowed")
    assert hasattr(allowlist, "_require_allowed")
    assert callable(allowlist.check_path_allowed)
    assert callable(allowlist._require_allowed)


def test_resources_module_importable():
    """resources.py must keep all six resource handlers importable."""
    import importlib

    resources = importlib.import_module("automedia.mcp.resources")
    expected = {
        "list_projects_resource",
        "pipeline_status_resource",
        "topic_pool_resource",
        "pipeline_metrics_resource",
        "getting_started_resource",
        "gate_info_resource",
    }
    missing = {name for name in expected if not hasattr(resources, name)}
    assert not missing, f"resources.py missing symbols: {sorted(missing)}"


def test_tools_module_importable():
    """tools/ package must keep re-exporting the tool-handler symbols."""
    import importlib

    tools = importlib.import_module("automedia.mcp.tools")
    for name in ("health_check", "run_pipeline", "get_config"):
        assert hasattr(tools, name), f"automedia.mcp.tools missing {name!r}"


def test_server_keeps_facade_api():
    """server.py must stay a facade: create_server, main, non-empty __all__."""
    import importlib

    server = importlib.import_module("automedia.mcp.server")
    assert hasattr(server, "create_server")
    assert hasattr(server, "main")
    assert callable(server.create_server)
    assert callable(server.main)
    all_ = getattr(server, "__all__", None)
    assert all_ is not None, "server.py must declare a public __all__"
    assert len(all_) > 0, "server.py __all__ must be non-empty"
