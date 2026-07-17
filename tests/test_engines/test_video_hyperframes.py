"""Unit tests for :class:`~automedia.engines.implementations.video_hyperframes.HyperFramesVideoEngine`.

Tests cover:

* Engine metadata (``engine_name``, ``modality``, ABC hierarchy)
* Auto-registration in :class:`EngineRegistry` with ``video`` modality
* :meth:`check_available` — hyperframes found, ffmpeg fallback, neither
* :meth:`render` — successful hyperframes CLI path
* :meth:`render` — asset copying and temp directory creation
* :meth:`render` — FFmpeg fallback when hyperframes fails
* :meth:`render` — ``EngineExecutionError`` when both paths fail
* :meth:`render` — ``EngineExecutionError`` on empty images
* Temp directory cleanup via ``shutil.rmtree`` in ``finally`` blocks
* Custom config (``timeout``, ``quality``) propagation

All external dependencies (``shutil.which``, ``subprocess.run``,
``tempfile.mkdtemp``, filesystem operations) are mocked — no real
subprocess or filesystem interaction.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from automedia.engines.errors import EngineExecutionError
from automedia.engines.implementations.video_hyperframes import HyperFramesVideoEngine
from automedia.engines.registry import EngineRegistry

# ===================================================================
# Helpers
# ===================================================================


def _ok_result() -> MagicMock:
    """Return a :class:`~unittest.mock.MagicMock` mimicking a successful
    :class:`subprocess.CompletedProcess` (``returncode=0``)."""
    return MagicMock(returncode=0, stdout="", stderr="")


def _fail_result(code: int = 1) -> MagicMock:
    """Return a :class:`~unittest.mock.MagicMock` mimicking a failing
    :class:`subprocess.CompletedProcess` (non-zero ``returncode``)."""
    return MagicMock(returncode=code, stdout="", stderr="render error")


# ===================================================================
# Shared fixtures
# ===================================================================


@pytest.fixture()
def engine() -> HyperFramesVideoEngine:
    """Return a fresh engine instance with empty config."""
    return HyperFramesVideoEngine()


@pytest.fixture()
def sample_assets() -> dict[str, Any]:
    """Synthetic assets dict — all paths are mocked away."""
    return {
        "images": ["/fake/img1.png", "/fake/img2.png"],
        "audio": "/fake/audio.mp3",
        "subtitles": "/fake/subs.srt",
        "template_dir": "/fake/template",
        "content": "Overlay text for the rendered video.",
    }


@pytest.fixture()
def minimal_assets() -> dict[str, Any]:
    """Minimal assets — images and content only."""
    return {
        "images": ["/fake/img1.png"],
        "content": "Minimal overlay.",
    }


@pytest.fixture(autouse=True)
def _engine_registry_cleanup() -> Iterator[None]:
    """Reset :class:`EngineRegistry` after every test in this module.

    Prevents cross-test pollution when other test modules also
    register engines in the global singleton.
    """
    yield
    EngineRegistry().clear()


@pytest.fixture()
def mock_all() -> Iterator[dict[str, MagicMock]]:
    """Patch every external dependency used by the engine.

    Default behaviour
    -----------------
    * ``shutil.which`` → ``None`` (neither ``hyperframes`` nor
      ``ffmpeg`` on ``PATH``)
    * ``subprocess.run`` → success (``returncode=0``)
    * ``tempfile.mkdtemp`` → ``"/tmp/hyperframes_test"``
    * ``os.path.isfile``, ``os.path.isdir`` → ``True``

    Each test overrides specific mocks via the returned dict.
    """
    with (
        patch(
            "automedia.engines.implementations.video_hyperframes.shutil.which",
        ) as m_which,
        patch(
            "automedia.engines.implementations.video_hyperframes.subprocess.run",
        ) as m_run,
        patch(
            "automedia.engines.implementations.video_hyperframes.tempfile.mkdtemp",
        ) as m_mkdtemp,
        patch(
            "automedia.engines.implementations.video_hyperframes.shutil.rmtree",
        ) as m_rmtree,
        patch(
            "automedia.engines.implementations.video_hyperframes.shutil.copy2",
        ) as m_copy2,
        patch(
            "automedia.engines.implementations.video_hyperframes.shutil.copytree",
        ) as m_copytree,
        patch(
            "automedia.engines.implementations.video_hyperframes.shutil.move",
        ) as m_move,
        patch(
            "automedia.engines.implementations.video_hyperframes.os.makedirs",
        ) as m_makedirs,
        patch(
            "automedia.engines.implementations.video_hyperframes.os.path.isfile",
        ) as m_isfile,
        patch(
            "automedia.engines.implementations.video_hyperframes.os.path.isdir",
        ) as m_isdir,
    ):
        # --- defaults ---
        m_which.return_value = None
        m_run.return_value = _ok_result()
        m_mkdtemp.return_value = "/tmp/hyperframes_test"
        m_isfile.return_value = True
        m_isdir.return_value = True

        yield {
            "which": m_which,
            "run": m_run,
            "mkdtemp": m_mkdtemp,
            "rmtree": m_rmtree,
            "copy2": m_copy2,
            "copytree": m_copytree,
            "move": m_move,
            "makedirs": m_makedirs,
            "isfile": m_isfile,
            "isdir": m_isdir,
        }


# ===================================================================
# Engine metadata
# ===================================================================


class TestEngineMetadata:
    """Verify engine-name, modality, and ABC hierarchy."""

    def test_engine_name(self) -> None:
        assert HyperFramesVideoEngine.engine_name == "hyperframes"

    def test_modality(self) -> None:
        assert HyperFramesVideoEngine.modality == "video"

    def test_is_base_video_engine_subclass(self) -> None:
        from automedia.engines.base import BaseVideoEngine

        assert issubclass(HyperFramesVideoEngine, BaseVideoEngine)


# ===================================================================
# Auto-registration in EngineRegistry
# ===================================================================


class TestAutoRegistration:
    """Auto-registration triggered by ``__init_subclass__``."""

    def setup_method(self) -> None:
        """Clear registry so we can test from a clean slate."""
        EngineRegistry().clear()

    def test_registered_in_engine_registry(self) -> None:
        """Engine is present in the global registry after module import."""
        _ = importlib.reload(
            importlib.import_module(
                "automedia.engines.implementations.video_hyperframes",
            ),
        )
        assert "hyperframes" in EngineRegistry()
        cls = EngineRegistry().get("hyperframes")
        assert cls.__name__ == "HyperFramesVideoEngine"

    def test_registered_for_video_modality(self) -> None:
        """Engine appears in ``list_by_modality("video")``."""
        _ = importlib.reload(
            importlib.import_module(
                "automedia.engines.implementations.video_hyperframes",
            ),
        )
        _registry: Any = EngineRegistry()
        assert "hyperframes" in _registry.list_by_modality("video")


# ===================================================================
# check_available
# ===================================================================


class TestCheckAvailable:
    """:meth:`HyperFramesVideoEngine.check_available` behaviour."""

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _which_side_effect(mapping: dict[str, str | None]) -> Any:
        """Build a ``side_effect`` callable for ``shutil.which``."""

        def _which(name: str) -> str | None:
            return mapping.get(name)

        return _which

    # -- tests ----------------------------------------------------------

    @patch("automedia.engines.implementations.video_hyperframes.shutil.which")
    def test_hyperframes_found(self, mock_which: MagicMock) -> None:
        """> ``hyperframes`` on ``PATH`` → ``(True, "hyperframes found at ...")``."""
        mock_which.side_effect = self._which_side_effect(
            {"hyperframes": "/usr/bin/hyperframes"},
        )
        ok, msg = HyperFramesVideoEngine().check_available()
        assert ok is True
        assert "hyperframes found at" in msg
        assert "/usr/bin/hyperframes" in msg

    @patch("automedia.engines.implementations.video_hyperframes.shutil.which")
    def test_ffmpeg_fallback(self, mock_which: MagicMock) -> None:
        """> ``ffmpeg`` on ``PATH`` (but not ``hyperframes``)
        → ``(True, "... ffmpeg fallback ...")``."""
        mock_which.side_effect = self._which_side_effect(
            {"hyperframes": None, "ffmpeg": "/usr/bin/ffmpeg"},
        )
        ok, msg = HyperFramesVideoEngine().check_available()
        assert ok is True
        assert "ffmpeg fallback" in msg
        assert "/usr/bin/ffmpeg" in msg

    @patch("automedia.engines.implementations.video_hyperframes.shutil.which")
    def test_neither_found(self, mock_which: MagicMock) -> None:
        """> Neither binary on ``PATH`` → ``(False, ...)``."""
        mock_which.return_value = None
        ok, msg = HyperFramesVideoEngine().check_available()
        assert ok is False
        assert "Neither" in msg
        assert "hyperframes" in msg
        assert "ffmpeg" in msg


# ===================================================================
# render — HyperFrames primary path
# ===================================================================


class TestRenderHyperFrames:
    """:meth:`render` when the ``hyperframes`` CLI is available."""

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_render_success_returns_absolute_path(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Successful hyperframes render returns ``os.path.abspath(output)``."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)

        output = str(tmp_path / "output.mp4")
        result = HyperFramesVideoEngine().render(sample_assets, output)

        assert result == os.path.abspath(output)

    def test_render_builds_correct_hyperframes_command(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """The subprocess is invoked with the expected CLI arguments."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)

        output = str(tmp_path / "output.mp4")
        HyperFramesVideoEngine().render(sample_assets, output)

        mock_all["run"].assert_called_once_with(
            [
                "hyperframes",
                "render",
                "--quality", "high",
                "--assets", "/tmp/hyperframes_test",
                "--output", output,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

    def test_render_copies_images_and_assets(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Images, audio, subtitles, and template are copied to the temp dir."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)

        output = str(tmp_path / "output.mp4")
        HyperFramesVideoEngine().render(sample_assets, output)

        # images/ sub-directory
        mock_all["makedirs"].assert_any_call(
            "/tmp/hyperframes_test/images",
            exist_ok=True,
        )

        # each image file
        mock_all["copy2"].assert_any_call(
            "/fake/img1.png",
            "/tmp/hyperframes_test/images",
        )
        mock_all["copy2"].assert_any_call(
            "/fake/img2.png",
            "/tmp/hyperframes_test/images",
        )

        # audio
        mock_all["copy2"].assert_any_call(
            "/fake/audio.mp3",
            "/tmp/hyperframes_test",
        )

        # subtitles
        mock_all["copy2"].assert_any_call(
            "/fake/subs.srt",
            "/tmp/hyperframes_test",
        )

        # template directory (recursive copy)
        mock_all["copytree"].assert_called_once_with(
            "/fake/template",
            "/tmp/hyperframes_test/template",
            dirs_exist_ok=True,
        )

    def test_render_skips_missing_optional_assets(
        self,
        mock_all: dict[str, MagicMock],
        minimal_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """When audio/subtitles/template are absent only images are copied."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)
        # Pretend no optional asset files exist
        mock_all["isfile"].return_value = False
        mock_all["isdir"].return_value = False

        output = str(tmp_path / "output.mp4")
        HyperFramesVideoEngine().render(minimal_assets, output)

        # Only image copies should have happened
        copy_calls = mock_all["copy2"].call_args_list
        assert len(copy_calls) == 1  # only the image
        assert copy_calls[0] == call(
            "/fake/img1.png",
            "/tmp/hyperframes_test/images",
        )
        # copytree should NOT have been called
        mock_all["copytree"].assert_not_called()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def test_render_cleans_up_temp_dir(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """> ``shutil.rmtree`` is called on the temp dir after success."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)

        output = str(tmp_path / "output.mp4")
        HyperFramesVideoEngine().render(sample_assets, output)

        mock_all["rmtree"].assert_called_once_with(
            "/tmp/hyperframes_test",
            ignore_errors=True,
        )

    def test_render_cleans_up_temp_dir_on_failure(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """> ``shutil.rmtree`` is called even when the subprocess fails
        (hyperframes only, no ffmpeg fallback)."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
            "ffmpeg": None,
        }.get(x)
        mock_all["run"].return_value = _fail_result()

        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError):
            HyperFramesVideoEngine().render(sample_assets, output)

        mock_all["rmtree"].assert_called_once_with(
            "/tmp/hyperframes_test",
            ignore_errors=True,
        )


# ===================================================================
# render — FFmpeg fallback
# ===================================================================


class TestRenderFFmpegFallback:
    """:meth:`render` when hyperframes fails and ffmpeg is available."""

    def test_fallback_succeeds(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Hyperframes fails → FFmpeg slideshow is used and succeeds."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(x)
        # hyperframes → fail, ffmpeg step 1 → ok, step 2 → ok
        mock_all["run"].side_effect = [
            _fail_result(),
            _ok_result(),
            _ok_result(),
        ]
        # two separate temp dirs
        mock_all["mkdtemp"].side_effect = [
            "/tmp/hyperframes_test",
            "/tmp/ffmpeg_test",
        ]

        output = str(tmp_path / "output.mp4")
        result = HyperFramesVideoEngine().render(sample_assets, output)

        assert result == os.path.abspath(output)
        assert mock_all["run"].call_count == 3

    def test_fallback_builds_correct_ffmpeg_command(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """The FFmpeg slideshow command uses the expected arguments."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(x)
        mock_all["run"].side_effect = [
            _fail_result(),
            _ok_result(),
            _ok_result(),
        ]
        mock_all["mkdtemp"].side_effect = [
            "/tmp/hyperframes_test",
            "/tmp/ffmpeg_test",
        ]

        output = str(tmp_path / "output.mp4")
        HyperFramesVideoEngine().render(sample_assets, output)

        # The second subprocess call should be the ffmpeg slideshow step 1
        step1_call_args = mock_all["run"].call_args_list[1]  # second call
        step1_cmd = step1_call_args[0][0]  # positional arg 0 = cmd list
        assert step1_cmd[0] == "ffmpeg"
        assert "-framerate" in step1_cmd
        assert "-pattern_type" in step1_cmd
        assert "glob" in step1_cmd

        # The third subprocess call should be the audio mux step 2
        step2_call_args = mock_all["run"].call_args_list[2]  # third call
        step2_cmd = step2_call_args[0][0]
        assert step2_cmd[0] == "ffmpeg"
        assert "-i" in step2_cmd
        # second -i is the audio file
        assert "/fake/audio.mp3" in step2_cmd

    def test_fallback_both_fail(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Hyperframes fails AND FFmpeg fails → ``EngineExecutionError``."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(x)
        # Everything fails
        mock_all["run"].side_effect = [
            _fail_result(),  # hyperframes
            _fail_result(),  # ffmpeg step 1
        ]

        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError) as excinfo:
            HyperFramesVideoEngine().render(sample_assets, output)

        error_msg = str(excinfo.value)
        assert "FFmpeg" in error_msg or "ffmpeg" in error_msg

    def test_fallback_no_audio_uses_move(
        self,
        mock_all: dict[str, MagicMock],
        minimal_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Without audio the ffmpeg fallback uses ``shutil.move`` instead of
        a second subprocess call."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": None,
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(x)
        # No audio file exists
        mock_all["isfile"].return_value = False

        output = str(tmp_path / "output.mp4")
        result = HyperFramesVideoEngine().render(minimal_assets, output)

        assert result == os.path.abspath(output)
        # Only one ffmpeg subprocess call (step 1 — slideshow only)
        mock_all["run"].assert_called_once()
        # ``shutil.move`` was used to place the temp video
        mock_all["move"].assert_called_once()

    def test_fallback_temp_cleanup_for_both_dirs(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Both temp directories are cleaned up after a succesful fallback."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(x)
        mock_all["run"].side_effect = [
            _fail_result(),
            _ok_result(),
            _ok_result(),
        ]
        mock_all["mkdtemp"].side_effect = [
            "/tmp/hyperframes_test",
            "/tmp/ffmpeg_test",
        ]

        output = str(tmp_path / "output.mp4")
        HyperFramesVideoEngine().render(sample_assets, output)

        mock_all["rmtree"].assert_any_call(
            "/tmp/hyperframes_test",
            ignore_errors=True,
        )
        mock_all["rmtree"].assert_any_call(
            "/tmp/ffmpeg_test",
            ignore_errors=True,
        )
        assert mock_all["rmtree"].call_count == 2


# ===================================================================
# render — error cases
# ===================================================================


class TestRenderErrors:
    """:meth:`render` expected-failure scenarios."""

    def test_no_tools_available(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Neither binary on PATH → ``EngineExecutionError``."""
        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError) as excinfo:
            HyperFramesVideoEngine().render(sample_assets, output)

        error_msg = str(excinfo.value)
        assert "hyperframes" in error_msg
        assert "ffmpeg" in error_msg

    def test_empty_images_list(
        self,
        mock_all: dict[str, MagicMock],
        tmp_path: Any,
    ) -> None:
        """Empty ``assets["images"]`` → ``EngineExecutionError``."""
        assets: dict[str, Any] = {"images": [], "content": "Nope."}
        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError) as excinfo:
            HyperFramesVideoEngine().render(assets, output)

        error_msg = str(excinfo.value)
        assert "no images" in error_msg

    def test_empty_images_list_with_tools(
        self,
        mock_all: dict[str, MagicMock],
        tmp_path: Any,
    ) -> None:
        """Empty images list is checked *before* tool availability."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)
        assets: dict[str, Any] = {"images": [], "content": "Nope."}
        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError) as excinfo:
            HyperFramesVideoEngine().render(assets, output)

        error_msg = str(excinfo.value)
        assert "no images" in error_msg
        # Internal methods should NOT have been reached
        mock_all["run"].assert_not_called()


# ===================================================================
# Temp directory cleanup (focused)
# ===================================================================


class TestTempCleanup:
    """:meth:`shutil.rmtree` behaviour in edge cases."""

    def test_no_temp_dir_when_no_tools(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """When no tool is found, ``_render_with_*`` is never entered, so
        ``rmtree`` is never called (``render()`` itself doesn't create
        a temp dir)."""
        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError):
            HyperFramesVideoEngine().render(sample_assets, output)

        mock_all["rmtree"].assert_not_called()

    def test_ffmpeg_cleanup_on_timeout(
        self,
        mock_all: dict[str, MagicMock],
        minimal_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """When FFmpeg subprocess times out, the temp dir is still cleaned."""
        from subprocess import TimeoutExpired

        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": None,
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(x)
        mock_all["run"].side_effect = TimeoutExpired(cmd="ffmpeg", timeout=300)

        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError):
            HyperFramesVideoEngine().render(minimal_assets, output)

        mock_all["rmtree"].assert_called_once_with(
            mock_all["mkdtemp"].return_value,
            ignore_errors=True,
        )

    def test_hyperframes_cleanup_on_unexpected_exception(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """An unexpected exception in ``_render_with_hyperframes`` is wrapped
        in ``EngineExecutionError`` and the temp dir is still cleaned."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
            "ffmpeg": None,
        }.get(x)
        # ``os.makedirs`` raises an unexpected ``OSError``
        mock_all["makedirs"].side_effect = OSError("permission denied")

        output = str(tmp_path / "output.mp4")
        with pytest.raises(EngineExecutionError):
            HyperFramesVideoEngine().render(sample_assets, output)

        mock_all["rmtree"].assert_called_once_with(
            "/tmp/hyperframes_test",
            ignore_errors=True,
        )


# ===================================================================
# Custom configuration
# ===================================================================


class TestRenderConfiguration:
    """Custom engine config values are propagated to subprocess."""

    def test_custom_timeout_and_quality(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """> ``timeout`` and ``quality`` from ``engine_config`` are used."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)

        engine = HyperFramesVideoEngine(
            engine_config={"timeout": 600, "quality": "low"},
        )
        output = str(tmp_path / "output.mp4")
        engine.render(sample_assets, output)

        mock_all["run"].assert_called_once_with(
            [
                "hyperframes",
                "render",
                "--quality", "low",
                "--assets", "/tmp/hyperframes_test",
                "--output", output,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
