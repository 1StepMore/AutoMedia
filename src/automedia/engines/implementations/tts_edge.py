"""Edge-TTS engine — wraps the ``edge-tts`` CLI for text-to-speech synthesis.

Provides:
    - :class:`EdgeTTSEngine` — a :class:`BaseTTSEngine` implementation that
      shells out to the ``edge-tts`` command-line tool.

Usage::

    engine = EdgeTTSEngine()
    path = engine.synthesize("Hello world", voice="zh-CN-YunxiNeural", output_path="/tmp/out.mp3")
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import ClassVar, cast

from typing_extensions import override

from automedia.engines.base import BaseTTSEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VOICE: str = "zh-CN-YunxiNeural"
"""Default Edge-TTS voice used when neither the *voice* parameter nor the
engine configuration provides one."""


# ---------------------------------------------------------------------------
# EdgeTTSEngine
# ---------------------------------------------------------------------------


class EdgeTTSEngine(BaseTTSEngine):
    """Text-to-Speech engine backed by the ``edge-tts`` CLI.

    Attributes
    ----------
    engine_name : str
        Registration key in the :class:`EngineRegistry`.
    modality : str
        Modality grouping (``"tts"``).
    """

    engine_name: ClassVar[str] = "edge-tts"
    modality: ClassVar[str] = "tts"

    # ------------------------------------------------------------------
    # Dependency check
    # ------------------------------------------------------------------

    @override
    def check_available(self) -> tuple[bool, str]:
        """Verify that the ``edge-tts`` CLI is on ``$PATH``.

        Returns
        -------
        tuple[bool, str]
            ``(True, ...)`` if ``edge-tts`` is found, otherwise
            ``(False, ...)`` with a diagnostic message.
        """
        if shutil.which("edge-tts") is not None:
            return True, "edge-tts CLI found on PATH"
        return False, "edge-tts CLI not found on PATH"

    # ------------------------------------------------------------------
    # TTS synthesis
    # ------------------------------------------------------------------

    @override
    def synthesize(
        self,
        text: str,
        voice: str = "",
        output_path: str = "",
    ) -> str:
        """Generate TTS audio via the ``edge-tts`` CLI.

        Parameters
        ----------
        text:
            Text to synthesize.  Must be non-empty.
        voice:
            Edge-TTS voice identifier (e.g. ``"zh-CN-YunxiNeural"``).
            Falls back to ``self._config.get("voice", DEFAULT_VOICE)``
            when empty.
        output_path:
            Destination path for the generated audio file.  Must be
            non-empty.

        Returns
        -------
        str
            Absolute path to the generated audio file.

        Raises
        ------
        ValueError
            If *text* or *output_path* is empty.
        subprocess.CalledProcessError
            If the ``edge-tts`` command exits with a non-zero status.
        """
        if not text:
            raise ValueError("text must not be empty")

        if not output_path:
            raise ValueError("output_path must not be empty")

        # Resolve voice: parameter → engine config → built-in default
        if not voice:
            voice = cast(str, self._config.get("voice", DEFAULT_VOICE))

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        cmd = [
            "edge-tts",
            "--voice",
            voice,
            "--text",
            text,
            "--write-media",
            output_path,
        ]

        logger.info("edge-tts: generating TTS → %s", output_path)
        result = subprocess.run(  # noqa: S603 — trusted internal command
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("edge-tts failed (rc=%d): %s", result.returncode, result.stderr)
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                result.stdout,
                result.stderr,  # type: ignore[arg-type]
            )

        logger.info("edge-tts: wrote %s", output_path)
        return os.path.abspath(output_path)
