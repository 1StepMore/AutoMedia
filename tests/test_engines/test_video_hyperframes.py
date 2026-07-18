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
from unittest.mock import ANY, MagicMock, call, patch

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


def _extract_env_from_run(mock_run: MagicMock) -> dict[str, str] | None:
    """Extract the ``env`` kwarg from a ``subprocess.run`` call."""
    call_kwargs = mock_run.call_args[1]
    return call_kwargs.get("env")


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
        patch(
            "automedia.engines.implementations.video_hyperframes.os.listdir",
        ) as m_listdir,
    ):
        # --- defaults ---
        m_which.return_value = None
        m_run.return_value = _ok_result()
        m_mkdtemp.return_value = "/tmp/hyperframes_test"
        m_isfile.return_value = True
        m_isdir.return_value = True
        m_listdir.return_value = []

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
            "listdir": m_listdir,
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
            env=ANY,
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

        # template directory — individual items copied to temp root
        mock_all["listdir"].assert_called_once_with("/fake/template")

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
        with patch.object(
            HyperFramesVideoEngine,
            "_provision_default_hyperframes_project",
        ) as m_provision:
            HyperFramesVideoEngine().render(minimal_assets, output)

        # Only image copies should have happened
        copy_calls = mock_all["copy2"].call_args_list
        assert len(copy_calls) == 1  # only the image
        assert copy_calls[0] == call(
            "/fake/img1.png",
            "/tmp/hyperframes_test/images",
        )
        # Default provisioning was called (no template_dir in minimal_assets)
        m_provision.assert_called_once()

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
            env=ANY,
        )


# ===================================================================
# render — HYPERFRAMES_BROWSER_PATH env var
# ===================================================================


