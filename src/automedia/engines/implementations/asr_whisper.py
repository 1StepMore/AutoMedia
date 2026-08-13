"""Whisper ASR engine — wraps the whisper CLI for speech-to-text transcription.

Provides:
    - :class:`WhisperASREngine` — shells out to the ``whisper`` command,
      parses the JSON output file produced next to the input audio, and
      falls back to stdout JSON parsing.

Auto-registers in :class:`EngineRegistry` via ``__init_subclass__``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from automedia.engines.base import BaseASREngine

logger = logging.getLogger(__name__)


class WhisperASREngine(BaseASREngine):
    """Speech-to-text via the Whisper CLI.

    Shells out to the ``whisper`` command-line tool and parses the JSON
    output file it writes next to the input audio.
    """

    engine_name: ClassVar[str] = "whisper"
    modality: ClassVar[str] = "asr"

    # ------------------------------------------------------------------
    # Required: availability check
    # ------------------------------------------------------------------

    def check_available(self) -> tuple[bool, str]:
        """Verify that the ``whisper`` CLI binary is on ``$PATH``.

        Returns:
            A tuple of ``(available, message)``.
        """
        if shutil.which("whisper") is not None:
            return True, "whisper CLI found on PATH"
        return False, "whisper CLI not found on PATH"

    # ------------------------------------------------------------------
    # Required: transcribe
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe *audio_path* via the Whisper CLI.

        Parameters
        ----------
        audio_path:
            Path to the audio file (MP3, WAV, etc.).
        language:
            Language code for Whisper (e.g. ``"zh"``, ``"en"``).
            When provided, this overrides any default set in
            ``self._config["language"]``.

        Returns
        -------
        dict
            Whisper JSON output with at least the keys:
            - ``text`` (str): Full transcription text.
            - ``segments`` (list[dict]): Per-segment data with ``start``,
              ``end``, and ``text`` keys.

        Raises
        ------
        FileNotFoundError
            If *audio_path* does not exist.
        subprocess.CalledProcessError
            If the whisper command exits with a non-zero status.
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"audio file not found: {audio_path}")

        # Resolve language: parameter > config > built-in default
        lang: str = language or self._config.get("language", "zh")

        # Resolve model: config override or built-in default
        model: str = self._config.get("model", "tiny")

        # Whisper writes output files next to the input file.
        audio_dir: str = os.path.dirname(os.path.abspath(audio_path))

        cmd: list[str] = [
            "whisper",
            audio_path,
            "--model",
            model,
            "--language",
            lang,
            "--output_format",
            "json",
            "--output_dir",
            audio_dir,
        ]

        logger.info(
            "whisper: transcribing %s (model=%s, language=%s)",
            audio_path,
            model,
            lang,
        )
        result = subprocess.run(  # noqa: S603 — trusted internal command
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            logger.error(
                "whisper failed (rc=%d): %s",
                result.returncode,
                result.stderr,
            )
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )

        # Whisper writes a .json file alongside the audio.
        audio_stem: str = Path(audio_path).stem
        json_path: str = os.path.join(audio_dir, f"{audio_stem}.json")

        if not os.path.isfile(json_path):
            logger.warning(
                "whisper JSON not found at %s, returning stdout parse",
                json_path,
            )
            # Fallback: try parsing stdout as JSON
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"text": result.stdout.strip(), "segments": []}

        with open(json_path, encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)

        logger.info(
            "whisper: transcribed %d segments",
            len(data.get("segments", [])),
        )
        return data
