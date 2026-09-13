"""Trace-id propagation across every registered MCP tool (issue #13).

Tool responses must carry the correlation id of the in-flight call as a
top-level ``trace_id``.  The dispatcher stamps this at the single FastMCP
``ToolManager.call_tool`` choke point, so tools that build their own response
dicts are covered without per-tool boilerplate.

Tools that take no arguments are invoked through the real dispatcher here;
tools that require arguments (or that cannot run safely in a unit test) are
checked against the trace-aware envelopes in ``mcp_error``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any

import pytest

from automedia.core.logging import bind_correlation_id, get_correlation_id
from automedia.mcp.mcp_error import (
    MCPErrorCode,
    attach_trace_id,
    error_response,
    success_response,
)

#: Tools with no required arguments that must not be driven through the
#: dispatcher in-process.  ``run_validation_suite`` would recursively run the
#: whole scenario library; the two health tools call external LLM providers
#: over the network; ``list_accounts`` raises before returning unless a master
#: key is configured.  Their trace coverage comes from the envelope assertion.
UNSAFE_TO_INVOKE = {
    "run_validation_suite": "runs the entire scenario library recursively",
    "list_accounts": "requires AUTOMEDIA_MASTER_KEY and raises before returning",
    "engine_health": "probes external LLM providers over the network",
    "health_engine": "probes external LLM providers over the network",
}


def _unwrap(raw: Any) -> dict[str, Any]:
    """Extract the structured payload from a FastMCP dispatcher result."""
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], dict):
        return raw[1]
    if isinstance(raw, dict):
        return raw
    raise AssertionError(f"unexpected dispatcher result shape: {raw!r}")


@pytest.fixture()
def isolated_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[None, None, None]:
    """Keep tool side effects (config, projects, pool db) inside tmp_path.

    The no-arg sweep below invokes ``list_projects``, whose path check
    resolves the relative entries in ``mcp_allowlist.yaml`` (``./data/`` …)
    against the current working directory — here ``tmp_path`` — and caches the
    resolved absolute paths in the process-global
    ``automedia.mcp.allowlist._cached_allowlist``.  That cache outlives the
    test and a tmp-relative value denies the real repo paths a later scenario
    needs (``partial-pass-omni-extraction`` then comes out ``failed`` instead
    of ``partial-pass``).  Reset the cache before and after so the fixture
    redirects every piece of state the calls touch, files and cache alike.
    """
    from automedia.mcp.allowlist import _reset_allowlist_cache

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("AUTOMEDIA_POOL_DB", str(tmp_path / "missing-pool.db"))
    _reset_allowlist_cache()
    yield
    _reset_allowlist_cache()


def test_no_arg_tools_carry_trace_id(isolated_env: None) -> None:
    """Every safely-invocable no-arg tool returns a non-empty trace id."""
    from automedia.mcp.server import create_server

    server = create_server()
    tools = server._tool_manager._tools
    invocable = {
        name
        for name, tool in tools.items()
        if not (tool.parameters.get("required") or []) and name not in UNSAFE_TO_INVOKE
    }
    assert len(invocable) > 10, "expected a broad set of no-arg tools to exercise"
    assert set(UNSAFE_TO_INVOKE) <= set(tools), "unsafe-tool names must be real tools"

    for name in sorted(invocable):
        payload = _unwrap(asyncio.run(server.call_tool(name, {})))
        trace_id = payload.get("trace_id")
        assert isinstance(trace_id, str) and trace_id.strip(), (
            f"tool {name!r} response lacks a non-empty trace_id: {payload!r}"
        )


def test_argument_tools_use_trace_aware_envelopes() -> None:
    """Tools skipped in the dispatcher test still emit traced envelopes."""
    correlation_id = bind_correlation_id()
    success = success_response({})
    failure = error_response(MCPErrorCode.PIPELINE_ERROR, "boom")
    assert success["trace_id"] == correlation_id
    assert failure["trace_id"] == correlation_id
    assert failure["success"] is False


def test_producer_set_trace_id_is_never_overwritten() -> None:
    """A producer-set id wins over the ambient correlation id."""
    bind_correlation_id()
    assert success_response({"trace_id": "tool-set"})["trace_id"] == "tool-set"
    assert attach_trace_id({"correlation_id": "tool-set"})["correlation_id"] == "tool-set"
    assert "trace_id" not in attach_trace_id({"correlation_id": "tool-set"})


def test_dispatcher_reuses_bound_id_and_restores_context(isolated_env: None) -> None:
    """A pre-bound id flows into the response and survives the call."""
    from automedia.mcp.server import create_server

    server = create_server()
    bound = bind_correlation_id()
    payload = _unwrap(
        asyncio.run(
            server.call_tool(
                "run_brand_strategy",
                {
                    "brand_name": "Acme",
                    "industry": "SaaS",
                    "target_audience": "developers",
                    "pattern": "a",
                },
            )
        )
    )
    assert payload["trace_id"] == bound
    assert get_correlation_id() == bound


def test_dispatcher_generates_id_when_none_bound(isolated_env: None) -> None:
    """With no ambient id the dispatcher generates one and does not leak it."""
    from automedia.mcp.server import create_server

    server = create_server()
    assert get_correlation_id() is None
    payload = _unwrap(
        asyncio.run(
            server.call_tool(
                "run_brand_strategy",
                {
                    "brand_name": "Acme",
                    "industry": "SaaS",
                    "target_audience": "developers",
                    "pattern": "a",
                },
            )
        )
    )
    assert isinstance(payload["trace_id"], str) and payload["trace_id"].strip()
    assert get_correlation_id() is None
