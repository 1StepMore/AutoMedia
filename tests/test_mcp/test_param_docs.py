"""Every MCP tool parameter must carry a non-empty description.

MCP clients render the JSON schema per tool; a parameter without a
description forces the calling agent to guess what to pass.  This test
boots the server in-process and asserts that *every* parameter of *every*
registered tool has a non-empty ``description`` in the tool's input
schema.

Protected against regression for AutoMedia #705 (163 parameters across
51 tools had no description at all).
"""

from __future__ import annotations

import pytest

from automedia.mcp.server import create_server


def _iter_param_schemas() -> list[tuple[str, str, dict]]:
    """Collect (tool_name, param_name, param_schema) for every tool param."""
    mcp = create_server()
    entries: list[tuple[str, str, dict]] = []
    for name, tool in mcp._tool_manager._tools.items():  # noqa: SLF001 — in-process introspection
        schema = tool.parameters
        properties: dict = schema.get("properties", {})
        required = set(schema.get("required", []))
        for param, pschema in properties.items():
            pschema = dict(pschema)
            pschema["_required"] = param in required
            entries.append((name, param, pschema))
    return entries


def test_every_tool_param_has_description() -> None:
    entries = _iter_param_schemas()
    assert entries, "no tool parameters discovered — server registration broken?"

    missing = [
        f"{tool}.{param}"
        for tool, param, pschema in entries
        if not str(pschema.get("description", "")).strip()
    ]
    assert not missing, (
        f"{len(missing)} tool parameters lack a description: {sorted(missing)}"
    )


@pytest.mark.parametrize(
    ("tool", "param"),
    [
        ("run_pipeline", "topic"),
        ("run_pipeline", "project_id"),
        ("get_pipeline_progress", "since_index"),
        ("review_decision", "action"),
        ("run_validation_scenario", "scenario_name"),
    ],
)
def test_spot_check_descriptions_are_substantive(tool: str, param: str) -> None:
    """Descriptions must say what to put there, not echo the parameter name."""
    entries = {(t, p): s for t, p, s in _iter_param_schemas()}
    pschema = entries.get((tool, param))
    assert pschema is not None, f"{tool}.{param} not registered"
    desc = str(pschema.get("description", "")).strip()
    assert len(desc) > 20, f"{tool}.{param} description too thin: {desc!r}"
    assert desc.lower() != param.lower()
