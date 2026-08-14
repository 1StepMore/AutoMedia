"""Doc↔reality audit (plan W3-T8, C4): AGENTS.md/README claims vs code truth.

Parses the MCP tool / CLI command tables in ``AGENTS.md`` and ``README.md``
plus the gate-count and adapter-count claims, and compares them against the
code: MCP registrations in ``src/automedia/mcp/server.py``, CLI registrations
in ``src/automedia/cli/app.py``, concrete ``BaseGate`` subclasses under
``src/automedia/gates/``, and ``is_stub`` flags under
``src/automedia/adapters/platforms/``.  Every divergence is emitted as a
first-class finding with severity + recommendation (findings only — W5-T2
owns the fixes via the doc-sync skill).

Verified reality (re-derived from source, not trusted blindly):

* MCP tools: 59 registrations of the form ``mcp.tool(...)(fn)`` in
  ``create_server()``.  FastMCP keys tools by ``fn.__name__`` (mcp
  fastmcp/tools/base.py: ``func_name = name or fn.__name__``), so import
  aliases are resolved to the function's real name: server.py imports the
  effects handler as ``effects_analyze_content`` but registers it as
  ``analyze_content`` — the docs table names match that reality.
* CLI commands: 17 (9 lazy sub-apps + 8 lazy fns in ``cli/app.py``).
* Gates: 33 concrete ``class X(BaseGate)`` subclasses (22 in ``gates/``,
  7 in ``gates/distribution/``, 4 in ``gates/sub_pipelines/``).
* Adapters: 20 modules under ``adapters/platforms/``, 12 with
  ``is_stub = False`` and 8 with ``is_stub = True``.

Known drift this audit MUST flag: README "29 quality gates" (Features) and
"21 gate implementations" (Core Subpackages) vs code 33; README "13 real API
+ 7 documented manual-only stubs" vs 12 real + 8 stubs; declared tools
missing from the doc tables (add_brand, configure_llm, get_redlines,
init_config, list_active_pipelines, list_platforms, onboard).

Output is deterministic: every list is sorted; findings are ordered by
severity then doc then claim.  The ``scenarios_dir`` argument is accepted
for signature symmetry with the coverage audit (W3-T7) but unused.

If ``automedia.validation.coverage`` (W3-T7) later lands with a
``declared_mcp_tools(root) -> list[str]`` extraction, it is preferred via
lazy import; until then the local regex (with alias resolution) is the
implementation.

SIZE_OK: this module deliberately exceeds the 250-line guideline — plan
W3-T8 pins the whole doc↔reality audit in one module (``doc_reality.py`` +
its test file) and must not touch the coverage module (parallel W3-T7);
same precedent as engine.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DOC_FILENAMES: tuple[str, str] = ("AGENTS.md", "README.md")
_SERVER_FILENAME = "server.py"
_CLI_FILENAME = "app.py"
_GATES_DIR = "gates"
_ADAPTERS_DIR = "adapters/platforms"
_PACKAGE_DIR = "automedia"
_SRC_DIR = "src"

_MCP_TOOL_RE = re.compile(r"mcp\.tool\([\s\S]*?\)\(\w+\)")
_IMPORT_LINE_RE = re.compile(r"^\s*(?:from\s+[\w.]+\s+import|import)\s+.+$", re.MULTILINE)
_AS_CLAUSE_RE = re.compile(r"\b(\w+)\s+as\s+(\w+)")
_REGISTER_RE = re.compile(r'register_(?:sub_app|fn)\(\s*"(\w+)"')
_ROW_RE = re.compile(r"^\s*\|")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_IDENT_RE = re.compile(r"[a-z][a-zA-Z0-9_]*")

_GATE_CLAIM_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\d+)\s+quality gates?"),
    re.compile(r"Total:\s*(\d+)\s+gates?"),
    re.compile(r"(\d+)\s+gate implementations?"),
    re.compile(r"(\d+)\s+implementations[^.\n]*?(?:H0|D1|P1|G0)"),
)
_ADAPTER_TOTAL_RE = re.compile(r"(\d+)\s+registered adapters?")
_ADAPTER_REAL_RE = re.compile(r"(\d+)\s+real\b")
_ADAPTER_STUBS_RE = re.compile(r"(\d+)(?:\s+[\w-]+)+\s+stubs?\b")
_CLASS_EXTENDS_BASEGATE_RE = re.compile(r"^class\s+\w+\(BaseGate\)", re.MULTILINE)
_STUB_FLAG_RE = re.compile(r"is_stub\s*=\s*(True|False)")

_SEVERITY_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


def doc_reality_audit(
    *,
    docs_root: str | Path | None = None,
    src_root: str | Path | None = None,
    scenarios_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Audit doc tables/count claims against code truth (deterministic).

    Args:
        docs_root: Directory containing ``AGENTS.md`` + ``README.md``
            (default: repo root — wheel-install-safe via ``parents[3]``).
        src_root: Directory containing the ``automedia/`` package — the
            repo's ``src/`` dir, a site-packages dir, or the repo root
            itself (all resolved via ``automedia/`` lookup).
        scenarios_dir: Accepted for API symmetry with the coverage audit
            (W3-T7); unused by this audit.

    Returns:
        The audit report dict:
        ``checked_files``, ``mcp_tools`` (declared/documented/undocumented/
        phantom_docs), ``cli_commands`` (same shape), ``gate_counts``
        (docs_claims/code/drift), ``adapter_counts``
        (docs_claims/code{real,stubs}/drift), and ``findings`` (each with
        severity/doc/claim/reality/recommendation).
    """
    docs_root = _resolve_root(docs_root)
    src_root = _resolve_root(src_root)
    package_root = _package_root(src_root)

    checked_files: list[str] = []
    doc_texts: dict[str, str] = {}
    for name in _DOC_FILENAMES:
        path = docs_root / name
        if path.is_file():
            doc_texts[name] = path.read_text(encoding="utf-8")
            checked_files.append(str(path))

    documented_tools: set[str] = set()
    documented_cmds: set[str] = set()
    for text in doc_texts.values():
        tools, cmds = _documented_names(text)
        documented_tools |= tools
        documented_cmds |= cmds

    declared_tools = _declared_mcp_tools(package_root)
    declared_cmds = _declared_cli_commands(package_root)
    for extra in (
        package_root / "mcp" / _SERVER_FILENAME,
        package_root / "cli" / _CLI_FILENAME,
    ):
        if extra.is_file():
            checked_files.append(str(extra))

    gate_count, gate_files = _code_gate_count(package_root)
    adapter_real, adapter_stubs, adapter_files = _code_adapter_counts(package_root)
    checked_files += [str(p) for p in gate_files + adapter_files]

    gate_claims: list[dict[str, Any]] = [
        {"doc": doc, "claim": claim, "count": count}
        for doc, text in doc_texts.items()
        for claim, count in _gate_claims(text)
    ]
    adapter_claims: list[dict[str, Any]] = [
        {"doc": doc, "claim": claim, "count": count}
        for doc, text in doc_texts.items()
        for claim, count in _adapter_claims(text)
    ]

    mcp_section = {
        "declared": sorted(declared_tools),
        "documented": sorted(documented_tools),
        "undocumented": sorted(declared_tools - documented_tools),
        "phantom_docs": sorted(documented_tools - declared_tools),
    }
    cli_section = {
        "declared": sorted(declared_cmds),
        "documented": sorted(documented_cmds),
        "undocumented": sorted(declared_cmds - documented_cmds),
        "phantom_docs": sorted(documented_cmds - declared_cmds),
    }

    findings: list[dict[str, str]] = []
    findings += _gate_findings(gate_claims, gate_count)
    findings += _adapter_findings(adapter_claims, adapter_real, adapter_stubs)
    findings += _missing_findings(
        mcp_section["undocumented"],
        "MCP tool",
        "declared in code but absent from the MCP tool tables",
        "Add <name> to the MCP tool tables",
    )
    findings += _missing_findings(
        mcp_section["phantom_docs"],
        "documented MCP tool",
        "not a registered MCP tool (call_tool would return Unknown tool)",
        "Remove <name> from the tables or register the tool",
    )
    findings += _missing_findings(
        cli_section["undocumented"],
        "CLI command",
        "registered in code but absent from the CLI command tables",
        "Add <name> to the CLI command tables",
    )
    findings += _missing_findings(
        cli_section["phantom_docs"],
        "documented CLI command",
        "not a registered CLI command (typer would raise No such command)",
        "Remove <name> from the tables or register the command",
    )
    if "effects_analyze_content" in _resolved_alias_names(package_root):
        findings.append(_analyze_content_note())
    findings.sort(key=lambda f: (_SEVERITY_RANK[f["severity"]], f["doc"], f["claim"]))

    return {
        "checked_files": sorted(checked_files),
        "mcp_tools": mcp_section,
        "cli_commands": cli_section,
        "gate_counts": {
            "docs_claims": sorted(gate_claims, key=lambda c: (c["doc"], c["claim"])),
            "code": gate_count,
            "drift": any(c["count"] != gate_count for c in gate_claims),
        },
        "adapter_counts": {
            "docs_claims": sorted(adapter_claims, key=lambda c: (c["doc"], c["claim"])),
            "code": {"real": adapter_real, "stubs": adapter_stubs},
            "drift": any(
                (
                    c["claim"].endswith("registered adapters")
                    and c["count"] != adapter_real + adapter_stubs
                )
                or ("real" in c["claim"] and c["count"] != adapter_real)
                or ("stub" in c["claim"] and c["count"] != adapter_stubs)
                for c in adapter_claims
            ),
        },
        "findings": findings,
    }


