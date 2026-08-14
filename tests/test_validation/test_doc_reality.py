"""Unit tests for the doc↔reality audit (plan W3-T8, C4).

All fixtures are synthetic: fixture Markdown doc snippets vs fixture code
trees under ``tmp_path`` (never the real repo — Red Line 4).  The drift
shapes mirror the verified real-repo drift: wrong gate counts (29/21 vs 33),
wrong adapter split (13 real + 7 stubs vs 12 + 8), declared tools missing
from the doc tables, and the ``effects_analyze_content`` import alias that
FastMCP registers as ``analyze_content`` (``fn.__name__``).
"""

from __future__ import annotations

import json
from pathlib import Path

from automedia.validation.doc_reality import doc_reality_audit

_AGENTS_TOOLS = """\
| Tool | Description |
|------|-------------|
| `health_check` | Return server health status |
| `engine_health` | ⚠️ Deprecated: use health_engine |
| `analyze_content` | Compute content analytics for a project |
| `run_pipeline` | Execute full production pipeline |
| `doc_only_tool` | Documented but never registered |
"""

_AGENTS_CMDS = """\
| Command | Description |
|---------|-------------|
| `automedia run` | Execute production pipeline |
| `automedia doctor` | Check dependencies |
| `automedia doc_only_cmd` | Documented but never registered |
"""

_README_TOOLS = """\
| Tool | Description |
|------|-------------|
| `health_check` | Return server health status |
| `engine_health` | ⚠️ Deprecated: use health_engine |
| `analyze_content` | Compute content analytics |
| `approve_gate` | Approve a paused gate |
| `run_pipeline` | Execute full production pipeline |
| `doc_only_tool` | Documented but never registered |
"""

_README_CMDS = """\
| Command | Description |
|---------|-------------|
| `automedia run` | Execute production pipeline |
| `automedia doctor` | Check dependencies |
| `automedia doc_only_cmd` | Documented but never registered |
"""

_AGENTS_GATE_LINE = (
    "│       ├── gates/                  # Quality gates "
    "(33 implementations including H0, D1-D7, P1-P4)"
)
_README_GATE_CLAIMS = """\
- **29 quality gates**: G0-G6 (copy), V0-V7 (video/quality), L1-L4
  (lifecycle), plus pre-gate, CW, D1-D7 (distribution), P1-P4 (repurpose)
- **Total: 33 gates.** Gate order: pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4.
- | `gates/` | 21 gate implementations + failure mode knowledge base |
"""

_ADAPTER_CLAIM = (
    "- **Platform adapter system**: Extensible publish targets — "
    "5 registered adapters (13 real API + 7 documented manual-only stubs)"
)

_SERVER_PY = """\
from automedia.effects.mcp import analyze_content as effects_analyze_content

def create_server():
    mcp = _mcp()
    mcp.tool(description="Return server health status.")(health_check)
    mcp.tool(description="Engine health.")(engine_health)
    mcp.tool(description="Approve a paused gate.")(approve_gate)
    mcp.tool(description="Run the pipeline.")(run_pipeline)
    mcp.tool(description="Compute content analytics.")(effects_analyze_content)
    mcp.tool(description="Undocumented tool.")(undocumented_tool)
    return mcp
"""

_APP_PY = """\
class LazyTyperGroup:
    def register_sub_app(self, name, module, help_text=None): ...
    def register_fn(self, name, module, fn_name, help_text=None): ...

LazyTyperGroup.register_sub_app(
    "run",
    "automedia.cli.commands.run",
    help_text="Execute production pipeline.",
)
LazyTyperGroup.register_fn(
    "doctor",
    "automedia.cli.commands.doctor",
    "doctor_cmd",
    help_text="Check dependencies.",
)
LazyTyperGroup.register_fn(
    "undocumented_cmd",
    "automedia.cli.commands.undocumented",
    "undocumented_cmd",
    help_text="Registered but not documented.",
)
"""

