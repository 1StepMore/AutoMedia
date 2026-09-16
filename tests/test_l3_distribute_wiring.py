"""L3 platform-integrity wiring for the CLI distribution path.

Task 13 (automedia-reinforcement): ``automedia distribute`` runs the D-gates
that write ``04_distribution/<platform>/*.md`` and must then gate the run on
``L3PlatformIntegrity`` with a COMPLETE, grounded context.  MCP
``distribute_content`` is a PUBLISH path (it produces no
``04_distribution/**/*.md``) and is deliberately NOT wired to L3.

The grounded context contract this module locks:

- ``platforms``/``expected_platforms``: the target platform set.
- ``file_paths``/``media_files``: the files the D-gates actually produced.
- ``formats``: the extensions of those produced files.
- ``required_formats``: the explicit, producible constant ``["md"]`` — the
  gate default (``["mp4", "txt", "json"]``) would block every distribution.
- ``unified_content``: the base draft.
- ``archive_metadata``: title/platform/created_at, with ``platform`` a SINGLE
  deterministic member (``sorted(platforms)[0]``) because the gate only
  requires membership even for a multi-platform run.
- ``content_platform_map`` is NOT set, so ``no_platform_splitting`` passes.

All tests are hermetic: synthetic ``tmp_path`` projects, no network, and the
D-gate LLM is mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.cli.commands.distribute import build_l3_distribution_context
from automedia.gates.platform_integrity import L3PlatformIntegrity
from tests.test_distribution.test_d_gate_base import patch_llm_complete

runner = CliRunner()

_CREATED_AT = "2026-07-07T00:00:00+00:00"
_D1_LLM_TARGET = "automedia.gates.distribution.d1_wechat.llm_complete"
_D2_LLM_TARGET = "automedia.gates.distribution.d2_twitter.llm_complete"

_PROJECT_INFO: dict[str, Any] = {
    "topic": "Distribution Topic",
    "created_at": _CREATED_AT,
}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _check(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in result["checks"] if c["name"] == name)


def _produced(*names: str) -> list[str]:
    return [f"/data/proj/04_distribution/{name}" for name in names]


def _make_project(
    base_dir: Path,
    *,
    project_id: str = "dist13abc456",
    topic: str = "Distribution Topic",
    brand: str = "TestBrand",
    created_at: str = _CREATED_AT,
    draft: str = "# Distribution Title\n\nBody content for distribution.",
) -> Path:
    """Create a synthetic project dir with a draft and 00_project_info.json."""
    proj_dir = base_dir / f"20260707_{project_id}"
    drafts = proj_dir / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "draft.md").write_text(draft, encoding="utf-8")
    info: dict[str, Any] = {
        "project_id": project_id,
        "topic": topic,
        "brand": brand,
        "tenant_id": "default",
        "created_at": created_at,
        "status": "completed",
    }
    (proj_dir / "00_project_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return proj_dir


@pytest.fixture()
def l3_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Spy on L3.execute, recording each context, delegating to the real gate."""
    calls: list[dict[str, Any]] = []
    real_execute = L3PlatformIntegrity.execute

    def _spy(self: L3PlatformIntegrity, context: dict[str, Any]) -> dict[str, Any]:
        calls.append(dict(context))
        return real_execute(self, context)

    monkeypatch.setattr(L3PlatformIntegrity, "execute", _spy)
    return calls


# =========================================================================
# build_l3_distribution_context
# =========================================================================


