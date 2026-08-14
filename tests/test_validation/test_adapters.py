"""Unit tests for the validation surface adapters (W1-T4).

Covers the three strategy adapters from guide §3.2:

* ``ToolAdapter`` — the async core (``run_async``) against a FAKE server
  object (never the real MCP server, no live calls): dict return,
  ``content[0].text`` JSON return, the verified ``(blocks, dict)`` tuple
  shape, malformed JSON text, call_tool exceptions, empty-arguments
  default, and the sync ``asyncio.run`` wrapper.
* ``CLIAdapter`` — real ``python3 -c`` commands: exit 0 / exit 1,
  per-step timeout, missing command, un-splittable command (shell
  fallback), missing binary (OSError), default timeout applied.
* ``FileAdapter`` — real tmp files: exists/size/nonempty/JSON/gate-records
  facts, missing file, empty file, oversized file, non-dict JSON.

All fixtures are synthetic; nothing here is e2e-marked.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from automedia.validation.adapters import CLIAdapter, FileAdapter, StepResult, ToolAdapter
from automedia.validation.schema import DEFAULT_TIMEOUT_SECONDS, Expect, Step


def tool_step(**overrides: object) -> Step:
    """A valid tool-kind step, overridable per test."""
    data: dict[str, Any] = {
        "name": "call health_check",
        "kind": "tool",
        "check": "server responds",
        "standard": "founder-expectations.F01",
        "tool": "health_check",
        "arguments": {},
        "expect": {"success": True},
    }
    data.update(overrides)
    return Step.from_dict(data)


def cli_step(command: str, timeout: float | None = None) -> Step:
    """A valid cli-kind step with the given command and optional timeout."""
    data: dict[str, Any] = {
        "name": "run command",
        "kind": "cli",
        "check": "command runs",
        "standard": "founder-expectations.F01",
        "command": command,
        "expect": {"success": True},
    }
    if timeout is not None:
        data["timeout_seconds"] = timeout
    return Step.from_dict(data)


def file_step(path: str) -> Step:
    """A valid file-kind step inspecting the given artifact path."""
    return Step.from_dict(
        {
            "name": "inspect artifact",
            "kind": "file",
            "check": "artifact exists",
            "standard": "founder-expectations.F01",
            "command": path,
            "expect": {"success": True},
        }
    )


def bare_step(kind: str, **kwargs: object) -> Step:
    """A schema-invalid step (missing call spec) built directly, for guards."""
    base: dict[str, Any] = {
        "name": "probe",
        "kind": kind,
        "check": "probe",
        "standard": "founder-expectations.F01",
        "expect": Expect(),
    }
    base.update(kwargs)
    return Step(**base)  # type: ignore[arg-type]


class FakeServer:
    """Duck-typed stand-in for the FastMCP instance (synthetic, no live calls)."""

    def __init__(self, result: object, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        self.calls.append((name, arguments))
        if self._error is not None:
            raise self._error
        return self._result


class FakeBlock:
    """Minimal stand-in for an mcp ``TextContent`` content block."""

    def __init__(self, text: str) -> None:
        self.text = text


class FakeContentBlock:
    """Stand-in block with a ``.content`` attribute but no ``.text``."""

    def __init__(self, content: str) -> None:
        self.content = content


class TestToolAdapterAsync:
    """The async core (``run_async``) — the engine's real path (W1-T7)."""

    def test_dict_return_used_verbatim(self) -> None:
        server = FakeServer({"success": True, "data": {"status": "ok"}})
        result = asyncio.run(ToolAdapter(server).run_async(tool_step(arguments={"key": "value"})))
        assert isinstance(result, StepResult)
        assert result.ok is True
        assert result.output == {"success": True, "data": {"status": "ok"}}
        assert server.calls == [("health_check", {"key": "value"})]

    def test_content_text_json_return_is_unwrapped(self) -> None:
        server = FakeServer([FakeBlock('{"success": true, "data": {"status": "ok"}}')])
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True, "data": {"status": "ok"}}

    def test_structured_tuple_shape_prefers_the_dict(self) -> None:
        # Verified production shape (mcp 1.27.2): dict-annotated tools return
        # (unstructured blocks, structured dict); the dict is authoritative.
        server = FakeServer(
            ([FakeBlock('{"success": true}')], {"success": True, "data": {"status": "ok"}})
        )
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True, "data": {"status": "ok"}}

    def test_malformed_json_text_is_wrapped_never_crashes(self) -> None:
        server = FakeServer([FakeBlock("this is not json")])
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True, "data": {"text": "this is not json"}}

    def test_block_text_falls_back_to_content_attribute(self) -> None:
        server = FakeServer([FakeContentBlock('{"success": true}')])
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True}

    def test_empty_content_sequence(self) -> None:
        server = FakeServer([])
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True, "data": {"text": ""}}

    def test_bare_string_return_is_wrapped(self) -> None:
        server = FakeServer("plain output")
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True, "data": {"text": "plain output"}}

    def test_non_dict_json_text_is_wrapped_under_data(self) -> None:
        server = FakeServer([FakeBlock("[1, 2, 3]")])
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True, "data": [1, 2, 3]}

    def test_block_without_text_or_content_falls_back_to_str(self) -> None:
        server = FakeServer([object()])
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert "data" in result.output
        assert isinstance(result.output["data"]["text"], str)

    def test_bare_content_block_return_is_wrapped(self) -> None:
        block = FakeBlock("raw block")
        server = FakeServer(block)
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is True
        assert result.output == {"success": True, "data": {"text": str(block)}}

    def test_call_tool_exception_is_captured(self) -> None:
        server = FakeServer(None, error=RuntimeError("kaboom"))
        result = asyncio.run(ToolAdapter(server).run_async(tool_step()))
        assert result.ok is False
        assert result.output == {"success": False, "error": "kaboom"}

    def test_empty_arguments_default(self) -> None:
        server = FakeServer([FakeBlock('{"success": true}')])
        result = asyncio.run(ToolAdapter(server).run_async(tool_step(arguments={})))
        assert result.ok is True
        assert server.calls == [("health_check", {})]

    def test_tool_step_without_tool_name(self) -> None:
        result = asyncio.run(ToolAdapter(FakeServer({})).run_async(bare_step("tool", tool=None)))
        assert result.ok is False
        assert result.output["success"] is False


