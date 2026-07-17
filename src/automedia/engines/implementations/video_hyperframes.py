"""HyperFrames video rendering engine with FFmpeg fallback.

Renders a video from the provided assets (images, audio, subtitles, template
directory, and content text) using either the ``hyperframes`` CLI tool or,
as a fallback, an ``ffmpeg`` slideshow pipeline.

Class
-----
HyperFramesVideoEngine
    Concrete :class:`~automedia.engines.base.BaseVideoEngine` subclass that
    auto-registers with ``engine_name="hyperframes"`` and ``modality="video"``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, ClassVar

from automedia.engines.base import BaseVideoEngine
from automedia.engines.errors import EngineExecutionError

logger = logging.getLogger(__name__)


class HyperFramesVideoEngine(BaseVideoEngine):
    """Render a video from images, audio, and subtitles.

    **Primary path** — ``hyperframes`` CLI:

    1. Copy all assets into a temporary working directory.
    2. Invoke ``hyperframes render --quality <quality> --assets <dir> --output <path>``.
    3. On success return ``output_path``.
    4. On failure, if ``ffmpeg`` is available, fall back to the FFmpeg
       slideshow path.

    **Fallback path** — ``ffmpeg`` slideshow:

    1. Build a slideshow video from the image sequence.
    2. Mux the audio track onto the result.
    3. Write the final file to ``output_path``.

    **When both tools are absent**, :meth:`check_available` returns
    ``(False, ...)``.  If the engine is used anyway, :meth:`render` raises
    :class:`EngineExecutionError`.
    """

    engine_name: ClassVar[str] = "hyperframes"
    modality: ClassVar[str] = "video"

    # ------------------------------------------------------------------
    # Constants for the FFmpeg fallback slideshow pipeline
    # ------------------------------------------------------------------

    _FALLBACK_FRAMERATE: float = 0.5
    """Input framerate (images per second) for the slideshow."""

    _OUTPUT_FRAMERATE: int = 30
    """Output video framerate after encoding."""

    _VIDEO_CODEC: str = "libx264"
    """Video codec used by the FFmpeg fallback."""

    # ------------------------------------------------------------------
    # Dependency check
    # ------------------------------------------------------------------

    def check_available(self) -> tuple[bool, str]:
        """Verify that at least one of ``hyperframes`` or ``ffmpeg`` is on ``PATH``.

        Returns
        -------
        tuple[bool, str]
            ``(True, ...)`` if either tool is found; ``(False, ...)`` only
            when neither is available.
        """
        hyperframes_path: str | None = shutil.which("hyperframes")
        ffmpeg_path: str | None = shutil.which("ffmpeg")

        if hyperframes_path:
            return (True, f"hyperframes found at {hyperframes_path}")

        if ffmpeg_path:
            return (True, f"hyperframes not found; ffmpeg fallback at {ffmpeg_path}")

        return (
            False,
            "Neither 'hyperframes' nor 'ffmpeg' found on PATH. "
            "Install hyperframes (npm/pip) or ffmpeg to use this engine.",
        )

    # ------------------------------------------------------------------
    # Render — primary hyperframes path → FFmpeg fallback
    # ------------------------------------------------------------------

    def render(self, assets: dict[str, Any], output_path: str) -> str:
        """Render a video from *assets* and write it to *output_path*.

        Parameters
        ----------
        assets:
            Dictionary with the following keys:

            - ``images`` (:class:`list[str]`): Paths to image files for video
              frames.  **Must not be empty.**
            - ``audio`` (:class:`str`): Path to the audio track file.
            - ``subtitles`` (:class:`str`): Path to the subtitle file
              (SRT or ASS).
            - ``template_dir`` (:class:`str`): Path to the video template
              directory.
            - ``content`` (:class:`str`): The rendered text content for
              overlays.

        output_path:
            Path where the rendered video file should be written.

        Returns
        -------
        str
            The absolute path to the rendered video (same as *output_path*).

        Raises
        ------
        EngineExecutionError
            - If ``assets["images"]`` is empty.
            - If the primary ``hyperframes`` call fails and ``ffmpeg`` is not
              available for the fallback.
            - If the FFmpeg fallback itself fails.
        """
        images: list[str] = assets.get("images", [])

        if not images:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details="Cannot render video: no images provided in assets.",
            )

        # Try the primary path first
        hyperframes_path: str | None = shutil.which("hyperframes")
        if hyperframes_path:
            try:
                return self._render_with_hyperframes(assets, output_path)
            except EngineExecutionError:
                logger.warning(
                    "hyperframes render failed; checking for ffmpeg fallback."
                )

        # Fallback: FFmpeg slideshow
        ffmpeg_path: str | None = shutil.which("ffmpeg")
        if ffmpeg_path:
            return self._render_with_ffmpeg(assets, output_path)

        # Neither worked and no fallback available
        raise EngineExecutionError(
            engine_name=self.engine_name,
            details=(
                "hyperframes CLI failed and 'ffmpeg' is not available on PATH. "
                "Install ffmpeg for fallback rendering, or fix the hyperframes "
                "invocation."
            ),
        )

    # ------------------------------------------------------------------
    # Primary path — HyperFrames CLI
    # ------------------------------------------------------------------

    def _render_with_hyperframes(
        self, assets: dict[str, Any], output_path: str
    ) -> str:
        """Render via ``hyperframes`` CLI using a temporary asset directory.

        Parameters
        ----------
        assets:
            Asset dictionary (see :meth:`render`).
        output_path:
            Final output path for the rendered video.

        Returns
        -------
        str
            The absolute, resolved path to the rendered video.

        Raises
        ------
        EngineExecutionError
            If the ``hyperframes`` subprocess fails or times out.
        """
        temp_dir: str | None = None
        timeout: int = self._config.get("timeout", 300)
        try:
            temp_dir = tempfile.mkdtemp(prefix="hyperframes_")

            # Copy images into the temp directory
            images_dir: str = os.path.join(temp_dir, "images")
            os.makedirs(images_dir, exist_ok=True)
            for img_path in assets.get("images", []):
                shutil.copy2(img_path, images_dir)

            # Copy audio if provided
            audio_path: str | None = assets.get("audio")
            if audio_path and os.path.isfile(audio_path):
                shutil.copy2(audio_path, temp_dir)

            # Copy subtitles if provided
            subs_path: str | None = assets.get("subtitles")
            if subs_path and os.path.isfile(subs_path):
                shutil.copy2(subs_path, temp_dir)

            # Copy template directory if provided
            template_dir: str | None = assets.get("template_dir")
            if template_dir and os.path.isdir(template_dir):
                dest_template: str = os.path.join(temp_dir, "template")
                shutil.copytree(template_dir, dest_template, dirs_exist_ok=True)

            # Build the command
            quality: str = self._config.get("quality", "high")

            cmd: list[str] = [
                "hyperframes",
                "render",
                "--quality", quality,
                "--assets", temp_dir,
                "--output", output_path,
            ]

            logger.info(
                "Running hyperframes render (quality=%s, output=%s, assets=%s)",
                quality,
                output_path,
                temp_dir,
            )

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                raise EngineExecutionError(
                    engine_name=self.engine_name,
                    details=(
                        f"hyperframes render failed (exit code {result.returncode}).\n"
                        f"stdout: {result.stdout}\n"
                        f"stderr: {result.stderr}"
                    ),
                )

            logger.info("hyperframes render succeeded (%s)", output_path)

            return os.path.abspath(output_path)

        except subprocess.TimeoutExpired:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(
                    f"hyperframes render timed out after {timeout} seconds."
                ),
            )
        except EngineExecutionError:
            raise
        except Exception as exc:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=f"Unexpected error during hyperframes render: {exc}",
                cause=exc,
            )
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Fallback path — FFmpeg slideshow
    # ------------------------------------------------------------------

    def _render_with_ffmpeg(
        self, assets: dict[str, Any], output_path: str
    ) -> str:
        """Render a video via an ``ffmpeg`` slideshow pipeline.

        Two-step process:

        1. Build an intermediate video from the image sequence.
        2. Mux the audio track onto the final output.

        Parameters
        ----------
        assets:
            Asset dictionary (see :meth:`render`).
        output_path:
            Final output path for the rendered video.

        Returns
        -------
        str
            The absolute, resolved path to the rendered video.

        Raises
        ------
        EngineExecutionError
            If either FFmpeg subprocess fails or times out.
        """
        temp_dir: str | None = None
        timeout: int = self._config.get("timeout", 300)
        try:
            temp_dir = tempfile.mkdtemp(prefix="ffmpeg_slideshow_")
            temp_video: str = os.path.join(temp_dir, "temp_video.mp4")

            images: list[str] = assets.get("images", [])
            audio: str | None = assets.get("audio")
            fallback_framerate: float = self._FALLBACK_FRAMERATE
            output_framerate: int = self._OUTPUT_FRAMERATE
            video_codec: str = self._VIDEO_CODEC

            # Step 1: Build slideshow video from images
            # Use the first image's directory as the glob root
            images_dir: str = os.path.dirname(images[0]) if images else ""
            glob_pattern: str = os.path.join(images_dir, "*.png")

            # Determine the actual image extension from the first image
            first_img: str = images[0]
            img_ext: str = os.path.splitext(first_img)[1] or ".png"
            glob_pattern = os.path.join(images_dir, f"*{img_ext}")

            step1_cmd: list[str] = [
                "ffmpeg",
                "-y",
                "-framerate", str(fallback_framerate),
                "-pattern_type", "glob",
                "-i", glob_pattern,
                "-c:v", video_codec,
                "-r", str(output_framerate),
                "-pix_fmt", "yuv420p",
                temp_video,
            ]

            logger.info(
                "Running FFmpeg slideshow (step 1/2) (glob=%s, temp=%s)",
                glob_pattern,
                temp_video,
            )

            result1: subprocess.CompletedProcess[str] = subprocess.run(
                step1_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result1.returncode != 0:
                raise EngineExecutionError(
                    engine_name=self.engine_name,
                    details=(
                        f"FFmpeg slideshow step 1 (build video) failed "
                        f"(exit code {result1.returncode}).\n"
                        f"stdout: {result1.stdout}\n"
                        f"stderr: {result1.stderr}"
                    ),
                )

            # Step 2: Mux audio onto the video (if audio is provided)
            if audio and os.path.isfile(audio):
                step2_cmd: list[str] = [
                    "ffmpeg",
                    "-y",
                    "-i", temp_video,
                    "-i", audio,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path,
                ]

                logger.info(
                    "Running FFmpeg audio mux (step 2/2) (audio=%s, output=%s)",
                    audio,
                    output_path,
                )

                result2: subprocess.CompletedProcess[str] = subprocess.run(
                    step2_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if result2.returncode != 0:
                    raise EngineExecutionError(
                        engine_name=self.engine_name,
                        details=(
                            f"FFmpeg audio mux step 2 failed "
                            f"(exit code {result2.returncode}).\n"
                            f"stdout: {result2.stdout}\n"
                            f"stderr: {result2.stderr}"
                        ),
                    )
            else:
                # No audio track — just move the temp video to the output path
                logger.info("No audio track provided; skipping audio mux step.")
                shutil.move(temp_video, output_path)

            logger.info("FFmpeg slideshow render succeeded (%s)", output_path)
            return os.path.abspath(output_path)

        except subprocess.TimeoutExpired:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(
                    f"FFmpeg slideshow render timed out after {timeout} seconds."
                ),
            )
        except EngineExecutionError:
            raise
        except Exception as exc:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=f"Unexpected error during FFmpeg slideshow render: {exc}",
                cause=exc,
            )
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
