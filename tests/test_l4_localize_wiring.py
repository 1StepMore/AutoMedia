"""L4 translation-quality wiring for ``automedia omni localize`` and MCP ``localize_output``.

Task 14 (automedia-reinforcement): the source language is resolved from the
explicit ``--source-lang`` / ``source_lang`` value, falling back to the merged
config's ``content.default_language`` (``zh``), and is passed to BOTH
``OLAdapter.translate(source_lang=...)`` and the L4 gate context.  The literal
sentinel ``"auto"`` must never reach either.

L4 is ADVISORY by decision for this integration: its verdict is recorded in the
MCP run output (``l4_verdicts``) and a failure never aborts translation — even
though the gate itself declares ``_failure_mode = "stop"``.

All tests are hermetic: synthetic ``tmp_path`` projects, a monkeypatched
``load_config`` (never the real ``~/.automedia/``), and no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.gates.translation_quality import L4TranslationQuality

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, body: str = "# Hello") -> Path:
    """Create a synthetic project with one draft under ``01_content/drafts``."""
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "article.md").write_text(body, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def default_zh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``load_config()`` to the built-in ``zh`` content default (hermetic)."""
    import automedia.core.config_loader as config_mod

    monkeypatch.setattr(
        config_mod,
        "load_config",
        lambda *args, **kwargs: {"content": {"default_language": "zh"}},
    )