def _resolve_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root).resolve()
    return Path(__file__).resolve().parents[3]


def _package_root(src_root: Path) -> Path:
    """The ``automedia`` package directory: directly under ``src_root`` (a
    site-packages dir), under ``src_root/src`` (repo layout), or
    ``src_root`` itself when it already IS the package dir."""
    candidates = (src_root / _PACKAGE_DIR, src_root / _SRC_DIR / _PACKAGE_DIR)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return src_root


def _documented_names(text: str) -> tuple[set[str], set[str]]:
    """Tool + command names from Markdown table rows.

    For each table row, the first cell is inspected: a cell holding exactly
    one backticked lowercase identifier is a tool/command row (that
    identifier); a cell holding several words (``automedia run``) is a CLI
    row whose command is the last word.  Deprecated-alias rows parse the
    same way as normal rows.
    """
    tools: set[str] = set()
    cmds: set[str] = set()
    for line in text.splitlines():
        if not _ROW_RE.match(line):
            continue
        cells = line.strip().strip("|").split("|")
        first_cell = cells[0].strip() if cells else ""
        backticked = _BACKTICK_RE.findall(first_cell)
        if not backticked:
            continue
        words = backticked[0].split()
        idents = [w for w in words if _IDENT_RE.fullmatch(w)]
        if not idents:
            continue
        if len(words) == 1:
            tools.add(idents[0])
        else:
            cmds.add(idents[-1])
    return tools, cmds