_GATE_CLASSES = [f"class G{i}Gate(BaseGate):\n    _gate_name = 'G{i}'\n" for i in range(33)]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_drift_repo(tmp_path: Path) -> tuple[Path, Path]:
    """docs_root + src_root with drift mirroring the real repo."""
    docs = tmp_path / "docs"
    src = tmp_path / "src"
    _write(
        docs / "AGENTS.md",
        _AGENTS_TOOLS + "\n" + _AGENTS_CMDS + "\n" + _AGENTS_GATE_LINE + "\n",
    )
    _write(
        docs / "README.md",
        _README_TOOLS + "\n" + _README_CMDS + "\n" + _README_GATE_CLAIMS + "\n"
        + _ADAPTER_CLAIM + "\n",
    )
    _write(src / "automedia" / "mcp" / "server.py", _SERVER_PY)
    _write(src / "automedia" / "cli" / "app.py", _APP_PY)
    for i, cls in enumerate(_GATE_CLASSES):
        _write(src / "automedia" / "gates" / f"gate_{i:02d}.py", cls)
    for name, stub in (
        ("wechat_publisher", "False"),
        ("zhihu_publisher", "False"),
        ("feishu_notifier", "False"),
        ("xiaohongshu_publisher", "True"),
        ("douyin_publisher", "True"),
    ):
        _write(
            src / "automedia" / "adapters" / "platforms" / f"{name}.py",
            f"class {name.capitalize()}:\n    is_stub = {stub}\n",
        )
    return docs, src


