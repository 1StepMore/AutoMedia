"""Azure Speech TTS engine — commercial neural text-to-speech via REST.

Provides:
    - :class:`AzureTTSEngine` — a :class:`BaseTTSEngine` implementation that
      calls the Azure Speech REST API (``https://{region}.tts.speech.
      microsoft.com/cognitiveservices/v1``) directly over ``httpx`` — no
      ``azure-*`` SDK dependency.

Configuration (``engines.tts.azure`` in ``.automedia/config.yaml``)::

    azure:
      voice: zh-CN-YunjianNeural          # kit baseline: 有力男声
      output_format: audio-24khz-48kbitrate-mono-mp3
      speech_key: null                    # prefer the env var below
      region: null                        # prefer the env var below

Credentials resolve **env first** (``AUTOMEDIA_AZURE_SPEECH_KEY``,
``AUTOMEDIA_AZURE_SPEECH_REGION``), then the config keys above. The engine is
chain-safe: ``check_available()`` is ``False`` without credentials, so the TTS
fallback chain (``engines.tts.chain``) skips it transparently when Azure is
not configured.

Speech-text normalization: per the narration methodology (``promo/docs/tts.md``),
the spoken form of "AI" is「人工智能」— :func:`speech_friendly_text` rewrites
standalone ``AI`` (not ``AIGC``-style tokens) before synthesis. Disable with
``engines.tts.azure.speech_normalization: false``.
"""

from __future__ import annotations

import logging
import os
import re
from typing import ClassVar, cast
from xml.sax.saxutils import escape as xml_escape

from typing_extensions import override

from automedia.core.env_overlay import env_lookup
from automedia.engines.base import BaseTTSEngine
from automedia.engines.errors import EngineExecutionError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VOICE: str = "zh-CN-YunjianNeural"
"""Default Azure neural voice (video-narration baseline voice)."""

DEFAULT_OUTPUT_FORMAT: str = "audio-24khz-48kbitrate-mono-mp3"
"""Narration-friendly output format (24 kHz mono MP3, per promo/docs/tts.md)."""

SPEECH_KEY_ENV: str = "AUTOMEDIA_AZURE_SPEECH_KEY"
SPEECH_REGION_ENV: str = "AUTOMEDIA_AZURE_SPEECH_REGION"

_REQUEST_TIMEOUT: float = 120.0

_SPEECH_HOST_TEMPLATE = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

# Standalone "AI" → 「人工智能」 (spoken form). Lookarounds keep tokens like
# AIGC / AINet intact; CJK neighbours are not ASCII letters, so 「AI绘图」
# and 「用AI」 both normalize.
_STANDALONE_AI_RE = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])")


def speech_friendly_text(text: str) -> str:
    """Rewrite *text* into its spoken form for narration synthesis.

    Currently: standalone ``AI`` → ``人工智能`` (the narration rule from the
    promo kit's TTS notes — "AI" reads awkwardly as letters in Chinese
    speech). Idempotent and safe on already-normalized text.
    """
    if "AI" not in text:
        return text
    return _STANDALONE_AI_RE.sub("人工智能", text)


# ---------------------------------------------------------------------------
# AzureTTSEngine
# ---------------------------------------------------------------------------


class AzureTTSEngine(BaseTTSEngine):
    """Text-to-Speech engine backed by the Azure Speech REST API.

    Attributes
    ----------
    engine_name : str
        Registration key in the :class:`EngineRegistry` (``"azure"``).
    modality : str
        Modality grouping (``"tts"``).
    """

    engine_name: ClassVar[str] = "azure"
    modality: ClassVar[str] = "tts"

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _credentials(self) -> tuple[str | None, str | None]:
        """Resolve (key, region) — env vars first, engine config second."""
        key = env_lookup(SPEECH_KEY_ENV) or self._config.get("speech_key")
        region = env_lookup(SPEECH_REGION_ENV) or self._config.get("region")
        return (str(key) if key else None), (str(region) if region else None)

    # ------------------------------------------------------------------
    # Dependency check
    # ------------------------------------------------------------------

    @override
    def check_available(self) -> tuple[bool, str]:
        """Report readiness: credentials present and ``httpx`` importable.

        Deliberately does **not** probe the network — credential presence is
        cheap and deterministic, and the chain needs a fast skip when Azure
        is simply not configured.
        """
        try:
            import httpx  # noqa: F401
        except ImportError:
            return False, "httpx not installed (core dependency) — cannot call Azure Speech"

        key, region = self._credentials()
        if not key:
            return False, f"{SPEECH_KEY_ENV} not set (and engines.tts.azure.speech_key empty)"
        if not region:
            return False, f"{SPEECH_REGION_ENV} not set (and engines.tts.azure.region empty)"
        return True, f"Azure Speech configured for region {region!r}"

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
        """Generate TTS audio via the Azure Speech REST API.

        Parameters
        ----------
        text:
            Text to synthesize.  Must be non-empty.  Normalized through
            :func:`speech_friendly_text` unless
            ``engines.tts.azure.speech_normalization`` is ``false``.
        voice:
            Azure neural voice identifier (e.g. ``"zh-CN-YunjianNeural"``).
            Falls back to ``self._config.get("voice", DEFAULT_VOICE)`` when
            empty.
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
            If *text* or *output_path* is empty, or credentials are missing.
        EngineExecutionError
            If the REST call fails (auth, quota, network, bad region).
        """
        if not text:
            raise ValueError("text must not be empty")
        if not output_path:
            raise ValueError("output_path must not be empty")

        key, region = self._credentials()
        if not key or not region:
            raise ValueError(
                f"Azure Speech credentials missing — set {SPEECH_KEY_ENV} and "
                f"{SPEECH_REGION_ENV} (or engines.tts.azure.speech_key/region)"
            )

        if not voice:
            voice = cast(str, self._config.get("voice", DEFAULT_VOICE))
        output_format = cast(str, self._config.get("output_format", DEFAULT_OUTPUT_FORMAT))

        if self._config.get("speech_normalization", True):
            text = speech_friendly_text(text)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        lang = "-".join(voice.split("-")[:2]) or "zh-CN"
        ssml = (
            f"<speak version='1.0' xml:lang='{lang}'>"
            f"<voice name='{xml_escape(voice)}'>{xml_escape(text)}</voice>"
            f"</speak>"
        )

        import httpx

        url = _SPEECH_HOST_TEMPLATE.format(region=region)
        headers = {
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": output_format,
            "User-Agent": "automedia-tts",
        }

        logger.info("azure-tts: synthesizing %d chars (%s) → %s", len(text), voice, output_path)
        try:
            with httpx.Client(timeout=httpx.Timeout(_REQUEST_TIMEOUT)) as client:
                resp = client.post(url, content=ssml.encode("utf-8"), headers=headers)
        except httpx.HTTPError as exc:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=f"Azure Speech request failed: {exc}",
            ) from exc

        if resp.status_code in (401, 403):
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(
                    f"Azure Speech rejected the credentials (HTTP {resp.status_code}) — "
                    f"check {SPEECH_KEY_ENV} and {SPEECH_REGION_ENV} (got region {region!r})"
                ),
            )
        if resp.status_code == 429:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details="Azure Speech quota/rate limit hit (HTTP 429) — "
                "the TTS chain will fall through to the next provider",
            )
        if resp.status_code != 200:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=f"Azure Speech returned HTTP {resp.status_code}: {resp.text[:200]}",
            )

        with open(output_path, "wb") as fh:
            fh.write(resp.content)

        logger.info("azure-tts: wrote %s (%d bytes)", output_path, len(resp.content))
        return os.path.abspath(output_path)
