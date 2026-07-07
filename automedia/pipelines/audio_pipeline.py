"""Audio pipeline — edge-tts TTS, Whisper ASR, SRT subtitle generation.

Provides:
    - :class:`AudioPipeline` — generates TTS audio via edge-tts, transcribes
      via Whisper, generates SRT subtitles, and proofreads SRT for brand name
      correctness.

Usage::

    pipeline = AudioPipeline()
    results = pipeline.generate_all("Hello world", voice="zh-CN-YunxiNeural", output_dir="/tmp/out")
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VOICE: str = "zh-CN-YunxiNeural"
DEFAULT_WHISPER_MODEL: str = "tiny"
DEFAULT_LANGUAGE: str = "zh"


# ---------------------------------------------------------------------------
# AudioPipeline
# ---------------------------------------------------------------------------


class AudioPipeline:
    """Audio production pipeline: TTS → ASR → SRT → proofread.

    Each method shells out to external CLI tools (edge-tts, whisper) via
    subprocess and produces files on disk.
    """

    # ------------------------------------------------------------------
    # TTS: edge-tts
    # ------------------------------------------------------------------

    def generate_tts(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        output_path: str = "",
    ) -> str:
        """Generate TTS audio via edge-tts CLI.

        Parameters
        ----------
        text:
            Text to synthesize.
        voice:
            Edge-TTS voice identifier (e.g. ``"zh-CN-YunxiNeural"``).
        output_path:
            Destination path for the generated MP3 file.

        Returns
        -------
        str
            Absolute path to the generated MP3 file.

        Raises
        ------
        subprocess.CalledProcessError
            If the edge-tts command fails.
        ValueError
            If *text* is empty.
        """
        if not text:
            raise ValueError("text must not be empty")

        if not output_path:
            raise ValueError("output_path must not be empty")

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        cmd = [
            "edge-tts",
            "--voice", voice,
            "--text", text,
            "--write-media", output_path,
        ]

        logger.info("edge-tts: generating TTS → %s", output_path)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("edge-tts failed (rc=%d): %s", result.returncode, result.stderr)
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )

        logger.info("edge-tts: wrote %s", output_path)
        return os.path.abspath(output_path)

    # ------------------------------------------------------------------
    # ASR: whisper
    # ------------------------------------------------------------------

    def transcribe_audio(
        self,
        audio_path: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> dict[str, Any]:
        """Transcribe audio via Whisper CLI and return structured result.

        Parameters
        ----------
        audio_path:
            Path to the audio file (MP3, WAV, etc.).
        language:
            Language code for Whisper (e.g. ``"zh"``, ``"en"``).

        Returns
        -------
        dict
            Whisper JSON output with at least the keys:
            - ``text``: str — full transcription text
            - ``segments``: list[dict] — per-segment data with ``start``,
              ``end``, and ``text`` fields.

        Raises
        ------
        subprocess.CalledProcessError
            If the whisper command fails.
        FileNotFoundError
            If *audio_path* does not exist.
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"audio file not found: {audio_path}")

        # Whisper writes output files next to the input file.
        audio_dir = os.path.dirname(os.path.abspath(audio_path))

        cmd = [
            "whisper",
            audio_path,
            "--model", DEFAULT_WHISPER_MODEL,
            "--language", language,
            "--output_format", "json",
            "--output_dir", audio_dir,
        ]

        logger.info("whisper: transcribing %s", audio_path)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            logger.error("whisper failed (rc=%d): %s", result.returncode, result.stderr)
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )

        # Whisper writes a .json file alongside the audio.
        audio_stem = Path(audio_path).stem
        json_path = os.path.join(audio_dir, f"{audio_stem}.json")

        if not os.path.isfile(json_path):
            logger.warning("whisper JSON not found at %s, returning stdout parse", json_path)
            # Fallback: try parsing stdout
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"text": result.stdout.strip(), "segments": []}

        with open(json_path, "r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)

        logger.info("whisper: transcribed %d segments", len(data.get("segments", [])))
        return data

    # ------------------------------------------------------------------
    # SRT generation
    # ------------------------------------------------------------------

    def generate_srt(
        self,
        transcription: dict[str, Any],
        output_path: str,
    ) -> str:
        """Generate an SRT subtitle file from Whisper transcription output.

        Parameters
        ----------
        transcription:
            Whisper JSON output (must contain ``segments`` key with each
            segment having ``start``, ``end``, and ``text``).
        output_path:
            Destination path for the ``.srt`` file.

        Returns
        -------
        str
            Absolute path to the generated SRT file.
        """
        segments = transcription.get("segments", [])
        if not segments:
            logger.warning("generate_srt: no segments in transcription")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        lines: list[str] = []
        for idx, seg in enumerate(segments, start=1):
            start = self._seconds_to_srt_time(seg.get("start", 0.0))
            end = self._seconds_to_srt_time(seg.get("end", 0.0))
            text = seg.get("text", "").strip()
            lines.append(f"{idx}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")  # blank line separator

        srt_content = "\n".join(lines)

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(srt_content)

        logger.info("generate_srt: wrote %d segments → %s", len(segments), output_path)
        return os.path.abspath(output_path)

    # ------------------------------------------------------------------
    # SRT proofreading (brand name check + sentence optimization)
    # ------------------------------------------------------------------

    def proofread_srt(
        self,
        srt_path: str,
        brand_name: str,
    ) -> bool:
        """Proofread an SRT file for brand name correctness.

        Checks that *brand_name* appears in the SRT with consistent and
        correct spelling.  If the brand name is mentioned in the SRT but
        misspelled, returns ``False``.

        This is a local heuristic check (no LLM call) that:
        1. Verifies *brand_name* is present if expected.
        2. Checks for common misspellings (Levenshtein distance ≤ 2 for
           names ≥ 5 chars, exact match for shorter names).

        Parameters
        ----------
        srt_path:
            Path to the SRT file.
        brand_name:
            Expected brand name to verify.

        Returns
        -------
        bool
            ``True`` if the brand name is correctly spelled (or absent,
            which means no brand mention to check). ``False`` if a
            misspelling is detected.
        """
        if not os.path.isfile(srt_path):
            logger.error("proofread_srt: file not found: %s", srt_path)
            return False

        with open(srt_path, "r", encoding="utf-8") as fh:
            content = fh.read()

        # Strip SRT timestamps and sequence numbers for text-only analysis
        text = self._strip_srt_metadata(content)

        if not brand_name:
            return True

        # If brand name exactly matches somewhere, it's fine
        if brand_name.lower() in text.lower():
            return True

        # Check for near-miss misspellings (fuzzy match)
        return self._check_brand_spelling(text, brand_name)

    # ------------------------------------------------------------------
    # One-stop: TTS → ASR → SRT
    # ------------------------------------------------------------------

    def generate_all(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        output_dir: str = "",
    ) -> dict[str, str]:
        """Run the full TTS → ASR → SRT pipeline.

        Parameters
        ----------
        text:
            Text content to synthesize.
        voice:
            Edge-TTS voice identifier.
        output_dir:
            Directory for all output files.

        Returns
        -------
        dict[str, str]
            Mapping of output type to file path:
            - ``"mp3"``: path to generated MP3
            - ``"json"``: path to Whisper JSON transcription
            - ``"srt"``: path to generated SRT file
        """
        if not output_dir:
            raise ValueError("output_dir must not be empty")

        os.makedirs(output_dir, exist_ok=True)

        # 1. TTS
        mp3_path = os.path.join(output_dir, "output.mp3")
        self.generate_tts(text, voice=voice, output_path=mp3_path)

        # 2. ASR
        transcription = self.transcribe_audio(mp3_path)

        # 3. Write Whisper JSON for reference
        json_path = os.path.join(output_dir, "transcription.json")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(transcription, fh, ensure_ascii=False, indent=2)

        # 4. SRT
        srt_path = os.path.join(output_dir, "output.srt")
        self.generate_srt(transcription, output_path=srt_path)

        return {
            "mp3": os.path.abspath(mp3_path),
            "json": os.path.abspath(json_path),
            "srt": os.path.abspath(srt_path),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """Convert seconds to SRT timestamp format ``HH:MM:SS,mmm``."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _strip_srt_metadata(content: str) -> str:
        """Remove SRT sequence numbers and timestamps, keeping only text."""
        lines = content.split("\n")
        text_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Skip empty lines, sequence numbers (pure digits), and timestamps
            if not stripped:
                continue
            if re.match(r"^\d+$", stripped):
                continue
            if re.match(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", stripped):
                continue
            text_lines.append(stripped)
        return " ".join(text_lines)

    @staticmethod
    def _check_brand_spelling(text: str, brand_name: str) -> bool:
        """Check that *brand_name* is spelled correctly in *text*.

        Returns ``True`` if no misspelling is found, ``False`` if a
        near-miss is detected.
        """
        # Extract all word-like tokens from the text
        words = re.findall(r"[\w\u4e00-\u9fff]+", text, re.UNICODE)

        # For short brand names (<=4 chars), require exact match
        if len(brand_name) <= 4:
            for word in words:
                if word.lower() != brand_name.lower() and _is_similar(word, brand_name, max_dist=1):
                    return False
            return True

        # For longer brand names, check with Levenshtein distance ≤ 2
        for word in words:
            if word.lower() == brand_name.lower():
                continue  # exact match, fine
            if _is_similar(word, brand_name, max_dist=2):
                return False  # near-miss → misspelling

        return True


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1.lower() == c2.lower() else 1
            curr_row.append(min(
                curr_row[j] + 1,       # insertion
                prev_row[j + 1] + 1,   # deletion
                prev_row[j] + cost,     # substitution
            ))
        prev_row = curr_row

    return prev_row[-1]


def _is_similar(word: str, brand_name: str, max_dist: int = 2) -> bool:
    """Check if *word* is a near-miss of *brand_name* (case-insensitive)."""
    if abs(len(word) - len(brand_name)) > max_dist:
        return False
    return _levenshtein_distance(word.lower(), brand_name.lower()) <= max_dist