class TestToolAdapterSync:
    """``run`` — the asyncio.run convenience wrapper (test/CLI path only)."""

    def test_run_wraps_run_async_via_asyncio_run(self) -> None:
        server = FakeServer([FakeBlock('{"success": true, "data": {"status": "ok"}}')])
        result = ToolAdapter(server).run(tool_step())
        assert isinstance(result, StepResult)
        assert result.ok is True
        assert result.output == {"success": True, "data": {"status": "ok"}}

    def test_run_propagates_call_failure(self) -> None:
        server = FakeServer(None, error=ValueError("bad tool"))
        result = ToolAdapter(server).run(tool_step())
        assert result.ok is False
        assert result.output == {"success": False, "error": "bad tool"}


class TestCLIAdapter:
    def test_exit_zero_with_stdout(self) -> None:
        result = CLIAdapter().run(cli_step("python3 -c 'print(\"hello validation\")'"))
        assert result.ok is True
        assert result.output["success"] is True
        assert result.output["exit_code"] == 0
        assert "hello validation" in result.output["stdout"]

    def test_exit_one_is_completed_not_failed(self) -> None:
        result = CLIAdapter().run(cli_step("python3 -c 'import sys; sys.exit(1)'"))
        assert result.ok is True  # the call reached and completed the surface
        assert result.output["success"] is False
        assert result.output["exit_code"] == 1

    def test_stderr_is_captured(self) -> None:
        result = CLIAdapter().run(
            cli_step("python3 -c 'import sys; sys.stderr.write(\"oops\"); sys.exit(2)'")
        )
        assert result.ok is True
        assert result.output["exit_code"] == 2
        assert "oops" in result.output["stderr"]

    def test_timeout_is_enforced_and_captured(self) -> None:
        result = CLIAdapter().run(
            cli_step("python3 -c 'import time; time.sleep(5)'", timeout=0.5)
        )
        assert result.ok is False
        assert result.output["success"] is False
        assert result.output["exit_code"] is None
        assert "timed out" in result.output["error"]
        assert result.output["stdout"] == ""
        assert result.output["stderr"] == ""

    def test_missing_command(self) -> None:
        result = CLIAdapter().run(bare_step("cli", command=None))
        assert result.ok is False
        assert result.output["success"] is False
        assert "command" in result.output["error"]

    def test_unparseable_command_falls_back_to_shell(self) -> None:
        # shlex.split raises on the unterminated quote -> shell=True fallback.
        result = CLIAdapter().run(cli_step("echo 'unterminated"))
        assert result.ok is True  # the shell ran (and reported a syntax error)
        assert result.output["exit_code"] != 0
        assert result.output["stderr"]

    def test_missing_binary_is_oserror_result(self) -> None:
        result = CLIAdapter().run(cli_step("definitely-not-a-real-binary-xyz"))
        assert result.ok is False
        assert result.output["success"] is False
        assert result.output["exit_code"] is None
        assert result.output["error"]

    def test_default_timeout_is_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_run(args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.update(kwargs)
            return subprocess.CompletedProcess(args, 0, "", "")  # type: ignore[arg-type]

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = CLIAdapter().run(cli_step("echo hi"))
        assert result.ok is True
        assert captured["timeout"] == DEFAULT_TIMEOUT_SECONDS


class TestFileAdapter:
    def test_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.json"
        result = FileAdapter().run(file_step(str(missing)))
        assert result.ok is False
        assert result.output["success"] is False
        assert result.output["exists"] is False
        assert result.output["size"] == 0
        assert result.output["nonempty"] is False
        assert result.output["is_json"] is False
        assert result.output["json_parse_ok"] is False
        assert result.output["gate_records"] == []

    def test_existing_plain_text_facts(self, tmp_path: Path) -> None:
        artifact = tmp_path / "draft.md"
        artifact.write_text("hello world", encoding="utf-8")
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.ok is True
        assert result.output["success"] is True
        assert result.output["exists"] is True
        assert result.output["size"] == 11
        assert result.output["nonempty"] is True
        assert result.output["is_json"] is False
        assert result.output["json_parse_ok"] is False
        assert result.output["gate_records"] == []

    def test_json_file_with_gates_records(self, tmp_path: Path) -> None:
        artifact = tmp_path / "info.json"
        gates = [{"gate": "G0", "status": "passed"}, {"gate": "G1", "status": "passed"}]
        artifact.write_text(json.dumps({"topic": "t", "gates": gates}), encoding="utf-8")
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.ok is True
        assert result.output["is_json"] is True
        assert result.output["json_parse_ok"] is True
        assert result.output["gate_records"] == gates

    def test_json_file_with_gate_records_key(self, tmp_path: Path) -> None:
        artifact = tmp_path / "info.json"
        records = [{"gate": "G0", "passed": True}]
        artifact.write_text(json.dumps({"gate_records": records}), encoding="utf-8")
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.output["gate_records"] == records

    def test_json_file_without_gate_keys(self, tmp_path: Path) -> None:
        artifact = tmp_path / "plain.json"
        artifact.write_text('{"a": 1}', encoding="utf-8")
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.output["is_json"] is True
        assert result.output["json_parse_ok"] is True
        assert result.output["gate_records"] == []

    def test_malformed_json_file(self, tmp_path: Path) -> None:
        artifact = tmp_path / "broken.json"
        artifact.write_text('{"a": ', encoding="utf-8")
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.ok is True
        assert result.output["is_json"] is True
        assert result.output["json_parse_ok"] is False
        assert result.output["gate_records"] == []

    def test_empty_file(self, tmp_path: Path) -> None:
        artifact = tmp_path / "empty.json"
        artifact.write_text("", encoding="utf-8")
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.output["size"] == 0
        assert result.output["nonempty"] is False
        assert result.output["is_json"] is False
        assert result.output["json_parse_ok"] is False

    def test_non_dict_json_has_no_gate_records(self, tmp_path: Path) -> None:
        artifact = tmp_path / "list.json"
        artifact.write_text("[1, 2, 3]", encoding="utf-8")
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.output["is_json"] is True
        assert result.output["json_parse_ok"] is True
        assert result.output["gate_records"] == []

    def test_oversized_file_is_not_json_parsed(self, tmp_path: Path) -> None:
        artifact = tmp_path / "big.bin"
        artifact.write_bytes(b"a" * (4 * 1024 * 1024 + 1))
        result = FileAdapter().run(file_step(str(artifact)))
        assert result.ok is True
        assert result.output["exists"] is True
        assert result.output["size"] == 4 * 1024 * 1024 + 1
        assert result.output["nonempty"] is True
        assert result.output["is_json"] is False
        assert result.output["json_parse_ok"] is False
        assert result.output["gate_records"] == []

    def test_directory_artifact_is_not_json(self, tmp_path: Path) -> None:
        result = FileAdapter().run(file_step(str(tmp_path)))
        assert result.ok is True
        assert result.output["exists"] is True
        assert result.output["is_json"] is False
        assert result.output["json_parse_ok"] is False
        assert result.output["gate_records"] == []

    def test_missing_path(self) -> None:
        result = FileAdapter().run(bare_step("file", command=None))
        assert result.ok is False
        assert result.output["success"] is False
        assert "path" in result.output["error"]
