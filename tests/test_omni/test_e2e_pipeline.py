"""E2E mock-mode pipeline test — OPP → OL → ORF via OmniToolRegistry."""
from __future__ import annotations

import pytest

from automedia.omni import OmniToolRegistry
from automedia.omni.base import BaseOmniAdapter
from automedia.omni.ol_adapter import TranslationResult
from automedia.omni.registry import OmniToolRegistry as Registry


class _MockOPPAdapter(BaseOmniAdapter):
    @property
    def name(self) -> str:
        return "opp_mock"

    def validate_env(self) -> bool:
        return True

    def extract(self, file_path: str) -> dict[str, str]:
        return {"status": "ok", "text": f"extracted from {file_path}", "format": "md"}


class _MockOLAdapter(BaseOmniAdapter):
    @property
    def name(self) -> str:
        return "ol_mock"

    def validate_env(self) -> bool:
        return True

    def translate(self, md_content: str, source_lang: str = "en", target_lang: str = "zh") -> TranslationResult:
        return TranslationResult(translated_md=f"[{source_lang}→{target_lang}] {md_content}")


class _MockORFAdapter(BaseOmniAdapter):
    @property
    def name(self) -> str:
        return "orf_mock"

    def validate_env(self) -> bool:
        return True

    def convert(self, file_path: str, output_path: str | None = None, **options: object) -> dict[str, str]:
        return {"status": "ok", "output_path": output_path or file_path + ".out"}


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    Registry.clear()


class TestE2EPipeline:
    """End-to-end pipeline: extract → translate → convert."""

    def test_register_all_mocks(self) -> None:
        reg = OmniToolRegistry()
        reg.register(_MockOPPAdapter())
        reg.register(_MockOLAdapter())
        reg.register(_MockORFAdapter())
        assert len(reg.list_tools()) == 3
        assert "opp_mock" in reg.list_tools()
        assert "ol_mock" in reg.list_tools()
        assert "orf_mock" in reg.list_tools()

    def test_extract_via_opp(self) -> None:
        adapter = _MockOPPAdapter()
        result = adapter.extract("/path/to/doc.md")
        assert result["status"] == "ok"
        assert "text" in result
        assert "extracted from" in result["text"]

    def test_translate_via_ol(self) -> None:
        adapter = _MockOLAdapter()
        text = "Hello world"
        result = adapter.translate(text, source_lang="en", target_lang="zh")
        assert result.translated_md == "[en→zh] Hello world"

    def test_convert_via_orf(self) -> None:
        adapter = _MockORFAdapter()
        result = adapter.convert("/path/to/input.md", output_path="/path/to/output.pdf")
        assert result["status"] == "ok"
        assert result["output_path"] == "/path/to/output.pdf"

    def test_full_pipeline(self) -> None:
        """Simulate OPP → OL → ORF pipeline end to end."""
        reg = OmniToolRegistry()
        opp = _MockOPPAdapter()
        ol = _MockOLAdapter()
        orf = _MockORFAdapter()
        reg.register(opp)
        reg.register(ol)
        reg.register(orf)

        # OPP: extract
        extract_result = opp.extract("/data/doc.md")
        assert extract_result["status"] == "ok"
        content = extract_result["text"]

        # OL: translate
        translate_result = ol.translate(content, source_lang="en", target_lang="zh")
        assert isinstance(translate_result, TranslationResult)
        assert "[en→zh]" in translate_result.translated_md

        # ORF: convert
        convert_result = orf.convert("/data/doc.md")
        assert convert_result["status"] == "ok"

    def test_pipeline_with_clear(self) -> None:
        """Clear registry mid-pipeline and verify isolation."""
        reg = OmniToolRegistry()
        reg.register(_MockOPPAdapter())
        reg.register(_MockOLAdapter())
        assert len(reg.list_tools()) == 2
        Registry.clear()
        assert len(reg.list_tools()) == 0
        with pytest.raises(KeyError, match="opp_mock"):
            reg.get("opp_mock")  # raises — adapter removed