class TestRenderChromePath:
    """HYPERFRAMES_BROWSER_PATH env var is set from config."""

    def test_sets_hyperframes_browser_path(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """chrome_path in config → HYPERFRAMES_BROWSER_PATH set in subprocess env."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)
        engine = HyperFramesVideoEngine(
            engine_config={"chrome_path": "/usr/bin/google-chrome"},
        )
        output = str(tmp_path / "output.mp4")
        engine.render(sample_assets, output)

        env = _extract_env_from_run(mock_all["run"])
        assert env is not None
        assert env.get("HYPERFRAMES_BROWSER_PATH") == "/usr/bin/google-chrome"

    def test_skips_when_null(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
        monkeypatch: Any,
    ) -> None:
        """chrome_path=None → HYPERFRAMES_BROWSER_PATH not in env."""
        monkeypatch.delenv("HYPERFRAMES_BROWSER_PATH", raising=False)
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)
        engine = HyperFramesVideoEngine(
            engine_config={"chrome_path": None},
        )
        output = str(tmp_path / "output.mp4")
        engine.render(sample_assets, output)

        env = _extract_env_from_run(mock_all["run"])
        assert env is not None
        assert "HYPERFRAMES_BROWSER_PATH" not in env

    def test_skips_when_path_not_found(
        self,
        mock_all: dict[str, MagicMock],
        sample_assets: dict[str, Any],
        tmp_path: Any,
        monkeypatch: Any,
    ) -> None:
        """chrome_path points to non-existent file → env var not set."""
        monkeypatch.delenv("HYPERFRAMES_BROWSER_PATH", raising=False)
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)
        # Mock os.path.isfile to return False for the chrome path
        mock_all["isfile"].side_effect = lambda p: (
            p != "/usr/bin/google-chrome"
        )

        engine = HyperFramesVideoEngine(
            engine_config={"chrome_path": "/usr/bin/google-chrome"},
        )
        output = str(tmp_path / "output.mp4")
        engine.render(sample_assets, output)

        env = _extract_env_from_run(mock_all["run"])
        assert env is not None
        assert "HYPERFRAMES_BROWSER_PATH" not in env


# ===================================================================
# Default template provisioning
# ===================================================================


class TestDefaultTemplateProvisioning:
    """_provision_default_hyperframes_project and _get_audio_duration."""

    # ------------------------------------------------------------------
    # _get_audio_duration unit tests
    # ------------------------------------------------------------------

    @patch("automedia.engines.implementations.video_hyperframes.os.path.isfile")
    @patch("automedia.engines.implementations.video_hyperframes.shutil.which")
    @patch("automedia.engines.implementations.video_hyperframes.subprocess.run")
    def test_get_audio_duration_success(
        self, m_run: MagicMock, m_which: MagicMock, m_isfile: MagicMock,
    ) -> None:
        """> ``ffprobe`` returns duration → floats."""
        m_isfile.return_value = True
        m_which.return_value = "/usr/bin/ffprobe"
        m_run.return_value = MagicMock(returncode=0, stdout="30.5\n", stderr="")

        result = HyperFramesVideoEngine._get_audio_duration("/fake/test.mp3")
        assert result == 30.5

    @patch("automedia.engines.implementations.video_hyperframes.shutil.which")
    def test_get_audio_duration_ffprobe_missing(
        self, m_which: MagicMock,
    ) -> None:
        """> ``ffprobe`` not on ``PATH`` → ``None``."""
        m_which.return_value = None
        result = HyperFramesVideoEngine._get_audio_duration("/fake/test.mp3")
        assert result is None

    @patch("automedia.engines.implementations.video_hyperframes.shutil.which")
    @patch("automedia.engines.implementations.video_hyperframes.os.path.isfile")
    def test_get_audio_duration_file_missing(
        self, m_isfile: MagicMock, m_which: MagicMock,
    ) -> None:
        """> Audio file not found → ``None``."""
        m_which.return_value = "/usr/bin/ffprobe"
        m_isfile.return_value = False
        result = HyperFramesVideoEngine._get_audio_duration("/fake/nope.mp3")
        assert result is None

    @patch("automedia.engines.implementations.video_hyperframes.os.path.isfile")
    @patch("automedia.engines.implementations.video_hyperframes.shutil.which")
    @patch("automedia.engines.implementations.video_hyperframes.subprocess.run")
    def test_get_audio_duration_timeout(
        self, m_run: MagicMock, m_which: MagicMock, m_isfile: MagicMock,
    ) -> None:
        """> ``ffprobe`` times out → ``None``."""
        from subprocess import TimeoutExpired

        m_isfile.return_value = True
        m_which.return_value = "/usr/bin/ffprobe"
        m_run.side_effect = TimeoutExpired(cmd="ffprobe", timeout=15)
        result = HyperFramesVideoEngine._get_audio_duration("/fake/test.mp3")
        assert result is None

    # ------------------------------------------------------------------
    # Default template provisioning — integration style
    # ------------------------------------------------------------------

    def test_provision_creates_expected_file_layout(
        self, tmp_path: Any,
    ) -> None:
        """> Full provisioning creates ``hyperframes.json``, ``index.html``,
        ``meta.json``, and scene compositions."""
        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        audio = tmp_path / "narration.mp3"
        img1.write_text("fake-png")
        img2.write_text("fake-png")
        audio.write_text("fake-mp3")

        project_dir = tmp_path / "hf_project"
        project_dir.mkdir(parents=True, exist_ok=True)
        assets: dict[str, Any] = {
            "images": [str(img1), str(img2)],
            "audio": str(audio),
            "content": "Test content for the video.",
        }

        with (
            patch(
                "automedia.engines.implementations.video_hyperframes.shutil.which",
            ) as m_which,
            patch(
                "automedia.engines.implementations.video_hyperframes.subprocess.run",
            ) as m_run,
        ):
            m_which.side_effect = lambda x: {  # type: ignore[return-value]
                "ffprobe": "/usr/bin/ffprobe",
            }.get(x)
            m_run.return_value = MagicMock(returncode=0, stdout="20.0\n", stderr="")

            engine = HyperFramesVideoEngine()
            engine._provision_default_hyperframes_project(
                str(project_dir), assets,
            )

        # Static files
        assert (project_dir / "hyperframes.json").is_file()
        assert (project_dir / "package.json").is_file()

        # Rendered files
        assert (project_dir / "index.html").is_file()
        assert (project_dir / "meta.json").is_file()

        # Scene compositions (2 images → 2 scenes)
        assert (project_dir / "compositions").is_dir()
        assert (project_dir / "compositions" / "01-scene.html").is_file()
        assert (project_dir / "compositions" / "02-scene.html").is_file()
        assert not (project_dir / "compositions" / "03-scene.html").exists()

        # Audio asset
        assert (project_dir / "assets" / "audio").is_dir()

    def test_provision_rendered_content_is_valid(
        self, tmp_path: Any,
    ) -> None:
        """> Rendered ``index.html`` contains valid scene references and
        ``meta.json`` is parseable with correct scene metadata."""
        import json

        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        audio = tmp_path / "voice.mp3"
        img1.write_text("fake")
        img2.write_text("fake")
        audio.write_text("fake")

        project_dir = tmp_path / "hf_project"
        project_dir.mkdir(parents=True, exist_ok=True)
        assets: dict[str, Any] = {
            "images": [str(img1), str(img2)],
            "audio": str(audio),
            "content": "Hello world.",
        }

        with (
            patch(
                "automedia.engines.implementations.video_hyperframes.shutil.which",
            ) as m_which,
            patch(
                "automedia.engines.implementations.video_hyperframes.subprocess.run",
            ) as m_run,
        ):
            m_which.side_effect = lambda x: {  # type: ignore[return-value]
                "ffprobe": "/usr/bin/ffprobe",
            }.get(x)
            m_run.return_value = MagicMock(returncode=0, stdout="20.0\n", stderr="")

            engine = HyperFramesVideoEngine()
            engine._provision_default_hyperframes_project(
                str(project_dir), assets,
            )

        # index.html has expected structure
        index_html = (project_dir / "index.html").read_text(encoding="utf-8")
        assert "<!doctype html>" in index_html.lower()
        assert "scene-1" in index_html
        assert "scene-2" in index_html
        assert "assets/audio/voice.mp3" in index_html
        assert 'data-duration="20.0"' in index_html

        # meta.json is valid and has correct scene count
        meta = json.loads((project_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["meta"]["targetDuration"] == 20.0
        assert len(meta["scenes"]) == 2
        assert meta["scenes"][0]["id"] == "scene-1"
        assert meta["scenes"][1]["id"] == "scene-2"

        # Scene compositions have correct IDs and GSAP timelines
        scene1 = (project_dir / "compositions" / "01-scene.html").read_text(
            encoding="utf-8",
        )
        assert 'data-composition-id="scene-1"' in scene1
        assert "gsap.timeline({ paused: true })" in scene1
        assert "Hello world." in scene1

        scene2 = (project_dir / "compositions" / "02-scene.html").read_text(
            encoding="utf-8",
        )
        assert 'data-composition-id="scene-2"' in scene2

    def test_provision_single_image(
        self, tmp_path: Any,
    ) -> None:
        """> 1 image → 1 scene composition (no extra files)."""
        img = tmp_path / "img.png"
        audio = tmp_path / "audio.mp3"
        img.write_text("fake")
        audio.write_text("fake")

        project_dir = tmp_path / "hf_project"
        project_dir.mkdir(parents=True, exist_ok=True)
        assets: dict[str, Any] = {
            "images": [str(img)],
            "audio": str(audio),
            "content": "Single scene.",
        }

        with (
            patch(
                "automedia.engines.implementations.video_hyperframes.shutil.which",
            ) as m_which,
            patch(
                "automedia.engines.implementations.video_hyperframes.subprocess.run",
            ) as m_run,
        ):
            m_which.side_effect = lambda x: {  # type: ignore[return-value]
                "ffprobe": "/usr/bin/ffprobe",
            }.get(x)
            m_run.return_value = MagicMock(returncode=0, stdout="10.0\n", stderr="")

            engine = HyperFramesVideoEngine()
            engine._provision_default_hyperframes_project(
                str(project_dir), assets,
            )

        assert (project_dir / "compositions" / "01-scene.html").is_file()
        assert not (project_dir / "compositions" / "02-scene.html").exists()

    def test_provision_no_audio_uses_default_duration(
        self, tmp_path: Any,
    ) -> None:
        """> No audio → each scene gets ``_DEFAULT_SCENE_DURATION`` seconds."""
        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        img1.write_text("fake")
        img2.write_text("fake")

        project_dir = tmp_path / "hf_project"
        project_dir.mkdir(parents=True, exist_ok=True)
        assets: dict[str, Any] = {
            "images": [str(img1), str(img2)],
            "content": "No audio test.",
        }

        engine = HyperFramesVideoEngine()
        engine._provision_default_hyperframes_project(str(project_dir), assets)

        # Without audio → 2 scenes × 10s default = 20s
        import json

        meta = json.loads((project_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["meta"]["targetDuration"] == 20.0
        assert meta["scenes"][0]["duration"] == 10.0
        assert meta["scenes"][1]["duration"] == 10.0

        # No assets/audio directory created
        assert not (project_dir / "assets" / "audio").exists()

    # ------------------------------------------------------------------
    # Integration: render() with template_dir="" triggers default provisioning
    # ------------------------------------------------------------------

    def test_default_templates_used_when_template_dir_empty(
        self, mock_all: dict[str, MagicMock], tmp_path: Any,
    ) -> None:
        """> ``template_dir=""`` → ``_provision_default_hyperframes_project`` called."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)
        # ``isdir`` returns ``False`` for template_dir → defaults path
        mock_all["isdir"].return_value = False

        assets: dict[str, Any] = {
            "images": ["/fake/img1.png", "/fake/img2.png"],
            "audio": "/fake/audio.mp3",
            "content": "Test",
            "template_dir": "",
        }
        output = str(tmp_path / "out.mp4")

        with patch.object(
            HyperFramesVideoEngine,
            "_provision_default_hyperframes_project",
        ) as m_provision:
            engine = HyperFramesVideoEngine()
            engine.render(assets, output)

            m_provision.assert_called_once()

    def test_user_template_dir_copied_to_root(
        self, mock_all: dict[str, MagicMock], tmp_path: Any,
    ) -> None:
        """> User ``template_dir`` → files copied to temp root,
        ``_provision_default_hyperframes_project`` NOT called."""
        mock_all["which"].side_effect = lambda x: {  # type: ignore[return-value]
            "hyperframes": "/usr/bin/hyperframes",
        }.get(x)
        # ``isdir`` returns ``True`` for template_dir → user templates path
        mock_all["isdir"].return_value = True
        # Simulate files in the template directory
        mock_all["listdir"].return_value = ["hyperframes.json", "index.html"]

        assets: dict[str, Any] = {
            "images": ["/fake/img1.png"],
            "audio": "/fake/audio.mp3",
            "content": "Test",
            "template_dir": "/fake/template",
        }
        output = str(tmp_path / "out.mp4")

        with patch.object(
            HyperFramesVideoEngine,
            "_provision_default_hyperframes_project",
        ) as m_provision:
            engine = HyperFramesVideoEngine()
            engine.render(assets, output)

            m_provision.assert_not_called()

        # Template files copied to temp_dir root (not /template/ subdir)
        copy_calls = mock_all["copy2"].call_args_list
        root_copies = [
            c for c in copy_calls
            if c[0][1] == "/tmp/hyperframes_test"
        ]
        assert len(root_copies) >= 1, (
            f"No files copied to temp root: {copy_calls}"
        )