def _make_clean_repo(tmp_path: Path) -> tuple[Path, Path]:
    """docs_root + src_root where every doc claim matches the code."""
    docs = tmp_path / "docs"
    src = tmp_path / "src"
    tools = """\
| Tool | Description |
|------|-------------|
| `health_check` | Return server health status |
| `run_pipeline` | Execute full production pipeline |
"""
    cmds = """\
| Command | Description |
|---------|-------------|
| `automedia run` | Execute production pipeline |
| `automedia doctor` | Check dependencies |
"""
    _write(docs / "AGENTS.md", tools + "\n" + cmds + "\n- **Total: 3 gates.**\n")
    _write(
        docs / "README.md",
        tools + "\n" + cmds + "\n- **Total: 3 gates.**\n"
        + "- **Platform adapter system**: 3 registered adapters "
        + "(3 real API + 0 documented manual-only stubs)\n",
    )
    _write(
        src / "automedia" / "mcp" / "server.py",
        "def create_server():\n"
        '    mcp.tool(description="Return server health status.")(health_check)\n'
        '    mcp.tool(description="Run the pipeline.")(run_pipeline)\n'
        "    return mcp\n",
    )
    _write(
        src / "automedia" / "cli" / "app.py",
        'LazyTyperGroup.register_sub_app("run", "automedia.cli.commands.run")\n'
        'LazyTyperGroup.register_fn("doctor", "automedia.cli.commands.doctor", "doctor_cmd")\n',
    )
    for name in ("wechat_publisher", "zhihu_publisher", "feishu_notifier"):
        _write(
            src / "automedia" / "adapters" / "platforms" / f"{name}.py",
            f"class {name.capitalize()}:\n    is_stub = False\n",
        )
    gate_files = (
        "class G0Gate(BaseGate):\n",
        "class V1Gate(BaseGate):\n",
        "class D1Gate(BaseGate):\n",
    )
    for i, cls in enumerate(gate_files):
        _write(src / "automedia" / "gates" / f"gate_{i}.py", cls)
    return docs, src


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDriftDetection:
    def test_gate_drift_flagged_when_docs_claim_wrong_counts(self, tmp_path: Path) -> None:
        # Given: docs claim 29 quality gates / 21 gate implementations while
        # AGENTS.md and README's Gate System both say 33 and code has 33
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: the two wrong claims are high-severity findings, the correct
        # ones are not
        assert report["gate_counts"]["code"] == 33
        assert report["gate_counts"]["drift"] is True
        claims = {c["claim"]: c for c in report["gate_counts"]["docs_claims"]}
        assert claims["29 quality gates"]["count"] == 29
        assert claims["21 gate implementations"]["count"] == 21
        assert claims["Total: 33 gates"]["count"] == 33
        assert claims["33 implementations including H0"]["count"] == 33
        gate_findings = [f for f in report["findings"] if f["severity"] == "high"]
        wrong_claims = {"29 quality gates", "21 gate implementations"}
        assert {f["claim"] for f in gate_findings} == wrong_claims
        assert all(f["doc"] == "README.md" for f in gate_findings)
        assert all("33 concrete BaseGate subclasses" in f["reality"] for f in gate_findings)

    def test_adapter_drift_flagged(self, tmp_path: Path) -> None:
        # Given: README claims 13 real API + 7 stubs while code has 3 real
        # (is_stub=False) + 2 stubs (is_stub=True)
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: real/stubs claims are medium findings; the matching total is
        # not; drift is True
        assert report["adapter_counts"]["code"] == {"real": 3, "stubs": 2}
        assert report["adapter_counts"]["drift"] is True
        claims = {c["claim"]: c for c in report["adapter_counts"]["docs_claims"]}
        assert claims["5 registered adapters"]["count"] == 5
        assert claims["13 real"]["count"] == 13
        assert claims["7 documented manual-only stubs"]["count"] == 7
        adapter_findings = [
            f for f in report["findings"] if "is_stub" in f["reality"]
        ]
        assert {f["claim"] for f in adapter_findings} == {
            "13 real",
            "7 documented manual-only stubs",
        }
        assert all(f["severity"] == "medium" for f in adapter_findings)
        reality = "3 real (is_stub=False) + 2 stubs (is_stub=True)"
        assert all(f["reality"] == reality for f in adapter_findings)

    def test_undocumented_tools_flagged(self, tmp_path: Path) -> None:
        # Given: a declared tool absent from both doc tables
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: it lands in mcp_tools.undocumented with a medium finding
        assert report["mcp_tools"]["undocumented"] == ["undocumented_tool"]
        finding = next(f for f in report["findings"] if f["claim"] == "undocumented_tool")
        assert finding["severity"] == "medium"
        assert "absent from the MCP tool tables" in finding["reality"]

    def test_phantom_docs_flagged(self, tmp_path: Path) -> None:
        # Given: a tool documented in both tables but never registered
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: it lands in mcp_tools.phantom_docs with a medium finding
        assert report["mcp_tools"]["phantom_docs"] == ["doc_only_tool"]
        finding = next(f for f in report["findings"] if f["claim"] == "doc_only_tool")
        assert finding["severity"] == "medium"
        assert "Unknown tool" in finding["reality"]

    def test_alias_registered_name_is_analyze_content(self, tmp_path: Path) -> None:
        # Given: server.py registers the effects handler via an import alias
        # (FastMCP keys tools by fn.__name__, so the name is analyze_content)
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: analyze_content is declared (not effects_analyze_content), is
        # documented, and the resolution is surfaced as a low finding
        assert "analyze_content" in report["mcp_tools"]["declared"]
        assert "effects_analyze_content" not in report["mcp_tools"]["declared"]
        assert "analyze_content" in report["mcp_tools"]["documented"]
        assert "analyze_content" not in report["mcp_tools"]["undocumented"]
        assert "analyze_content" not in report["mcp_tools"]["phantom_docs"]
        note = next(
            f for f in report["findings"]
            if f["claim"] == "effects_analyze_content vs analyze_content"
        )
        assert note["severity"] == "low"
        assert "analyze_content" in note["reality"]

    def test_deprecated_alias_rows_parsed(self, tmp_path: Path) -> None:
        # Given: doc tables carry deprecated-alias rows (engine_health)
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: the alias name is counted as documented and registered
        assert "engine_health" in report["mcp_tools"]["documented"]
        assert "engine_health" in report["mcp_tools"]["declared"]
        assert "engine_health" not in report["mcp_tools"]["phantom_docs"]

    def test_cli_undocumented_and_phantom(self, tmp_path: Path) -> None:
        # Given: one registered CLI command missing from docs and one
        # documented command never registered
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: both directions are reported
        assert report["cli_commands"]["undocumented"] == ["undocumented_cmd"]
        assert report["cli_commands"]["phantom_docs"] == ["doc_only_cmd"]
        assert {f["claim"] for f in report["findings"] if "CLI command" in f["reality"]} == {
            "undocumented_cmd",
            "doc_only_cmd",
        }