def _declared_mcp_tools(src_root: Path) -> set[str]:
    """Registered MCP tool names, preferring the W3-T7 coverage extraction
    when it exists, else the local regex + alias resolution."""
    try:
        from automedia.validation import coverage as _coverage  # type: ignore[no-redef]

        extract = getattr(_coverage, "declared_mcp_tools", None)
        if callable(extract):
            return set(extract(src_root))
    except Exception:  # noqa: S110, BLE001 — parallel seam; fall back to the local regex
        pass
    return _regex_declared_mcp_tools(src_root / "mcp" / _SERVER_FILENAME)


def _regex_declared_mcp_tools(server_path: Path) -> set[str]:
    """Registered names via ``mcp.tool(...)(sym)`` regex + import-alias
    resolution (FastMCP keys tools by ``fn.__name__``, not the bound name)."""
    if not server_path.is_file():
        return set()
    source = server_path.read_text(encoding="utf-8")
    aliases = _import_aliases(source)
    symbols = [m.split(")(")[1][:-1] for m in _MCP_TOOL_RE.findall(source)]
    return {aliases.get(sym, sym) for sym in symbols}


def _import_aliases(source: str) -> dict[str, str]:
    """Map alias → original name for ``... import name as alias`` clauses."""
    aliases: dict[str, str] = {}
    for line in _IMPORT_LINE_RE.findall(source):
        for original, alias in _AS_CLAUSE_RE.findall(line):
            aliases[alias] = original
    return aliases


def _resolved_alias_names(package_root: Path) -> set[str]:
    """Names bound via an import alias in server.py (code-side cosmetics)."""
    path = package_root / "mcp" / _SERVER_FILENAME
    if not path.is_file():
        return set()
    return set(_import_aliases(path.read_text(encoding="utf-8")))


def _declared_cli_commands(src_root: Path) -> set[str]:
    """CLI command names from the lazy registrations in ``cli/app.py``."""
    path = src_root / "cli" / _CLI_FILENAME
    if not path.is_file():
        return set()
    return set(_REGISTER_RE.findall(path.read_text(encoding="utf-8")))


