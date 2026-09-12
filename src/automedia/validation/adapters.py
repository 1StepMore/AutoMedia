"""Surface adapters for the agent-tester validation engine (W1-T4).

Strategy pattern (guide §3.2): the engine never calls a surface directly —
every step goes through one adapter, selected by step ``kind``.  Three
surfaces ship (no HTTP adapter, plan decision 1):

* ``ToolAdapter`` — one MCP tool call through the injected FastMCP
  instance (the real dispatcher, never a mock).
* ``CLIAdapter`` — one subprocess run of a CLI command.
* ``FileAdapter`` — one artifact file inspection (exists/size/JSON).

Async contract (plan review fix C3): FastMCP 1.27.2 ``call_tool`` is a
coroutine, so ``ToolAdapter.run_async`` is the real implementation and the
engine's async step executor (W1-T7) always uses it.  ``asyncio.run()``
appears only in ``ToolAdapter.run`` — a documented test/CLI-path
convenience — never on the engine path.

The FastMCP instance is injected (W4 wires the validation MCP tools): this
module MUST NOT import ``automedia.mcp.server`` (circular import hazard).
The server is typed structurally via :class:`ToolCallable`.

Unwrap contract (verified against mcp 1.27.2 in .venv): ``call_tool``
returns ``Sequence[ContentBlock] | dict[str, Any]`` per its signature; a
dict-annotated tool (all 59 AutoMedia tools) actually yields the tuple
``(unstructured blocks, structured dict)``.  ``_unwrap_result`` therefore
handles a bare dict, a content-block sequence (``content[0].text`` JSON),
and the ``(blocks, dict)`` tuple (preferring the authoritative structured
dict) — and never crashes on malformed JSON.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from automedia.validation.schema import DEFAULT_TIMEOUT_SECONDS, Step

_JSON_PARSE_LIMIT: int = 4 * 1024 * 1024
"""Artifacts larger than this get existence/size facts only — no JSON read."""


@dataclass
class StepResult:
    """What every adapter hands back (guide §3.2)."""

    ok: bool
    output: dict[str, Any]


class ToolCallable(Protocol):
    """Structural type of the injected FastMCP instance (duck-typed).

    Deliberately returns ``object``: the concrete shape is
    ``Sequence[ContentBlock] | dict[str, Any]``, which the adapter unwraps.
    """

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        """Call one registered MCP tool; return content blocks or a dict."""
        ...


class Adapter(Protocol):
    """One step -> one real call on a surface (strategy interface, guide §3.2)."""

    def run(self, step: Step) -> StepResult:
        """Turn one step into one real call on the surface; return the result."""
        ...


def _block_text(block: object) -> str:
    """Extract the text payload of a content block, with fallbacks.

    Prefers the ``.text`` attribute (mcp ``TextContent``); falls back to a
    ``.content`` attribute, then to ``str()`` of the block.
    """
    text = getattr(block, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(block, "content", None)
    if isinstance(content, str):
        return content
    return str(block)


def _parse_text(text: str) -> dict[str, Any]:
    """JSON-parse a block's text into a dict, never raising.

    A malformed or non-JSON text is wrapped as
    ``{"success": True, "data": {"text": <raw text>}}`` so the adapter never
    crashes on the surface shape; a parse that yields a non-dict value is
    wrapped under ``data``.
    """
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {"success": True, "data": {"text": text}}
    if isinstance(parsed, dict):
        return parsed
    return {"success": True, "data": parsed}


def _unwrap_result(raw: object) -> dict[str, Any]:
    """Normalise both documented call_tool return shapes to one dict.

    * a ``dict`` is used verbatim;
    * a ``(blocks, structured_dict)`` tuple (the actual shape mcp 1.27.2
      produces for dict-annotated tools) yields the structured dict;
    * a ``Sequence[ContentBlock]`` is reduced to ``content[0]``'s text and
      JSON-parsed via :func:`_parse_text`.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        if len(raw) == 2 and isinstance(raw[1], dict):
            return raw[1]
        if raw:
            return _parse_text(_block_text(raw[0]))
        return {"success": True, "data": {"text": ""}}
    return {"success": True, "data": {"text": str(raw)}}