class TestCleanAndRobustness:
    def test_no_drift_when_docs_match_code(self, tmp_path: Path) -> None:
        # Given: every doc claim matches the code truth
        docs, src = _make_clean_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: no findings, no drift, no phantom/undocumented entries
        assert report["findings"] == []
        assert report["gate_counts"]["drift"] is False
        assert report["gate_counts"]["code"] == 3
        assert report["adapter_counts"]["drift"] is False
        assert report["adapter_counts"]["code"] == {"real": 3, "stubs": 0}
        assert report["mcp_tools"]["undocumented"] == []
        assert report["mcp_tools"]["phantom_docs"] == []
        assert report["cli_commands"]["undocumented"] == []
        assert report["cli_commands"]["phantom_docs"] == []

    def test_missing_doc_file_does_not_crash(self, tmp_path: Path) -> None:
        # Given: only README.md exists in the docs root
        docs, src = _make_clean_repo(tmp_path)
        (docs / "AGENTS.md").unlink()

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: it audits the surviving doc file only
        assert any("README.md" in f for f in report["checked_files"])
        assert not any("AGENTS.md" in f for f in report["checked_files"])
        assert "health_check" in report["mcp_tools"]["documented"]
        assert report["mcp_tools"]["undocumented"] == []

    def test_deterministic_output(self, tmp_path: Path) -> None:
        # Given: a drift-laden repo
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs twice
        first = doc_reality_audit(docs_root=docs, src_root=src)
        second = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: the reports are byte-identical
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        assert first == second

    def test_report_shape(self, tmp_path: Path) -> None:
        # Given: a drift-laden repo
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: every documented section has the expected keys and types
        assert set(report) == {
            "checked_files",
            "mcp_tools",
            "cli_commands",
            "gate_counts",
            "adapter_counts",
            "findings",
        }
        assert all(isinstance(f, str) for f in report["checked_files"])
        for section in ("mcp_tools", "cli_commands"):
            expected = {"declared", "documented", "undocumented", "phantom_docs"}
            assert set(report[section]) == expected
            assert all(
                isinstance(v, list) and all(isinstance(n, str) for n in v)
                for v in report[section].values()
            )
        assert set(report["gate_counts"]) == {"docs_claims", "code", "drift"}
        assert isinstance(report["gate_counts"]["code"], int)
        assert isinstance(report["gate_counts"]["drift"], bool)
        for claim in report["gate_counts"]["docs_claims"]:
            assert set(claim) == {"doc", "claim", "count"}
            assert isinstance(claim["count"], int)
        assert set(report["adapter_counts"]) == {"docs_claims", "code", "drift"}
        assert set(report["adapter_counts"]["code"]) == {"real", "stubs"}
        finding_keys = {"severity", "doc", "claim", "reality", "recommendation"}
        assert set(report["findings"][0]) == finding_keys
        assert report["findings"][0]["severity"] in {"high", "medium", "low"}

    def test_findings_sorted_by_severity_then_doc_then_claim(self, tmp_path: Path) -> None:
        # Given: a drift-laden repo
        docs, src = _make_drift_repo(tmp_path)

        # When: the audit runs
        report = doc_reality_audit(docs_root=docs, src_root=src)

        # Then: findings are ordered high → medium → low, then doc, then claim
        rank = {"high": 0, "medium": 1, "low": 2}
        severities = [f["severity"] for f in report["findings"]]
        assert severities == sorted(severities, key=rank.__getitem__)
        medium = [f for f in report["findings"] if f["severity"] == "medium"]
        assert [f["doc"] for f in medium] == sorted(f["doc"] for f in medium)
        for doc in {f["doc"] for f in medium}:
            group = [f["claim"] for f in medium if f["doc"] == doc]
            assert group == sorted(group)
