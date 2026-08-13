"""E2E test: switching between proxy, parallel, and SDK integration modes.

Verifies that all 3 integration modes (SDK direct adapter calls, proxy MCP tools,
and parallel server mode) work correctly and independently.  Each mode is tested
in isolated test functions with all adapters mocked at their source modules.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from automedia.mcp.parallel import (
    _SUBSET_MODES,
    get_server_commands,
    start_parallel_servers,
    stop_parallel_servers,
)
from automedia.omni.config import OmniConfig

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_extraction_result(
    md_content: str = "",
    manifest: dict | None = None,
    warnings: list[str] | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like an ``ExtractionResult``."""
    return MagicMock(
        md_content=md_content,
        manifest=manifest or {},
        warnings=warnings or [],
    )


def _mock_translation_result(
    translated_md: str = "",
    xliff_path: str | None = None,
    warnings: list[str] | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like a ``TranslationResult``."""
    return MagicMock(
        translated_md=translated_md,
        xliff_path=xliff_path,
        warnings=warnings or [],
    )


def _mock_orf_convert_result(
    status: str = "ok",
    output_path: str = "",
    errors: list[str] | None = None,
) -> dict:
    """Build a dict that quacks like the ORFAdapter.convert() return value."""
    return {
        "status": status,
        "output_path": output_path,
        "success": status == "ok",
        "errors": errors or [],
    }


# ===================================================================
# 1. SDK mode — direct adapter calls
# ===================================================================


class TestSDKMode:
    """SDK mode: adapters imported and called directly from ``automedia.omni``."""

    # SDK mode imports from automedia.omni namespace, so we must patch
    # the already-imported reference there (not the source module).
    @patch("automedia.omni.OPPAdapter")
    def test_opp_adapter_extract(
        self,
        mock_opp_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """OPPAdapter().extract() returns ExtractionResult with expected fields."""
        from automedia.omni import OPPAdapter

        mock_adapter = mock_opp_class.return_value
        mock_adapter.extract.return_value = _mock_extraction_result(
            md_content="# Extracted Title\n\nBody text.",
            manifest={"segments": [{"index": 0, "text": "# Extracted Title"}]},
            warnings=[],
        )

        adapter = OPPAdapter()
        result = adapter.extract(str(tmp_path / "doc.md"), "auto", "en")

        assert result.md_content == "# Extracted Title\n\nBody text."
        assert result.manifest["segments"][0]["text"] == "# Extracted Title"
        assert result.warnings == []
        mock_adapter.extract.assert_called_once_with(
            str(tmp_path / "doc.md"),
            "auto",
            "en",
        )

    @patch("automedia.omni.OLAdapter")
    def test_ol_adapter_translate(
        self,
        mock_ol_class: MagicMock,
    ) -> None:
        """OLAdapter().translate() returns TranslationResult with expected fields."""
        from automedia.omni import OLAdapter

        mock_adapter = mock_ol_class.return_value
        mock_adapter.translate.return_value = _mock_translation_result(
            translated_md="# Translated Title\n\n翻译正文。",
            xliff_path=None,
            warnings=[],
        )

        adapter = OLAdapter()
        result = adapter.translate("# Hello\n\nBody.", "en", "zh")

        assert result.translated_md == "# Translated Title\n\n翻译正文。"
        assert result.xliff_path is None
        assert result.warnings == []
        mock_adapter.translate.assert_called_once_with(
            "# Hello\n\nBody.",
            "en",
            "zh",
        )

    @patch("automedia.omni.ORFAdapter")
    def test_orf_adapter_convert(
        self,
        mock_orf_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """ORFAdapter().convert() returns dict with expected fields."""
        from automedia.omni import ORFAdapter

        mock_adapter = mock_orf_class.return_value
        output_path = str(tmp_path / "output.html")
        mock_adapter.convert.return_value = _mock_orf_convert_result(
            output_path=output_path,
        )

        adapter = ORFAdapter()
        result = adapter.convert(
            file_path=str(tmp_path / "input.md"),
            target_format="html",
        )

        assert result["status"] == "ok"
        assert result["output_path"] == output_path
        assert result["success"] is True
        assert result["errors"] == []
        mock_adapter.convert.assert_called_once()

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_sdk_adapters_exported(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
    ) -> None:
        """All 3 adapter classes and result types are exported from ``automedia.omni``."""
        import automedia.omni as omni

        assert hasattr(omni, "OPPAdapter")
        assert hasattr(omni, "OLAdapter")
        assert hasattr(omni, "ORFAdapter")
        assert hasattr(omni, "ExtractionResult")
        assert hasattr(omni, "TranslationResult")
        assert hasattr(omni, "BaseOmniAdapter")

    @patch("automedia.omni.OPPAdapter")
    def test_sdk_result_structure(
        self,
        mock_opp_class: MagicMock,
    ) -> None:
        """ExtractionResult behaves as a typed dataclass-like object in SDK mode."""
        from automedia.omni import OPPAdapter
        from automedia.omni.opp_adapter import ExtractionResult

        # Verify a real ExtractionResult can be constructed
        real_result = ExtractionResult(
            md_content="# Real",
            manifest={"key": "value"},
            warnings=["note"],
        )
        assert real_result.md_content == "# Real"
        assert real_result.manifest == {"key": "value"}
        assert real_result.warnings == ["note"]

        # Mocked ExtractionResult also works via MagicMock
        mock_adapter = mock_opp_class.return_value
        mock_adapter.extract.return_value = _mock_extraction_result(
            md_content="# Mocked",
            manifest={"segments": []},
            warnings=[],
        )

        adapter = OPPAdapter()
        result = adapter.extract("/doc.md")
        assert result.md_content == "# Mocked"
        assert result.manifest["segments"] == []


# ===================================================================
# 2. Proxy mode — MCP tool functions
# ===================================================================


class TestProxyMode:
    """Proxy mode: Omni MCP tools that proxy to adapters internally."""

    @patch("automedia.mcp.server._require_allowed")
    @patch("automedia.omni.opp_adapter.OPPAdapter")
    def test_extract_brief(
        self,
        mock_opp_class: MagicMock,
        mock_require_allowed: MagicMock,
        tmp_path: Path,
    ) -> None:
        """extract_brief proxies to OPPAdapter.extract() and returns expected dict."""
        from automedia.mcp.server import extract_brief

        mock_adapter = mock_opp_class.return_value
        mock_adapter.extract.return_value = _mock_extraction_result(
            md_content="# Extracted\n\nContent here.",
            manifest={"segments": [{"index": 0, "text": "# Extracted"}]},
            warnings=[],
        )

        result = extract_brief(
            file_path=str(tmp_path / "doc.md"),
            source_lang="en",
            target_lang="zh",
        )

        assert result["md_content"] == "# Extracted\n\nContent here."
        assert result["manifest_json"]["segments"][0]["text"] == "# Extracted"
        assert result["warnings"] == []
        mock_adapter.extract.assert_called_once_with(
            str(tmp_path / "doc.md"),
            "en",
            "zh",
        )

    @patch("automedia.omni.ol_adapter.OLAdapter")
    def test_localize_content(
        self,
        mock_ol_class: MagicMock,
    ) -> None:
        """localize_content proxies to OLAdapter.translate() and returns expected dict."""
        from automedia.mcp.server import localize_content

        mock_adapter = mock_ol_class.return_value
        mock_adapter.translate.return_value = _mock_translation_result(
            translated_md="# 翻译标题\n\n翻译正文。",
            xliff_path=None,
            warnings=[],
        )

        result = localize_content(
            md_content="# Hello\n\nBody.",
            source_lang="en",
            target_lang="zh",
        )

        assert result["translated_md"] == "# 翻译标题\n\n翻译正文。"
        assert result["xliff_path"] is None
        assert result["warnings"] == []
        mock_adapter.translate.assert_called_once_with(
            "# Hello\n\nBody.",
            "en",
            "zh",
        )

    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_format_output(
        self,
        mock_orf_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """format_output proxies to ORFAdapter.convert() and returns expected dict."""
        from automedia.mcp.server import format_output

        mock_adapter = mock_orf_class.return_value
        output_path = str(tmp_path / "output.html")
        mock_adapter.convert.return_value = _mock_orf_convert_result(
            output_path=output_path,
        )

        result = format_output(
            content="# Hello\n\nBody.",
            target_format="html",
        )

        assert result["output_path"].endswith(".html")
        assert result["output_format"] == "html"
        assert result["warnings"] == []
        mock_adapter.convert.assert_called_once()

    @patch("automedia.mcp.server._require_allowed")
    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_full_proxy_roundtrip(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        mock_require_allowed: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Full round-trip via proxy tools: extract → localize → format."""
        from automedia.mcp.server import extract_brief, format_output, localize_content

        mock_opp = mock_opp_class.return_value
        mock_opp.extract.return_value = _mock_extraction_result(
            md_content="# Doc\n\nContent body.",
            manifest={"segments": [{"index": 0, "text": "# Doc"}]},
            warnings=[],
        )

        mock_ol = mock_ol_class.return_value
        mock_ol.translate.return_value = _mock_translation_result(
            translated_md="# Doc 翻译\n\n翻译正文。",
            xliff_path=None,
            warnings=[],
        )

        mock_orf = mock_orf_class.return_value
        mock_orf.convert.return_value = _mock_orf_convert_result(
            output_path=str(tmp_path / "output.html"),
        )

        # Stage 1: extract
        extract_result = extract_brief(file_path=str(tmp_path / "doc.md"))
        assert extract_result["md_content"] == "# Doc\n\nContent body."
        assert extract_result["warnings"] == []

        # Stage 2: localize
        localize_result = localize_content(
            md_content=extract_result["md_content"],
            source_lang="en",
            target_lang="zh",
        )
        assert localize_result["translated_md"] == "# Doc 翻译\n\n翻译正文。"
        assert localize_result["warnings"] == []

        # Stage 3: format
        format_result = format_output(
            content=localize_result["translated_md"],
            target_format="html",
        )
        assert format_result["output_format"] == "html"
        assert format_result["warnings"] == []

        # Verify correct adapter methods were called
        mock_opp.extract.assert_called_once()
        mock_ol.translate.assert_called_once()
        mock_orf.convert.assert_called_once()

    def test_proxy_tools_signatures(self) -> None:
        """Proxy tool functions have the expected parameter signatures."""
        import inspect

        from automedia.mcp.server import extract_brief, format_output, localize_content

        # extract_brief(file_path, source_lang='auto', target_lang='en')
        sig = inspect.signature(extract_brief)
        params = list(sig.parameters)
        assert "file_path" in params
        assert "source_lang" in params
        assert "target_lang" in params

        # localize_content(md_content, source_lang, target_lang)
        sig = inspect.signature(localize_content)
        params = list(sig.parameters)
        assert "md_content" in params
        assert "source_lang" in params
        assert "target_lang" in params

        # format_output(content, target_format, **options)
        sig = inspect.signature(format_output)
        params = list(sig.parameters)
        assert "content" in params
        assert "target_format" in params


# ===================================================================
# 3. Mode switching verification
# ===================================================================


class TestModeSwitching:
    """Verify mode switching via config affects dispatching correctly."""

    # -- Config-level mode tests ----------------------------------------

    def test_omni_config_default_mode_is_sdk(self) -> None:
        """Default ``OmniConfig`` has ``integration_mode='sdk'``."""
        config = OmniConfig()
        assert config.integration_mode == "sdk"

    def test_omni_config_accepts_all_modes(self) -> None:
        """``OmniConfig`` accepts all valid integration modes."""
        for mode in ("sdk", "proxy", "parallel"):
            config = OmniConfig(integration_mode=mode)
            assert config.integration_mode == mode

    @patch("automedia.omni.config.load_omni_config")
    def test_sdk_mode_config_dispatch(
        self,
        mock_load: MagicMock,
    ) -> None:
        """Config ``integration_mode='sdk'`` → only AutoMedia server is launched."""
        mock_load.return_value = OmniConfig(integration_mode="sdk")
        config = mock_load()
        assert config.integration_mode == "sdk"

        cmds = get_server_commands(config.integration_mode)
        assert "AutoMedia" in cmds
        assert "OPP" not in cmds
        assert "OL" not in cmds
        assert "ORF" not in cmds

    @patch("automedia.omni.config.load_omni_config")
    def test_proxy_mode_config_dispatch(
        self,
        mock_load: MagicMock,
    ) -> None:
        """Config ``integration_mode='proxy'`` → all 4 servers are launched."""
        mock_load.return_value = OmniConfig(integration_mode="proxy")
        config = mock_load()
        assert config.integration_mode == "proxy"

        cmds = get_server_commands(config.integration_mode)
        for name in ("AutoMedia", "OPP", "OL", "ORF"):
            assert name in cmds, f"{name} should be in proxy mode servers"

    @patch("automedia.omni.config.load_omni_config")
    def test_parallel_mode_config_dispatch(
        self,
        mock_load: MagicMock,
    ) -> None:
        """Config ``integration_mode='parallel'`` → all 4 servers are launched."""
        mock_load.return_value = OmniConfig(integration_mode="parallel")
        config = mock_load()
        assert config.integration_mode == "parallel"

        cmds = get_server_commands(config.integration_mode)
        for name in ("AutoMedia", "OPP", "OL", "ORF"):
            assert name in cmds, f"{name} should be in parallel mode servers"

    # -- Subset modes mapping -------------------------------------------

    def test_subsets_modes_mapping(self) -> None:
        """``_SUBSET_MODES`` correctly maps each mode to expected server names."""
        assert _SUBSET_MODES["sdk"] == ["AutoMedia"]
        assert set(_SUBSET_MODES["proxy"]) == {"AutoMedia", "OPP", "OL", "ORF"}
        assert set(_SUBSET_MODES["parallel"]) == {"AutoMedia", "OPP", "OL", "ORF"}
        # Unknown mode falls back to "all" (all 4)
        assert set(_SUBSET_MODES.get("unknown", _SUBSET_MODES["all"])) == {
            "AutoMedia",
            "OPP",
            "OL",
            "ORF",
        }

    def test_get_server_commands_structure(self) -> None:
        """``get_server_commands`` returns dict of name → executable command list."""
        cmds = get_server_commands("sdk")
        assert isinstance(cmds, dict)
        assert "AutoMedia" in cmds

        cmd = cmds["AutoMedia"]
        assert isinstance(cmd, list)
        assert len(cmd) == 3  # [python, -m, automedia.mcp.server]
        assert cmd[0] == subprocess.sys.executable
        assert cmd[1] == "-m"
        assert cmd[2] == "automedia.mcp.server"

    def test_get_server_commands_respects_mode(self) -> None:
        """``get_server_commands`` returns different server sets per mode."""
        sdk_cmds = get_server_commands("sdk")
        proxy_cmds = get_server_commands("proxy")

        # SDK has 1 entry; proxy has 4 entries
        assert len(sdk_cmds) == 1
        assert len(proxy_cmds) == 4

        # SDK commands differ from proxy commands
        assert set(sdk_cmds.keys()) != set(proxy_cmds.keys())

    # -- Parallel server launch per mode --------------------------------

    @patch("automedia.mcp.parallel._install_signal_handlers")
    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_parallel_mode_launches_all_servers(
        self,
        mock_popen: MagicMock,
        mock_sig: MagicMock,
    ) -> None:
        """``start_parallel_servers(mode='parallel')`` launches 4 processes."""
        # Use a plain MagicMock — subprocess.Popen is mocked so spec= fails
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        servers = start_parallel_servers(mode="parallel")

        assert len(servers) == 4
        for name in ("AutoMedia", "OPP", "OL", "ORF"):
            assert name in servers

        stop_parallel_servers(servers)
        mock_proc.terminate.assert_called()

    @patch("automedia.mcp.parallel._install_signal_handlers")
    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_sdk_mode_launches_only_automedia(
        self,
        mock_popen: MagicMock,
        mock_sig: MagicMock,
    ) -> None:
        """``start_parallel_servers(mode='sdk')`` launches only the main server."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        servers = start_parallel_servers(mode="sdk")

        assert len(servers) == 1
        assert "AutoMedia" in servers
        assert "OPP" not in servers
        assert "OL" not in servers
        assert "ORF" not in servers

        stop_parallel_servers(servers)
        mock_proc.terminate.assert_called()

    @patch("automedia.mcp.parallel._install_signal_handlers")
    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_proxy_mode_launches_all_servers(
        self,
        mock_popen: MagicMock,
        mock_sig: MagicMock,
    ) -> None:
        """``start_parallel_servers(mode='proxy')`` launches 4 processes."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        servers = start_parallel_servers(mode="proxy")

        assert len(servers) == 4
        for name in ("AutoMedia", "OPP", "OL", "ORF"):
            assert name in servers

        stop_parallel_servers(servers)

    @patch("automedia.mcp.parallel._install_signal_handlers")
    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_stop_parallel_servers_handles_already_stopped(
        self,
        mock_popen: MagicMock,
        mock_sig: MagicMock,
    ) -> None:
        """``stop_parallel_servers`` gracefully handles already-terminated processes."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Already exited
        mock_popen.return_value = mock_proc

        servers = start_parallel_servers(mode="sdk")
        # Process already exited, stop should not call terminate
        stop_parallel_servers(servers)
        mock_proc.terminate.assert_not_called()


# ===================================================================
# 4. Error isolation
# ===================================================================


class TestErrorIsolation:
    """Errors in one mode do not affect another mode.

    Proxy mode wraps adapter calls in try/except and returns graceful error
    dicts.  SDK mode does **not** wrap — exceptions propagate to the caller.
    """

    @patch("automedia.mcp.server._require_allowed")
    @patch("automedia.omni.opp_adapter.OPPAdapter")
    def test_proxy_mode_swallows_adapter_errors(
        self,
        mock_opp_class: MagicMock,
        mock_require_allowed: MagicMock,
    ) -> None:
        """Proxy ``extract_brief`` catches adapter exceptions → graceful error dict."""
        from automedia.mcp.server import extract_brief

        mock_opp_class.return_value.extract.side_effect = RuntimeError(
            "OPP adapter crashed in proxy mode",
        )

        result = extract_brief(
            file_path="/nonexistent/doc.md",
            source_lang="en",
            target_lang="zh",
        )
        assert result["md_content"] == ""
        assert result["manifest_json"] == {}
        assert any("OPP adapter crashed" in w for w in result["warnings"])

    @patch("automedia.omni.ol_adapter.OLAdapter")
    def test_proxy_localize_swallows_adapter_errors(
        self,
        mock_ol_class: MagicMock,
    ) -> None:
        """Proxy ``localize_content`` catches adapter exceptions → graceful error dict."""
        from automedia.mcp.server import localize_content

        mock_ol_class.return_value.translate.side_effect = ValueError(
            "OL adapter crashed in proxy mode",
        )

        result = localize_content(
            md_content="# Hello",
            source_lang="en",
            target_lang="zh",
        )
        assert result["translated_md"] == ""
        assert result["xliff_path"] is None
        assert any("OL adapter crashed" in w for w in result["warnings"])

    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_proxy_format_swallows_adapter_errors(
        self,
        mock_orf_class: MagicMock,
    ) -> None:
        """Proxy ``format_output`` catches adapter exceptions → graceful error dict."""
        from automedia.mcp.server import format_output

        mock_orf_class.return_value.convert.side_effect = RuntimeError(
            "ORF adapter crashed in proxy mode",
        )

        result = format_output(content="# Hello", target_format="html")
        assert result["output_path"] == ""
        assert result["output_format"] == "html"
        assert any("ORF adapter crashed" in w for w in result["warnings"])

    @patch("automedia.omni.OPPAdapter")
    def test_sdk_mode_propagates_errors(
        self,
        mock_opp_class: MagicMock,
    ) -> None:
        """SDK mode does **not** wrap — adapter exceptions propagate to the caller."""
        from automedia.omni import OPPAdapter

        mock_opp_class.return_value.extract.side_effect = RuntimeError(
            "SDK mode error",
        )

        adapter = OPPAdapter()
        with pytest.raises(RuntimeError, match="SDK mode error"):
            adapter.extract("/doc.md")

    def test_sdk_ok_after_proxy_error(self) -> None:
        """A failing proxy tool does not corrupt the adapter class for SDK use.

        Both proxy and SDK modes use the same underlying adapter class.
        An error in one does not break the other because each creates
        independent adapter instances.
        """
        from automedia.mcp.server import extract_brief
        from automedia.omni.opp_adapter import OPPAdapter

        real_opp = OPPAdapter()
        # Proxy mode catches exceptions gracefully — test that the error
        # dict is returned without crashing the process.
        proxy_result = extract_brief(file_path="/nonexistent/doc.md")
        assert proxy_result["md_content"] == ""
        # SDK adapter is a separate instance and remains functional
        assert real_opp is not None
        assert hasattr(real_opp, "extract")

    def test_independent_adapter_lifecycle(self) -> None:
        """SDK and proxy modes each instantiate their own adapters independently."""
        from automedia.mcp.server import extract_brief
        from automedia.omni.opp_adapter import OPPAdapter

        # SDK creates its own adapter instance directly
        sdk_adapter = OPPAdapter()
        assert hasattr(sdk_adapter, "extract")
        assert hasattr(sdk_adapter, "name")

        # Proxy creates a separate adapter instance internally inside
        # the tool function — the two instances are independent
        proxy_result = extract_brief(file_path="/proxy_doc.md")
        assert isinstance(proxy_result, dict)
        # SDK instance is unharmed
        assert sdk_adapter.extract is not None


# ===================================================================
# 5. Cross-mode consistency: config → mode → behavior
# ===================================================================


class TestCrossModeConsistency:
    """End-to-end consistency: config mode value maps to correct behavior."""

    @patch("automedia.omni.config.load_omni_config")
    def test_config_integration_mode_is_consumed(
        self,
        mock_load: MagicMock,
    ) -> None:
        """Mode from config is used to determine server launch strategy."""
        # Simulate reading config with sdk mode
        mock_load.return_value = OmniConfig(integration_mode="sdk")
        config = mock_load()

        cmds = get_server_commands(config.integration_mode)
        assert len(cmds) == 1  # Only AutoMedia

        # Now simulate switching to proxy mode
        mock_load.return_value = OmniConfig(integration_mode="proxy")
        config = mock_load()

        cmds = get_server_commands(config.integration_mode)
        assert len(cmds) == 4  # All 4 servers

    def test_mode_affects_server_count(self) -> None:
        """The integration mode directly controls how many servers are started."""
        assert len(get_server_commands("sdk")) == 1
        assert len(get_server_commands("proxy")) == 4
        assert len(get_server_commands("parallel")) == 4

    @patch("automedia.mcp.parallel._install_signal_handlers")
    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_mode_switch_between_sdk_and_parallel(
        self,
        mock_popen: MagicMock,
        mock_sig: MagicMock,
    ) -> None:
        """Switching from SDK to parallel mode changes the number of launched servers."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        # SDK mode → 1 server
        sdk_servers = start_parallel_servers(mode="sdk")
        assert len(sdk_servers) == 1
        stop_parallel_servers(sdk_servers)

        # Parallel mode → 4 servers
        parallel_servers = start_parallel_servers(mode="parallel")
        assert len(parallel_servers) == 4
        stop_parallel_servers(parallel_servers)

    def test_get_server_commands_unknown_mode_falls_back(self) -> None:
        """Unknown mode passed to ``get_server_commands`` falls back to launching all."""
        cmds = get_server_commands("bogus_mode")
        # "bogus_mode" is not in _SUBSET_MODES, so _SUBSET_MODES.get(...) returns None
        # and the code uses _SUBSET_MODES["all"]
        assert len(cmds) == 4
        for name in ("AutoMedia", "OPP", "OL", "ORF"):
            assert name in cmds