class TestBuildL3DistributionContext:
    """The builder emits every key the gate reads that can fail."""

    def test_builds_complete_grounded_context(self) -> None:
        produced = _produced("wechat/a.md", "zhihu/b.md")

        ctx = build_l3_distribution_context(
            _PROJECT_INFO,
            ["wechat", "zhihu"],
            produced,
            unified_content="Unified base draft body.",
        )

        assert ctx["platforms"] == ["wechat", "zhihu"]
        assert ctx["expected_platforms"] == ["wechat", "zhihu"]
        assert ctx["file_paths"] == produced
        assert ctx["media_files"] == produced
        assert ctx["formats"] == ["md"]
        assert ctx["required_formats"] == ["md"]
        assert ctx["unified_content"] == "Unified base draft body."
        assert ctx["archive_metadata"] == {
            "title": "Distribution Topic",
            "platform": "wechat",
            "created_at": _CREATED_AT,
        }
        # Deliberately not set — makes no_platform_splitting pass.
        assert "content_platform_map" not in ctx

    def test_platforms_are_normalised_to_a_deterministic_order(self) -> None:
        ctx = build_l3_distribution_context(
            _PROJECT_INFO,
            ["zhihu", "wechat"],
            _produced("zhihu/a.md"),
            unified_content="body",
        )

        assert ctx["platforms"] == ["wechat", "zhihu"]
        assert ctx["expected_platforms"] == ["wechat", "zhihu"]

    def test_metadata_platform_is_a_single_deterministic_member(self) -> None:
        ctx = build_l3_distribution_context(
            _PROJECT_INFO,
            ["twitter", "wechat"],
            _produced("twitter/a.md", "wechat/b.md"),
            unified_content="body",
        )

        # One deterministic value even for a multi-platform run.
        assert ctx["archive_metadata"]["platform"] == "twitter"
        assert ctx["archive_metadata"]["platform"] in ctx["platforms"]

    def test_required_formats_is_the_explicit_constant_not_derived(self) -> None:
        """required_formats stays ["md"] even when nothing was produced."""
        ctx = build_l3_distribution_context(
            _PROJECT_INFO,
            ["wechat"],
            [],
            unified_content="body",
        )

        assert ctx["formats"] == []
        assert ctx["required_formats"] == ["md"]

    def test_formats_are_the_produced_extensions(self) -> None:
        ctx = build_l3_distribution_context(
            _PROJECT_INFO,
            ["wechat"],
            _produced("wechat/a.md", "wechat/meta.json"),
            unified_content="body",
        )

        assert ctx["formats"] == ["json", "md"]

    def test_metadata_title_and_created_at_come_from_project_info(self) -> None:
        info = {"topic": "Another Topic", "created_at": "2025-01-02T03:04:05+00:00"}

        ctx = build_l3_distribution_context(
            info,
            ["wechat"],
            _produced("wechat/a.md"),
            unified_content="body",
        )

        assert ctx["archive_metadata"]["title"] == "Another Topic"
        assert ctx["archive_metadata"]["created_at"] == "2025-01-02T03:04:05+00:00"


# =========================================================================
# The built context against the real L3 gate
# =========================================================================


class TestBuiltContextAgainstL3:
    """Contract-completeness proofs: each removed input fails its check."""

    def _context(self, produced: list[str] | None = None) -> dict[str, Any]:
        return build_l3_distribution_context(
            _PROJECT_INFO,
            ["wechat", "zhihu"],
            _produced("wechat/a.md", "zhihu/b.md") if produced is None else produced,
            unified_content="Unified base draft body.",
        )

    def test_complete_context_passes_all_checks(self) -> None:
        result = L3PlatformIntegrity().execute(self._context())

        assert result["passed"] is True
        assert all(c["passed"] for c in result["checks"])

    def test_missing_produced_md_fails_format_completeness(self) -> None:
        """No produced artifacts => formats empty => format_completeness fails."""
        ctx = self._context(produced=[])

        result = L3PlatformIntegrity().execute(ctx)

        fc = _check(result, "format_completeness")
        assert fc["passed"] is False
        assert result["passed"] is False

    def test_wrong_produced_extension_fails_format_completeness(self) -> None:
        ctx = self._context(produced=_produced("wechat/a.txt"))

        result = L3PlatformIntegrity().execute(ctx)

        fc = _check(result, "format_completeness")
        assert fc["passed"] is False
        assert "md" in fc["detail"]

    def test_omitting_archive_metadata_fails_metadata_integrity(self) -> None:
        """Removing archive_metadata proves the builder-supplied key is required."""
        ctx = self._context()
        # Sanity: the built context supplies it and passes.
        assert L3PlatformIntegrity().execute(ctx)["passed"] is True

        del ctx["archive_metadata"]

        result = L3PlatformIntegrity().execute(ctx)

        mi = _check(result, "metadata_integrity")
        assert mi["passed"] is False
        assert "archive_metadata" in mi["detail"]
        assert result["passed"] is False

    def test_content_platform_map_fails_no_platform_splitting(self) -> None:
        ctx = self._context()
        ctx["content_platform_map"] = {"wechat": "content_a", "zhihu": "content_b"}

        result = L3PlatformIntegrity().execute(ctx)

        ns = _check(result, "no_platform_splitting")
        assert ns["passed"] is False
        assert result["passed"] is False


# =========================================================================
# CLI automedia distribute wiring
# =========================================================================


