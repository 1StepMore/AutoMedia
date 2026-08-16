"""Pluggable AI-writing-taste detector framework (issue #62, Wave-B B1-B3).

A detector is any :class:`BaseDetector` subclass that inspects text and
returns a :class:`DetectorResult` with a normalized ``ai_score`` in [0, 1]
(higher = reads as AI-written) and a boolean ``passed``.  Detectors
auto-register in the :class:`DetectorRegistry` singleton at import time —
registration is unconditional; availability is per-detector via
``BaseDetector.available()`` (env-gated by the class attribute
``_env_required``, using the repo's ``AUTOMEDIA_*`` env-var convention).

Built-in detectors:

- ``deterministic_taste`` — env-free; reuses the G1 humanizer's 9 regex
  categories strictly by import (no pattern duplication).  Scores
  ``ai_score = failing / total`` and passes when ``ai_score <= 0.5``.

Convenience API:

- :func:`list_detectors` — names of all registered detectors (sorted).
- :func:`detect_text` — run every *available* detector against text and
  return their results in registry order.

The G1 humanizer closed loop (B4) will consume this framework to verify
that rewritten output no longer reads as AI-written.
"""

from __future__ import annotations

from automedia.detectors.base import BaseDetector, DetectorResult
from automedia.detectors.deterministic import DeterministicTasteDetector
from automedia.detectors.registry import DetectorRegistry

__all__ = [
    "BaseDetector",
    "DetectorResult",
    "DetectorRegistry",
    "DeterministicTasteDetector",
    "list_detectors",
    "detect_text",
]


def list_detectors() -> list[str]:
    """Return the names of all registered detectors (sorted)."""
    return DetectorRegistry().list()


def detect_text(text: str) -> list[DetectorResult]:
    """Run every available detector against *text* and return their results.

    Detectors whose ``available()`` is False (e.g. env-gated adapters
    without their env var) are skipped.  A detector that raises propagates
    its error — results are never fabricated.
    """
    results: list[DetectorResult] = []
    for name in DetectorRegistry().list():
        detector = DetectorRegistry().get(name)()
        if detector.available():
            results.append(detector.detect(text))
    return results