class ToolAdapter:
    """MCP surface: one tool call through the injected FastMCP instance.

    The server is the same FastMCP instance captured from
    ``create_server()`` (W4 wires it) — the real dispatcher, never a mock.
    """

    def __init__(self, server: ToolCallable) -> None:
        self._server = server

    async def run_async(self, step: Step) -> StepResult:
        """Call ``step.tool`` with ``step.arguments`` and unwrap the result.

        Never raises: call_tool failures are captured into
        ``StepResult(ok=False, ...)``.  This is the engine's real path;
        tool-level timeout enforcement belongs to the engine's async step
        executor (W1-T7 wraps this in ``asyncio.wait_for``).
        """
        tool = step.tool
        if tool is None:
            return StepResult(False, {"success": False, "error": "tool step without a tool name"})
        try:
            raw = await self._server.call_tool(tool, step.arguments or {})
        except Exception as exc:  # surface failure is captured, never raised
            return StepResult(False, {"success": False, "error": str(exc)})
        return StepResult(True, _unwrap_result(raw))

    def run(self, step: Step) -> StepResult:
        """Sync convenience wrapper — test/CLI paths only.

        The engine's async executor (W1-T7) always uses ``run_async``;
        ``asyncio.run()`` belongs on the CLI path only (plan assumption).
        """
        return asyncio.run(self.run_async(step))


class CLIAdapter:
    """CLI surface: one subprocess run of ``step.command``.

    The command string is parsed with :func:`shlex.split` and executed with
    ``shell=False`` (preferred); if the string cannot be split, it falls
    back to ``shell=True``.  Scenario commands come from the committed
    scenarios library — trusted configuration, same trust model as the
    cron schedule config (cli/commands/cron.py:321).
    """

    def run(self, step: Step) -> StepResult:
        """Run the command; capture exit code, stdout, and stderr."""
        command = step.command
        if command is None:
            return StepResult(False, {"success": False, "error": "cli step without a command"})
        timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        parts: str | list[str]
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command
            shell = True
        else:
            shell = False
        try:
            proc = self._run_process(parts, timeout, shell)
        except subprocess.TimeoutExpired as exc:
            return StepResult(
                False,
                {
                    "success": False,
                    "error": f"command timed out after {timeout:g}s",
                    "exit_code": None,
                    "stdout": exc.stdout if isinstance(exc.stdout, str) else "",
                    "stderr": exc.stderr if isinstance(exc.stderr, str) else "",
                },
            )
        except OSError as exc:
            return StepResult(
                False,
                {
                    "success": False,
                    "error": str(exc),
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                },
            )
        return StepResult(
            True,
            {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
            },
        )

    @staticmethod
    def _run_process(
        parts: str | list[str], timeout: float, shell: bool
    ) -> subprocess.CompletedProcess[str]:
        """The single subprocess choke point (trusted scenario commands)."""
        return subprocess.run(  # noqa: S603 — trusted committed scenario config
            parts,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,  # nosec B602 — trusted committed scenario config
            check=False,
        )


def _extract_gate_records(parsed: object) -> list[Any]:
    """Extract gate-pass records from a parsed JSON artifact (or [])."""
    if not isinstance(parsed, dict):
        return []
    for key in ("gates", "gate_records"):
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    return []


class FileAdapter:
    """File surface: one artifact file inspection (plan W1-T4).

    ``step.command`` carries the artifact path.  The output dict is the
    artifact fact sheet consumed by the artifact expects (W1-T6) and the
    report:

    * ``exists`` / ``size`` / ``nonempty`` — basic artifact facts;
    * ``is_json`` — the content looks like JSON (starts with ``{``/``[``
      after stripping);
    * ``json_parse_ok`` — that content actually parsed with
      :func:`json.loads`;
    * ``gate_records`` — the ``gates``/``gate_records`` list of a parsed
      JSON artifact (project info / pipeline_md5.json records), else [].

    A missing file is ``ok=False`` with ``exists=False``; artifacts larger
    than :data:`_JSON_PARSE_LIMIT` are never read (facts only).
    """

    def run(self, step: Step) -> StepResult:
        """Inspect the artifact named by ``step.command``; never raises."""
        command = step.command
        if command is None:
            return StepResult(False, {"success": False, "error": "file step without a path"})
        path = Path(command).expanduser()
        if not path.exists():
            return StepResult(
                False,
                {
                    "success": False,
                    "path": str(path),
                    "exists": False,
                    "size": 0,
                    "nonempty": False,
                    "is_json": False,
                    "json_parse_ok": False,
                    "gate_records": [],
                },
            )
        size = path.stat().st_size
        parsed: object = None
        if size <= _JSON_PARSE_LIMIT:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            is_json = text.lstrip().startswith(("{", "["))
            if is_json:
                try:
                    parsed = json.loads(text)
                except ValueError:
                    parsed = None
        else:
            is_json = False
        return StepResult(
            True,
            {
                "success": True,
                "path": str(path),
                "exists": True,
                "size": size,
                "nonempty": size > 0,
                "is_json": is_json,
                "json_parse_ok": parsed is not None,
                "gate_records": _extract_gate_records(parsed),
            },
        )