@pytest.fixture()
def allow_any(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the MCP path allowlist for synthetic ``tmp_path`` projects."""
    import automedia.mcp.tools.omni as omni_mod

    monkeypatch.setattr(omni_mod, "_require_allowed", lambda *args, **kwargs: None)


@pytest.fixture()
def translate_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every ``OLAdapter.translate`` call and return a matching result.

    The returned markdown carries frontmatter whose ``source_lang`` /
    ``target_lang`` mirror the call arguments, so a correct source_lang makes
    L4 pass and a wrong one makes it fail predictably.
    """
    import automedia.omni.ol_adapter as ol_mod

    calls: list[dict[str, Any]] = []

    def _spy(
        self: object,
        md_content: str,
        source_lang: str = "auto",
        target_lang: str = "auto",
        config_path: str | None = None,
    ) -> ol_mod.TranslationResult:
        calls.append({"source_lang": source_lang, "target_lang": target_lang})
        return ol_mod.TranslationResult(
            translated_md=(
                f"---\nsource_lang: {source_lang}\ntarget_lang: {target_lang}\n---\n# Body\n"
            ),
            warnings=[],
        )

    monkeypatch.setattr(ol_mod.OLAdapter, "translate", _spy)
    return calls


@pytest.fixture()
def l4_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every L4 context while delegating to the real implementation."""
    calls: list[dict[str, Any]] = []
    real_execute = L4TranslationQuality.execute

    def _spy(self: L4TranslationQuality, context: dict[str, Any]) -> dict[str, Any]:
        calls.append(dict(context))
        return real_execute(self, context)

    monkeypatch.setattr(L4TranslationQuality, "execute", _spy)
    return calls


# ---------------------------------------------------------------------------
# resolve_source_lang
# ---------------------------------------------------------------------------


class TestResolveSourceLang:
    """The sentinel ``"auto"`` and the empty value both resolve to the config default."""

    def test_explicit_value_passes_through(self, default_zh: None) -> None:
        """A real language code is returned unchanged."""
        from automedia.omni.ol_adapter import resolve_source_lang

        assert resolve_source_lang("en") == "en"

    def test_empty_uses_config_default(self, default_zh: None) -> None:
        """An empty value falls back to ``content.default_language`` (``zh``)."""
        from automedia.omni.ol_adapter import resolve_source_lang

        assert resolve_source_lang("") == "zh"

    def test_literal_auto_is_never_returned(self, default_zh: None) -> None:
        """The literal ``"auto"`` is resolved away (L4 can never match it)."""
        from automedia.omni.ol_adapter import resolve_source_lang

        assert resolve_source_lang("auto") == "zh"
        assert resolve_source_lang("AUTO") == "zh"


# ---------------------------------------------------------------------------
# MCP localize_output
# ---------------------------------------------------------------------------


class TestMcpLocalizeOutputL4Wiring:
    """MCP ``localize_output`` resolves source_lang and records an advisory L4 verdict."""

    def test_runs_l4_and_records_verdict(
        self,
        default_zh: None,
        allow_any: None,
        translate_spy: list[dict[str, Any]],
        l4_spy: list[dict[str, Any]],
        tmp_path: Path,
    ) -> None:
        """L4 executes and its verdict is present in the returned payload."""
        from automedia.mcp.server import localize_output

        _make_project(tmp_path)
        result = localize_output(str(tmp_path), "en")

        assert result["success"] is True
        assert len(l4_spy) == 1
        assert "l4_verdicts" in result
        assert len(result["l4_verdicts"]) == 1
        assert result["l4_verdicts"][0]["passed"] is True
        assert result["l4_verdicts"][0]["target_lang"] == "en"
        assert result["l4_verdicts"][0]["file"] == "article.md"

    def test_source_lang_default_is_zh_and_never_auto(
        self,
        default_zh: None,
        allow_any: None,
        translate_spy: list[dict[str, Any]],
        l4_spy: list[dict[str, Any]],
        tmp_path: Path,
    ) -> None:
        """No explicit value → the config default (``zh``) reaches both seams; never ``"auto"``."""
        from automedia.mcp.server import localize_output

        _make_project(tmp_path)
        result = localize_output(str(tmp_path), "en")

        assert result["source_lang"] == "zh"
        assert translate_spy[0]["source_lang"] == "zh"
        assert l4_spy[0]["source_lang"] == "zh"
        assert all(call["source_lang"] != "auto" for call in translate_spy)
        assert all(ctx["source_lang"] != "auto" for ctx in l4_spy)

    def test_explicit_source_lang_reaches_translate_and_l4(
        self,
        default_zh: None,
        allow_any: None,
        translate_spy: list[dict[str, Any]],
        l4_spy: list[dict[str, Any]],
        tmp_path: Path,
    ) -> None:
        """An explicit ``source_lang`` overrides the config default at both seams."""
        from automedia.mcp.server import localize_output

        _make_project(tmp_path)
        result = localize_output(str(tmp_path), "ko", source_lang="en")

        assert result["source_lang"] == "en"
        assert translate_spy[0]["source_lang"] == "en"
        assert l4_spy[0]["source_lang"] == "en"

    def test_l4_failure_is_advisory_translation_still_succeeds(
        self,
        default_zh: None,
        allow_any: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A failing L4 verdict is recorded but does NOT abort translation."""
        import automedia.omni.ol_adapter as ol_mod
        from automedia.mcp.server import localize_output

        _make_project(tmp_path)

        # L4 declares stop semantics …
        assert L4TranslationQuality().failure_mode == "stop"

        # … but the integration is advisory: a source_lang mismatch fails L4.
        def _bad_translate(
            self: object,
            md_content: str,
            source_lang: str = "auto",
            target_lang: str = "auto",
            config_path: str | None = None,
        ) -> ol_mod.TranslationResult:
            return ol_mod.TranslationResult(
                translated_md="---\nsource_lang: fr\ntarget_lang: en\n---\n# Body\n",
                warnings=[],
            )

        monkeypatch.setattr(ol_mod.OLAdapter, "translate", _bad_translate)
        result = localize_output(str(tmp_path), "en")

        assert result["success"] is True
        assert result["l4_verdicts"][0]["passed"] is False
        assert result["l4_verdicts"][0]["failure_mode"] == "advisory"
        # Translation output was still written.
        out_file = tmp_path / "05_publish" / "en" / "article.md"
        assert out_file.exists()
        assert "en" in result["results"]
        assert any("advisory" in w.lower() for w in result["warnings"])

    def test_l4_gate_crash_is_advisory(
        self,
        default_zh: None,
        allow_any: None,
        translate_spy: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """An exception inside L4 still records a verdict and never aborts translation."""
        from automedia.mcp.server import localize_output

        _make_project(tmp_path)

        def _boom(self: L4TranslationQuality, context: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("L4 exploded")

        monkeypatch.setattr(L4TranslationQuality, "execute", _boom)
        result = localize_output(str(tmp_path), "en")

        assert result["success"] is True
        assert result["l4_verdicts"][0]["passed"] is False
        assert any("L4 exploded" in f for f in result["l4_verdicts"][0]["failures"])
        assert (tmp_path / "05_publish" / "en" / "article.md").exists()


# ---------------------------------------------------------------------------
# CLI omni localize
# ---------------------------------------------------------------------------


class TestCliLocalizeSourceLang:
    """CLI ``omni localize`` exposes ``--source-lang`` and resolves it identically."""

    def test_default_source_lang_is_zh_not_auto(
        self,
        default_zh: None,
        translate_spy: list[dict[str, Any]],
        l4_spy: list[dict[str, Any]],
        tmp_path: Path,
    ) -> None:
        """Omitting ``--source-lang`` resolves to ``zh`` for translate and L4."""
        _make_project(tmp_path)
        result = runner.invoke(
            app,
            ["omni", "localize", "--project", str(tmp_path), "--target-langs", "en"],
        )

        assert result.exit_code == 0, result.output
        assert translate_spy[0]["source_lang"] == "zh"
        assert l4_spy[0]["source_lang"] == "zh"
        assert translate_spy[0]["source_lang"] != "auto"

    def test_explicit_source_lang_reaches_translate(
        self,
        default_zh: None,
        translate_spy: list[dict[str, Any]],
        l4_spy: list[dict[str, Any]],
        tmp_path: Path,
    ) -> None:
        """``--source-lang en`` overrides the config default at both seams."""
        _make_project(tmp_path)
        result = runner.invoke(
            app,
            [
                "omni",
                "localize",
                "--project",
                str(tmp_path),
                "--target-langs",
                "ko",
                "--source-lang",
                "en",
            ],
        )

        assert result.exit_code == 0, result.output
        assert translate_spy[0]["source_lang"] == "en"
        assert l4_spy[0]["source_lang"] == "en"
