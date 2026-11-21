"""G4/G5 wechat pre-publish wiring (issue #609).

``prepare_wechat_publish_gates`` (gates/publish_gate_wiring.py) is the single
seam every wechat publish path calls after ``prepare_publish_log`` and before
``PublishEngine.publish_all``.  These tests pin the context resolution order,
the stop-mode blocking behaviour, and the wechat-only gating of the
distribution surface — the #585-style run-tested half lives in
``scenarios/lifecycle/g4-wechat-checklist-gate.yaml`` /
``g5-html-hard-gate.yaml``.

Synthetic fixtures only (Red Line 4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from automedia.gates.publish_gate_wiring import (
    WechatChecklistGateError,
    build_g4_wechat_context,
    prepare_wechat_publish_gates,
)

_COMPLIANT_INFO: dict[str, Any] = {
    "title": "短标题",  # ≤ 9 characters
    "digest": "weekly digest",
    "tags": ["t1", "t2", "t3", "t4", "t5"],
    "cover_image": "cover-ref.png",
}
_COMPLIANT_DRAFT_MD = (
    "# 短标题\n\n![a](1.png)\n\n![b](2.png)\n\n![c](3.png)\n\nBody of the synthetic draft.\n"
)


def _compliant_tree(tmp_path: Path, info: dict[str, Any] | None = None) -> Path:
    """Write a checklist-compliant synthetic project tree."""
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "draft.md").write_text(_COMPLIANT_DRAFT_MD, encoding="utf-8")
    payload = dict(_COMPLIANT_INFO if info is None else info)
    (tmp_path / "00_project_info.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


class TestBuildContextResolution:
    def test_info_file_fields_fill_the_context(self, tmp_path: Path) -> None:
        _compliant_tree(tmp_path)
        context = build_g4_wechat_context(str(tmp_path), {})
        assert context["title"] == "短标题"
        assert context["digest"] == "weekly digest"
        assert context["tags"] == ["t1", "t2", "t3", "t4", "t5"]
        assert context["cover_image"] == "cover-ref.png"
        assert "<img" in context["content"], "markdown draft must arrive as converted HTML"

    def test_project_dict_wins_over_info_file(self, tmp_path: Path) -> None:
        _compliant_tree(tmp_path)
        context = build_g4_wechat_context(str(tmp_path), {"title": "proj-title"})
        assert context["title"] == "proj-title"

    def test_cover_falls_back_to_layout_convention(self, tmp_path: Path) -> None:
        _compliant_tree(tmp_path, info={"title": "短标题", "tags": ["a", "b", "c", "d", "e"]})
        cover_dir = tmp_path / "02_images" / "cover"
        cover_dir.mkdir(parents=True)
        (cover_dir / "cover.png").write_bytes(b"")
        context = build_g4_wechat_context(str(tmp_path), {})
        assert context["cover_image"].endswith("cover.png")


class TestStopModeBlocking:
    def test_compliant_tree_passes_both_gates(self, tmp_path: Path) -> None:
        _compliant_tree(tmp_path)
        verdicts = prepare_wechat_publish_gates(str(tmp_path), {})
        assert verdicts["G4"]["passed"] is True
        assert verdicts["G5"]["passed"] is True

    def test_missing_tags_block_the_publish(self, tmp_path: Path) -> None:
        _compliant_tree(tmp_path, info={"title": "短标题"})
        with pytest.raises(WechatChecklistGateError) as excinfo:
            prepare_wechat_publish_gates(str(tmp_path), {})
        assert "tag_count" in str(excinfo.value)

    def test_missing_cover_blocks_the_publish(self, tmp_path: Path) -> None:
        info = {"title": "短标题", "digest": "d", "tags": ["a", "b", "c", "d", "e"]}
        _compliant_tree(tmp_path, info=info)
        with pytest.raises(WechatChecklistGateError) as excinfo:
            prepare_wechat_publish_gates(str(tmp_path), {})
        assert "cover_exists" in str(excinfo.value)

    def test_markdown_artifacts_in_html_block_g5(self, tmp_path: Path) -> None:
        _compliant_tree(tmp_path)
        drafts = tmp_path / "01_content" / "drafts"
        (drafts / "draft.md").unlink()
        (drafts / "draft.html").write_text("<p>**bold left as markdown**</p>", encoding="utf-8")
        with pytest.raises(WechatChecklistGateError) as excinfo:
            prepare_wechat_publish_gates(str(tmp_path), {})
        assert "no_markdown" in str(excinfo.value)


class TestWechatOnlyGating:
    def test_non_wechat_target_skips_the_checklist(self, tmp_path: Path) -> None:
        """A zhihu-only distribute never runs the wechat checklist.

        The fixture project violates the checklist (no tags); a zhihu-only
        publish must still reach the engine untouched.
        """
        from unittest.mock import MagicMock, patch

        from automedia.adapters.distribution import distribute_to_platforms
        from automedia.adapters.registry import AdapterRegistry

        proj_dir = tmp_path / "p"
        drafts = proj_dir / "01_content" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "draft.md").write_text("# x\n\nbody", encoding="utf-8")
        non_compliant = {
            "project_id": "zhihupublish01",
            "topic": "no tags anywhere",
            "brand": "",
            "_dir": str(proj_dir),
        }

        class _ZhihuAdapter:
            platform_name = "zhihu"
            is_stub = True

            def __init__(self, account_id: str = "") -> None:
                self.account_id = account_id

            def validate(self, artifact_dir: str) -> bool:
                return True

        AdapterRegistry.clear()
        AdapterRegistry.register(_ZhihuAdapter)
        engine_mock = MagicMock(return_value={"zhihu": {"status": "ok"}})
        try:
            with (
                patch(
                    "automedia.adapters.distribution._discover_projects",
                    return_value=[non_compliant],
                ),
                patch(
                    "automedia.adapters.distribution.PublishEngine.publish_all",
                    engine_mock,
                ),
            ):
                result = distribute_to_platforms(
                    project_id="zhihupublish01",
                    platforms=["zhihu"],
                )
        finally:
            AdapterRegistry.clear()

        assert result["platforms"]["zhihu"] == "success"
        engine_mock.assert_called_once()

    def test_wechat_target_blocked_before_the_engine(self, tmp_path: Path) -> None:
        """A checklist-violating wechat publish is blocked with an empty plan."""
        from unittest.mock import MagicMock, patch

        from automedia.adapters.distribution import distribute_to_platforms
        from automedia.adapters.registry import AdapterRegistry

        proj_dir = tmp_path / "p"
        drafts = proj_dir / "01_content" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "draft.md").write_text("# x\n\nbody", encoding="utf-8")
        non_compliant = {
            "project_id": "wechatblock01",
            "topic": "no tags anywhere",
            "brand": "",
            "_dir": str(proj_dir),
        }

        class _WechatAdapter:
            platform_name = "wechat"
            is_stub = True

            def __init__(self, account_id: str = "") -> None:
                self.account_id = account_id

            def validate(self, artifact_dir: str) -> bool:
                return True

        AdapterRegistry.clear()
        AdapterRegistry.register(_WechatAdapter)
        engine_mock = MagicMock()
        try:
            with (
                patch(
                    "automedia.adapters.distribution._discover_projects",
                    return_value=[non_compliant],
                ),
                patch(
                    "automedia.adapters.distribution.PublishEngine.publish_all",
                    engine_mock,
                ),
            ):
                result = distribute_to_platforms(
                    project_id="wechatblock01",
                    platforms=["wechat"],
                )
        finally:
            AdapterRegistry.clear()

        assert result["platforms"] == {}
        assert "tag_count" in result["error"]
        engine_mock.assert_not_called()
