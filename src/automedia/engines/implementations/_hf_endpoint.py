"""Hugging Face endpoint resolution for model downloads — issue #512.

``faster-whisper`` resolves bare model names (e.g. ``"tiny"``) through
``huggingface_hub`` on first use, and the hub endpoint is baked into
``huggingface_hub.constants`` at *import time*. On networks where
``huggingface.co`` is unreachable the download fails, transcription fails,
and V2/V5 degrade to their honest skip forever (issue #512 — reproduced:
``LocalEntryNotFoundError`` without a mirror; the same load succeeds with
``HF_ENDPOINT=https://hf-mirror.com``).

``ensure_hf_endpoint`` gives the ASR engines one place to settle the
endpoint BEFORE the library is first imported in the process. Priority:
config key ``hf_endpoint`` > an already-set ``HF_ENDPOINT`` >
:data:`DEFAULT_HF_ENDPOINT` (the mirror — owner decision, #512). A hit in
the local hub cache needs no network at all, so the default is inert
whenever the model is already on disk.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"
"""Mirror used when neither config nor environment pins an endpoint."""


def ensure_hf_endpoint(config: Mapping[str, Any] | None = None) -> str:
    """Settle ``HF_ENDPOINT`` in the environment and return the value.

    An explicit config key ``hf_endpoint`` wins and overwrites the
    environment; otherwise an existing ``HF_ENDPOINT`` is kept untouched;
    otherwise the mirror default is set. Must be called before
    ``huggingface_hub`` (and therefore ``faster_whisper``) is first imported
    in the process — the constant is baked at import time.
    """
    configured = str((config or {}).get("hf_endpoint") or "").strip()
    if configured:
        os.environ["HF_ENDPOINT"] = configured
        return configured
    return os.environ.setdefault("HF_ENDPOINT", DEFAULT_HF_ENDPOINT)
