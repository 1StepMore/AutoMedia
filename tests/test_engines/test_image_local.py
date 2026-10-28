"""Tests for LocalImageEngine — deterministic offline Pillow images."""

from __future__ import annotations

import os
from typing import Any

import pytest
from PIL import Image, ImageStat

from automedia.engines.implementations.image_local import LocalImageEngine


class TestLocalImageAttributes:
    def test_engine_name(self) -> None:
        assert LocalImageEngine.engine_name == "local"

    def test_modality(self) -> None:
        assert LocalImageEngine.modality == "image"


class TestLocalImageCheckAvailable:
    def test_available_with_pillow(self) -> None:
        available, message = LocalImageEngine().check_available()
        assert available is True
        assert message == "PIL"


class TestLocalImageGenerate:
    def test_exact_dimensions_pipeline_call_shape(self, tmp_path: Any) -> None:
        output = str(tmp_path / "image.png")
        result = LocalImageEngine().generate("标题文字", 640, 480, output)

        assert os.path.isabs(result)
        assert os.path.isfile(result)
        with Image.open(result) as img:
            assert img.size == (640, 480)

    def test_exact_dimensions_keyword_call_shape(self, tmp_path: Any) -> None:
        output = str(tmp_path / "image.png")
        result = LocalImageEngine().generate("标题文字", output, width=320, height=240)

        assert os.path.isabs(result)
        with Image.open(result) as img:
            assert img.size == (320, 240)

    def test_non_uniform_gradient(self, tmp_path: Any) -> None:
        output = str(tmp_path / "image.png")
        LocalImageEngine().generate("gradient test", output, width=320, height=240)
        with Image.open(output) as img:
            stat = ImageStat.Stat(img.convert("L"))
            assert stat.stddev[0] > 3.0

    def test_deterministic_same_prompt(self, tmp_path: Any) -> None:
        first = str(tmp_path / "a.png")
        second = str(tmp_path / "b.png")
        engine = LocalImageEngine()
        engine.generate("相同提示词", 256, 256, first)
        engine.generate("相同提示词", 256, 256, second)

        with open(first, "rb") as fh_a, open(second, "rb") as fh_b:
            assert fh_a.read() == fh_b.read()

    def test_index_changes_output(self, tmp_path: Any) -> None:
        first = str(tmp_path / "a.png")
        second = str(tmp_path / "b.png")
        engine = LocalImageEngine()
        engine.generate("same prompt", first, width=128, height=128, index=0)
        engine.generate("same prompt", second, width=128, height=128, index=1)

        with open(first, "rb") as fh_a, open(second, "rb") as fh_b:
            assert fh_a.read() != fh_b.read()

    def test_different_prompt_differs(self, tmp_path: Any) -> None:
        first = str(tmp_path / "a.png")
        second = str(tmp_path / "b.png")
        engine = LocalImageEngine()
        engine.generate("prompt one", 128, 128, first)
        engine.generate("prompt two", 128, 128, second)

        with open(first, "rb") as fh_a, open(second, "rb") as fh_b:
            assert fh_a.read() != fh_b.read()

    def test_creates_parent_directory(self, tmp_path: Any) -> None:
        output = str(tmp_path / "nested" / "deep" / "image.png")
        LocalImageEngine().generate("nested", 100, 100, output)
        assert os.path.isfile(output)

    def test_empty_prompt_still_renders(self, tmp_path: Any) -> None:
        output = str(tmp_path / "empty.png")
        LocalImageEngine().generate("", 120, 120, output)
        assert os.path.isfile(output)

    def test_multiline_prompt_renders(self, tmp_path: Any) -> None:
        output = str(tmp_path / "multi.png")
        LocalImageEngine().generate("第一行标题\n第二行正文", 200, 200, output)
        with Image.open(output) as img:
            assert img.size == (200, 200)

    def test_long_prompt_renders(self, tmp_path: Any) -> None:
        output = str(tmp_path / "long.png")
        LocalImageEngine().generate("这是一个非常非常长的中文标题不应该崩溃", 200, 120, output)
        assert os.path.isfile(output)

    def test_invalid_dimensions_raise(self, tmp_path: Any) -> None:
        engine = LocalImageEngine()
        with pytest.raises(ValueError, match="dimensions"):
            engine.generate("x", 0, 100, str(tmp_path / "bad.png"))

    def test_empty_output_path_raises(self) -> None:
        with pytest.raises(ValueError, match="output_path"):
            LocalImageEngine().generate("x", 10, 10, "")

    def test_missing_output_path_raises(self) -> None:
        with pytest.raises(ValueError, match="output_path"):
            LocalImageEngine().generate("x", width=10, height=10)

    def test_font_path_config_accepted(self, tmp_path: Any) -> None:
        output = str(tmp_path / "font.png")
        engine = LocalImageEngine({"font_path": "/nonexistent/font.ttf"})
        engine.generate("字体回退", 150, 150, output)
        assert os.path.isfile(output)
