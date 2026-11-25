"""Tests for the ``image_prompt.j2`` template structure (#681).

Experiment #681 showed that with the same local ComfyUI model, a
quality-tags-first prompt produced a pretty but scene-irrelevant picture,
while a subject-first prompt produced an on-topic one.  The template must
therefore lead with the subject and relegate quality/style tags to the end,
and it must render the ``scene_text`` narration beat when one is given.

No LLM is involved — these tests render the built-in template directly via
:func:`automedia.prompts.load_prompt`.
"""

from __future__ import annotations

import pytest

from automedia.prompts import load_prompt


@pytest.fixture(autouse=True)
def _no_user_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Point the override chain at an empty dir so the built-in template wins.

    ``load_prompt`` prefers ``~/.automedia/overrides/prompts/image_prompt.j2``
    when it exists; a local override on the dev machine would otherwise make
    these tests assert against the override instead of the shipped template.
    """
    monkeypatch.setattr("automedia.prompts._OVERRIDE_DIR", tmp_path / "overrides")


def _render(**kwargs: object) -> str:
    base: dict[str, object] = {"topic": "AI trends", "brand": "", "image_index": 0}
    base.update(kwargs)
    return load_prompt("image_prompt", **base)


class TestImagePromptSubjectFirst:
    """Subject-first instruction replaces the quality-tags-first one (#681)."""

    def test_contains_subject_first_instruction(self) -> None:
        rendered = _render()
        assert "Start with the subject" in rendered

    def test_old_quality_tags_instruction_is_gone(self) -> None:
        rendered = _render()
        assert "Start with quality tags" not in rendered

    def test_quality_and_style_tags_relegated_to_end(self) -> None:
        rendered = _render()
        assert "at the END" in rendered


class TestImagePromptSceneText:
    """The narration beat is rendered into the template context."""

    def test_scene_text_is_rendered(self) -> None:
        rendered = _render(scene_text="低价工具把成本转成重复的人工")
        assert "低价工具把成本转成重复的人工" in rendered

    def test_scene_text_carrying_the_do_not_render_words_rule(self) -> None:
        rendered = _render(scene_text="创作者在深夜补报表。")
        assert "do NOT render its words in the image" in rendered

    def test_no_text_constraint_present_with_scene_text(self) -> None:
        rendered = _render(scene_text="创作者在深夜补报表。")
        assert "no text, no letters, no captions" in rendered


class TestImagePromptBackwardCompatible:
    """Callers that do not pass ``scene_text`` (batch image tracks) still render."""

    def test_renders_without_scene_text(self) -> None:
        rendered = _render()
        assert "Image index: 0" in rendered
        # The scene block must be omitted entirely, not rendered empty.
        assert "Narration beat" not in rendered

    def test_renders_with_empty_scene_text(self) -> None:
        rendered = _render(scene_text="")
        assert "Narration beat" not in rendered

    def test_renders_with_optional_brand_and_platform(self) -> None:
        rendered = load_prompt(
            "image_prompt",
            topic="t",
            brand="Acme",
            image_index=2,
            platform="",
            scene_text="",
        )
        assert "Brand context: Acme" in rendered
        assert "Image index: 2" in rendered