def _gate_claims(text: str) -> list[tuple[str, int]]:
    """Count claims about gates, in document order (deterministic)."""
    claims: list[tuple[str, int]] = []
    for pattern in _GATE_CLAIM_RES:
        for match in pattern.finditer(text):
            claim = " ".join(match.group(0).split())
            claims.append((claim, int(match.group(1))))
    return claims


def _adapter_claims(text: str) -> list[tuple[str, int]]:
    """Adapter count claims (total/real/stubs) from adapter-bearing lines."""
    claims: list[tuple[str, int]] = []
    for pattern, accept in (
        (_ADAPTER_TOTAL_RE, lambda line: True),
        (_ADAPTER_REAL_RE, lambda line: "adapter" in line.lower()),
        (_ADAPTER_STUBS_RE, lambda line: "adapter" in line.lower()),
    ):
        for match in pattern.finditer(text):
            line_start = text[: match.start()].rsplit("\n", 1)[-1]
            line = line_start + text[match.start() :].split("\n", 1)[0]
            if not accept(line):
                continue
            claim = " ".join(match.group(0).split())
            claims.append((claim, int(match.group(1))))
    return claims


def _code_gate_count(src_root: Path) -> tuple[int, list[Path]]:
    """Concrete ``class X(BaseGate)`` subclasses under ``gates/**``."""
    files = sorted((src_root / _GATES_DIR).rglob("*.py"))
    count = 0
    for path in files:
        count += len(_CLASS_EXTENDS_BASEGATE_RE.findall(path.read_text(encoding="utf-8")))
    return count, files


def _code_adapter_counts(src_root: Path) -> tuple[int, int, list[Path]]:
    """(real, stubs) from ``is_stub = ...`` flags in ``adapters/platforms``."""
    real = stubs = 0
    files = sorted((src_root / _ADAPTERS_DIR).glob("*.py"))
    for path in files:
        match = _STUB_FLAG_RE.search(path.read_text(encoding="utf-8"))
        if match is None:
            continue
        if match.group(1) == "True":
            stubs += 1
        else:
            real += 1
    return real, stubs, files


def _gate_findings(claims: list[dict[str, Any]], code: int) -> list[dict[str, str]]:
    findings = []
    for claim in claims:
        if claim["count"] == code:
            continue
        findings.append(
            {
                "severity": "high",
                "doc": claim["doc"],
                "claim": claim["claim"],
                "reality": f"{code} concrete BaseGate subclasses in automedia/gates/**",
                "recommendation": f"Update {claim['doc']} to state {code} gates",
            }
        )
    return findings


def _adapter_findings(claims: list[dict[str, Any]], real: int, stubs: int) -> list[dict[str, str]]:
    findings = []
    for claim in claims:
        if claim["claim"].endswith("registered adapters"):
            mismatch = claim["count"] != real + stubs
        elif "real" in claim["claim"]:
            mismatch = claim["count"] != real
        elif "stub" in claim["claim"]:
            mismatch = claim["count"] != stubs
        else:
            mismatch = False
        if not mismatch:
            continue
        findings.append(
            {
                "severity": "medium",
                "doc": claim["doc"],
                "claim": claim["claim"],
                "reality": f"{real} real (is_stub=False) + {stubs} stubs (is_stub=True)",
                "recommendation": f"Update {claim['doc']} to {real} real + {stubs} stubs",
            }
        )
    return findings


def _missing_findings(
    names: list[str], kind: str, reality: str, recommendation_template: str
) -> list[dict[str, str]]:
    return [
        {
            "severity": "medium",
            "doc": "AGENTS.md + README.md",
            "claim": name,
            "reality": f"{kind} {reality}",
            "recommendation": recommendation_template.replace("<name>", name),
        }
        for name in names
    ]


def _analyze_content_note() -> dict[str, str]:
    """LOW note documenting the verified effects_analyze_content resolution.

    The plan alleged the tool is registered as ``effects_analyze_content``;
    verification shows FastMCP keys by ``fn.__name__`` (mcp fastmcp/tools/
    base.py), so the alias-bound handler registers as ``analyze_content``,
    which is exactly what both doc tables list — no drift to fix.
    """
    return {
        "severity": "low",
        "doc": "AGENTS.md + README.md",
        "claim": "effects_analyze_content vs analyze_content",
        "reality": "registered name is analyze_content (FastMCP keys fn.__name__; "
        "server.py imports the handler as effects_analyze_content alias)",
        "recommendation": "None — docs match code; the plan's alleged drift is refuted",
    }
