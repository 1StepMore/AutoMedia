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
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from automedia.validation.media_probe import (
    glob_artifacts,
    is_image_path,
    probe_image,
    probe_media,
    probe_srt,
    probe_text,
)
from automedia.validation.schema import DEFAULT_TIMEOUT_SECONDS, Step
from automedia.validation.stub_bin import STUB_BIN_ENV

_JSON_PARSE_LIMIT: int = 4 * 1024 * 1024
"""Artifacts larger than this get existence/size facts only — no JSON read."""

_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI: colours, cursor movement, erase
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: window title, hyperlinks
    r"|\x1b[@-Z\\-_]"  # two-byte escapes (e.g. save/restore cursor)
)
"""Terminal escape sequences stripped from captured CLI streams."""

_POSIX_UTIL_NAMES: frozenset[str] = frozenset(
    {
        "awk",
        "cat",
        "cut",
        "find",
        "grep",
        "head",
        "ls",
        "sed",
        "sort",
        "tail",
        "tr",
        "uniq",
        "wc",
        "xargs",
    }
)
"""Bare POSIX utility names a committed scenario command may use.

Only these are resolved to an absolute path on Windows (see
:func:`_resolve_posix_util`); anything else is left exactly as written.
"""


def _is_under_windows_system_dir(candidate: str) -> bool:
    """True when *candidate* lives under ``%SystemRoot%`` / ``%windir%``."""
    normalised = os.path.normcase(os.path.normpath(candidate))
    for variable in ("SystemRoot", "windir"):
        root = os.environ.get(variable)
        if not root:
            continue
        prefix = os.path.normcase(os.path.normpath(root))
        if normalised == prefix or normalised.startswith(prefix + os.sep):
            return True
    return False


def _posix_util_candidates(token: str) -> list[str]:
    """Return PATH candidates named *token*, ``token.exe`` form included.

    ``shutil.which`` is asked first, then every ``PATH`` entry is scanned for
    both names.  Duplicates are dropped so the ordering below is stable.
    """
    candidates: list[str] = []
    found = shutil.which(token)
    if found:
        candidates.append(found)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        for name in (token, f"{token}.exe"):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _resolve_posix_util(token: str) -> str:
    """Resolve a bare POSIX utility name to a non-system executable.

    Windows ``CreateProcess`` searches ``%SystemRoot%\\system32`` *before*
    ``PATH``, so a bare ``find`` in a scenario command always lands on
    ``C:\\Windows\\system32\\find.exe`` — the Windows *text* search tool, which
    rejects ``-name``/``-size`` and exits 2.  That is why ``auto-journey``
    step 3 ("a ``*_draft.md`` of at least 500 bytes exists") failed on every
    Windows harness run even though the draft was produced (#625 follow-up).

    Resolving the *token* to an absolute path keeps the command portable
    without editing ``scenarios/`` (expectations are owner-only) and without
    weakening the assertion: it still asks for that glob and that size.

    Returns *token* unchanged when there is nothing better to use — an honest
    fallback that preserves the pre-existing behaviour instead of inventing a
    failure.
    """
    if sys.platform != "win32":
        return token
    if not token or "/" in token or "\\" in token:
        return token
    if token.lower() not in _POSIX_UTIL_NAMES:
        return token
    for candidate in _posix_util_candidates(token):
        if _is_under_windows_system_dir(candidate):
            continue
        return candidate
    return token


def _plain(text: str) -> str:
    """Strip ANSI styling so an expectation matches the text a human sees.

    Rich/typer colourise help output whenever the child believes it has a
    colour-capable stream, and its highlighter splits a token across style
    spans: ``\\x1b[1;36m-\\x1b[0m\\x1b[1;36m-port\\x1b[0m`` renders as
    ``--port`` but the raw string contains no ``--port``. That is why
    ``ui-cli-surface`` passed on a developer box and failed on every CI run
    (issue #366): the substring check saw the escapes, not the option name.
    Stripping here keeps every CLI expectation environment-independent.
    """
    return _ANSI_ESCAPE_RE.sub("", text)