class TestCliDistributeL3Wiring:
    """A real distribute run gates on L3 with the produced artifacts."""

    def test_real_distribute_run_passes_l3(
        self, tmp_path: Path, l3_spy: list[dict[str, Any]]
    ) -> None:
        _make_project(tmp_path)

        with patch_llm_complete(_D1_LLM_TARGET):
            result = runner.invoke(
                app,
                [
                    "distribute",
                    "dist13abc456",
                    "--platforms",
                    "wechat",
                    "--base-dir",
                    str(tmp_path),
                ],
            )

        assert result.exit_code == 0, result.output
        assert len(l3_spy) == 1
        ctx = l3_spy[0]

        assert ctx["platforms"] == ["wechat"]
        assert ctx["expected_platforms"] == ["wechat"]
        assert ctx["required_formats"] == ["md"]
        assert ctx["formats"] == ["md"]
        assert ctx["archive_metadata"] == {
            "title": "Distribution Topic",
            "platform": "wechat",
            "created_at": _CREATED_AT,
        }
        assert "content_platform_map" not in ctx

        # The produced .md is real and reached the gate.
        produced = ctx["file_paths"]
        assert len(produced) == 1
        assert produced[0].endswith(".md")
        assert Path(produced[0]).is_file()
        assert ctx["media_files"] == produced

        # And that exact context genuinely passes L3.
        assert L3PlatformIntegrity().execute(ctx)["passed"] is True

    def test_multi_platform_run_uses_one_deterministic_metadata_platform(
        self, tmp_path: Path, l3_spy: list[dict[str, Any]]
    ) -> None:
        _make_project(tmp_path)

        with patch_llm_complete(_D1_LLM_TARGET), patch_llm_complete(_D2_LLM_TARGET):
            result = runner.invoke(
                app,
                [
                    "distribute",
                    "dist13abc456",
                    "--platforms",
                    "twitter,wechat",
                    "--base-dir",
                    str(tmp_path),
                ],
            )

        assert result.exit_code == 0, result.output
        assert len(l3_spy) == 1
        ctx = l3_spy[0]

        assert ctx["platforms"] == ["twitter", "wechat"]
        assert ctx["expected_platforms"] == ["twitter", "wechat"]
        assert ctx["archive_metadata"]["platform"] == "twitter"
        assert ctx["archive_metadata"]["platform"] in ctx["platforms"]
        assert len(ctx["file_paths"]) == 2
        assert ctx["formats"] == ["md"]

    def test_l3_stop_failure_blocks_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing L3 (failure_mode 'stop') must block the distribution."""
        _make_project(tmp_path)

        def _failing_execute(self: L3PlatformIntegrity, context: dict[str, Any]) -> dict[str, Any]:
            return {
                "gate": "L3",
                "passed": False,
                "checks": [{"name": "format_completeness", "passed": False, "detail": "simulated"}],
                "error": "L3 simulated failure",
            }

        monkeypatch.setattr(L3PlatformIntegrity, "execute", _failing_execute)

        with patch_llm_complete(_D1_LLM_TARGET):
            result = runner.invoke(
                app,
                [
                    "distribute",
                    "dist13abc456",
                    "--platforms",
                    "wechat",
                    "--base-dir",
                    str(tmp_path),
                ],
            )

        assert result.exit_code == 1
        assert "L3" in result.output
        # The D-gate still ran and produced its artifact; L3 blocked the verdict.
        assert list((tmp_path).glob("*/04_distribution/wechat/*.md"))


# =========================================================================
# MCP distribute_content must NOT be wired to L3
# =========================================================================


class TestMcpDistributeContentStaysPublishPath:
    """MCP distribute_content publishes via PublishEngine — L3 has no producer."""

    def test_mcp_distribute_content_does_not_invoke_l3(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from automedia.mcp.tools_distribution import distribute_content

        calls: list[dict[str, Any]] = []

        def _spy(self: L3PlatformIntegrity, context: dict[str, Any]) -> dict[str, Any]:
            calls.append(dict(context))
            raise AssertionError("L3 must not be invoked on the MCP publish path")

        monkeypatch.setattr(L3PlatformIntegrity, "execute", _spy)

        with patch(
            "automedia.adapters.distribution.distribute_to_platforms",
            return_value={
                "platforms": {"wechat": "success"},
                "summary": "1/1 platforms succeeded",
                "dry_run": False,
            },
        ) as mock_delegate:
            result = distribute_content(project_id="dist13abc456", platforms="wechat")

        mock_delegate.assert_called_once()
        assert calls == []
        assert result["platforms"]["wechat"] == "success"