def _tolerant_decode(raw: bytes | bytearray | str | None) -> str:
    """Decode subprocess output without dying on mixed-encoding children.

    Order: UTF-8 (the repo's canonical output encoding), then GBK/cp936
    (Windows native console tools), then UTF-8 with replacement — a decode
    failure must never lose the captured bytes outright.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


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
    """Normalise every documented call_tool return shape to one dict.

    * a ``dict`` is used verbatim;
    * a ``(blocks, structured_dict)`` tuple (the actual shape mcp 1.27.2
      produces for dict-annotated tools) yields the structured dict;
    * a ``CallToolResult`` (the dispatcher's failure shape — it carries
      ``isError`` so MCP clients see the failure) yields its
      ``structuredContent``, keeping the tool's error payload intact;
    * a ``Sequence[ContentBlock]`` is reduced to ``content[0]``'s text and
      JSON-parsed via :func:`_parse_text`.
    """
    if isinstance(raw, dict):
        return raw
    structured = getattr(raw, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        if len(raw) == 2 and isinstance(raw[1], dict):
            return raw[1]
        if raw:
            return _parse_text(_block_text(raw[0]))
        return {"success": True, "data": {"text": ""}}
    return {"success": True, "data": {"text": str(raw)}}


def _expand_env(value: object) -> object:
    """Recursively expand ``${VAR}`` in string arguments before a call."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


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
        arguments = cast(dict[str, Any], _expand_env(step.arguments or {}))
        try:
            raw = await self._server.call_tool(tool, arguments)
        except Exception as exc:  # surface failure is captured, never raised
            return StepResult(False, {"success": False, "error": str(exc)})
        return StepResult(True, _unwrap_result(raw))

    def run(self, step: Step) -> StepResult:
        """Sync convenience wrapper — test/CLI paths only.

        The engine's async executor (W1-T7) always uses ``run_async``;
        ``asyncio.run()`` belongs on the CLI path only (plan assumption).
        """
        return asyncio.run(self.run_async(step))


def _active_stub_dir(env: dict[str, str]) -> str | None:
    """Return the normalised stub-bin dir already on ``env``'s PATH, if any."""
    raw = env.get(STUB_BIN_ENV, "").strip()
    if not raw:
        return None
    stub_dir = str(Path(raw).expanduser())
    parts = [part for part in env.get("PATH", "").split(os.pathsep) if part]
    return stub_dir if stub_dir in parts else None


def _scenario_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Build the scenario child env with the running interpreter's bin dir.

    Scenario YAMLs call bare ``python``; launching the suite as
    ``.venv/bin/python -m automedia validate run`` (without ``.venv/bin`` on
    PATH) therefore resolved the system interpreter and lost ``mcp`` (#676).
    Prepending ``dirname(sys.executable)`` — ``Scripts`` on Windows — keeps
    the ambient PATH intact for ``ffmpeg``/``pandoc``/``pdftotext``.

    An active stub-bin dir (gap T-21) stays ahead of the interpreter dir so a
    stubbed ``ffmpeg``/``python`` is never shadowed by the real one.
    """
    env = dict(os.environ if environ is None else environ)
    bin_dir = os.path.dirname(sys.executable)
    if not bin_dir:
        return env
    stub_dir = _active_stub_dir(env)
    parts = [part for part in env.get("PATH", "").split(os.pathsep) if part and part != bin_dir]
    index = 1 if stub_dir is not None and parts and parts[0] == stub_dir else 0
    parts.insert(index, bin_dir)
    env["PATH"] = os.pathsep.join(parts)
    return env


class CLIAdapter:
    """CLI surface: one subprocess run of ``step.command``.

    The command string is parsed with :func:`shlex.split` and executed with
    ``shell=False`` (preferred); if the string cannot be split, it falls
    back to ``shell=True``.  Scenario commands come from the committed
    scenarios library — trusted configuration, same trust model as the
    cron schedule config (cli/commands/cron.py:321).
    """

    def run(self, step: Step) -> StepResult:
        """Run the command; capture exit code, stdout, and stderr.

        ``step.command`` is expanded with :func:`os.path.expandvars` (so a
        sandboxed scenario can reference ``${AUTOMEDIA_PROJECTS_DIR}``) and the
        child inherits the engine's environment, which carries the sandbox
        directories (#333/#334).  A leading bare ``automedia`` token resolves
        to ``sys.executable -m automedia`` so steps do not depend on the
        console script being on the child's PATH (#564).
        """
        command = step.command
        if command is None:
            return StepResult(False, {"success": False, "error": "cli step without a command"})
        timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        expanded = os.path.expandvars(command)
        # POSIX shlex rules eat backslashes, which corrupts every expanded
        # Windows path (C:\Users\... -> C:UsersRenAnZai...): keep them intact
        # by splitting without posix escaping on Windows, then dequote simple
        # surrounding quotes that posix=False leaves in place (#night-20261117).
        posix_split = sys.platform != "win32"
        parts: str | list[str]
        try:
            parts = shlex.split(expanded, posix=posix_split)
        except ValueError:
            parts = command
            shell = True
        else:
            shell = False
            if not posix_split and isinstance(parts, list):
                parts = [
                    p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in ('"', "'") else p
                    for p in parts
                ]
        if isinstance(parts, list) and parts and parts[0] == "automedia":
            # Bare ``automedia`` is a console-script entry point whose location
            # is install-layout dependent: the engine's ``Scripts/``/``bin``
            # directory is not necessarily on a child process' PATH (#564 —
            # exit 127 under a scenario shell).  Resolve it through the running
            # interpreter so every CLI step executes the same ``automedia``
            # package the engine itself runs, on every platform.
            parts = [sys.executable, "-m", "automedia", *parts[1:]]
        if isinstance(parts, list) and parts:
            # Windows resolves a bare executable name through system32 before
            # PATH, so ``find``/``grep``/... would hit the Windows text tools
            # instead of the POSIX ones a scenario means (#625 follow-up).
            # An absolute non-system path is used when one exists; otherwise
            # the token is left untouched.
            parts = [_resolve_posix_util(parts[0]), *parts[1:]]
        try:
            proc = self._run_process(parts, timeout, shell)
        except subprocess.TimeoutExpired as exc:
            # Coerce via a local first: mypy 1.13 (pre-commit pin) does not
            # propagate the isinstance narrowing into a call argument written
            # as a ternary, so ``_plain(x) if isinstance(x, str) else ""``
            # trips its ``bytes | None`` stub for TimeoutExpired.stdout.
            stdout_text = _tolerant_decode(exc.stdout)
            stderr_text = _tolerant_decode(exc.stderr)
            return StepResult(
                False,
                {
                    "success": False,
                    "error": f"command timed out after {timeout:g}s",
                    "exit_code": None,
                    "stdout": _plain(stdout_text),
                    "stderr": _plain(stderr_text),
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
                "stdout": _plain(proc.stdout or ""),
                "stderr": _plain(proc.stderr or ""),
            },
        )

    @staticmethod
    def _run_process(
        parts: str | list[str], timeout: float, shell: bool
    ) -> subprocess.CompletedProcess[str]:
        """The single subprocess choke point (trusted scenario commands).

        Captures bytes and decodes tolerantly (utf-8, then GBK, then
        replacement) instead of ``text=True``: a native Windows child whose
        console output is GBK (cp936) crashed the ``subprocess`` reader
        thread under strict UTF-8 decoding, silently losing the step's
        stdout/stderr (#night-20261117).
        """
        proc = subprocess.run(  # noqa: S603 — trusted committed scenario config
            parts,
            capture_output=True,
            timeout=timeout,
            shell=shell,  # nosec B602 — trusted committed scenario config
            check=False,
            env=_scenario_env(),
        )
        return subprocess.CompletedProcess(
            proc.args,
            proc.returncode,
            stdout=_tolerant_decode(proc.stdout),
            stderr=_tolerant_decode(proc.stderr),
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
    """File surface: one artifact inspection (plan W1-T4).

    ``step.command`` carries the artifact path or the root directory of an
    ``artifact_glob`` set.  The output dict is the artifact fact sheet
    consumed by the artifact expects (W1-T6) and the report:

    * ``exists`` / ``size`` / ``nonempty`` — basic artifact facts;
    * ``is_json`` — the content looks like JSON (starts with ``{``/``[``
      after stripping);
    * ``json_parse_ok`` — that content actually parsed with
      :func:`json.loads`;
    * ``gate_records`` — the ``gates``/``gate_records`` list of a parsed
      JSON artifact (project info / pipeline_md5.json records), else [];
    * ``artifact_glob`` — absolute matching paths for a glob locator;
    * ``media`` / ``text`` / ``subtitle`` — probe facts when the step
      declares the corresponding expect block;
    * ``base_dir`` — absolute directory for resolving relative assertions.

    A missing file is ``ok=False`` with ``exists=False``; artifacts larger
    than :data:`_JSON_PARSE_LIMIT` are never read (facts only).
    """

    def run(self, step: Step) -> StepResult:
        """Inspect the artifact named by ``step.command``; never raises."""
        command = step.command
        if command is None:
            return StepResult(False, {"success": False, "error": "file step without a path"})
        path = Path(os.path.expandvars(command)).expanduser()
        pattern = step.expect.artifact_glob
        base_dir = path if path.is_dir() else path.parent
        if pattern is not None:
            matches = glob_artifacts(str(path), pattern) if path.exists() else []
            facts: dict[str, Any] = {
                "success": path.exists(),
                "path": str(path),
                "exists": bool(matches),
                "size": 0,
                "nonempty": bool(matches),
                "is_json": False,
                "json_parse_ok": False,
                "gate_records": [],
                "artifact_glob": matches,
                "base_dir": str(base_dir.resolve()),
            }
            if not path.exists():
                facts["error"] = f"artifact root not found: {path}"
            targets = [Path(match) for match in matches]
            self._add_probe_facts(step, facts, targets, path)
            return StepResult(path.exists(), facts)
        if not path.exists():
            facts = {
                "success": False,
                "path": str(path),
                "exists": False,
                "size": 0,
                "nonempty": False,
                "is_json": False,
                "json_parse_ok": False,
                "gate_records": [],
                "base_dir": str(base_dir.resolve()),
            }
            self._add_probe_facts(step, facts, [path], path)
            return StepResult(False, facts)
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
        facts = {
            "success": True,
            "path": str(path),
            "exists": True,
            "size": size,
            "nonempty": size > 0,
            "is_json": is_json,
            "json_parse_ok": parsed is not None,
            "gate_records": _extract_gate_records(parsed),
            "base_dir": str(base_dir.resolve()),
        }
        self._add_probe_facts(step, facts, [path], path)
        return StepResult(True, facts)

    @staticmethod
    def _add_probe_facts(
        step: Step,
        facts: dict[str, Any],
        targets: list[Path],
        path: Path,
    ) -> None:
        """Attach media/text/subtitle probe facts declared by the step."""
        expect = step.expect
        if expect.media is not None:
            probes: list[dict[str, Any]] = []
            for target in targets:
                if step.check in {"media.image", "media.carousel"}:
                    probes.append(probe_image(target))
                elif step.check in {"media.video", "media.audio"}:
                    probes.append(probe_media(target))
                elif is_image_path(target):
                    probes.append(probe_image(target))
                else:
                    probes.append(probe_media(target))
            facts["media"] = probes
        if expect.text is not None:
            target = path if path.is_file() else targets[0] if targets else path
            facts["text"] = probe_text(target)
        if expect.subtitle is not None:
            target = path if path.is_file() else targets[0] if targets else path
            facts["subtitle"] = probe_srt(target)
