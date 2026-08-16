"""Env-gated external/API detector adapters (B3).

These adapters follow the repo's ``AUTOMEDIA_*`` env-var convention (see
``.env.example``): a detector is only *available* when its required env
var is set and non-empty.  Adapters are still registered unconditionally —
registration is not gating; calling ``detect()`` on an unavailable adapter
raises instead of fabricating evidence.

Production wiring point: to integrate a real external AI-taste API (e.g.
a GPTZero-style service), replace the raise at the end of
:meth:`GPTZeroStyleApiDetector.detect` with an authenticated HTTP call
using the key from ``os.environ["AUTOMEDIA_DETECTOR_GPTZERO_API_KEY"]``
and map the API response into a :class:`DetectorResult`.  This build never
makes a network call — the adapter is a deliberate, honest no-op boundary
that raises rather than returning fake scores.
"""

from __future__ import annotations

from automedia.detectors.base import BaseDetector, DetectorResult


class GPTZeroStyleApiDetector(BaseDetector):
    """Placeholder for an external AI-writing-detector API.

    Gated on ``AUTOMEDIA_DETECTOR_GPTZERO_API_KEY``.  With the env var
    unset, :meth:`available` reports False and :meth:`detect` raises a
    RuntimeError naming the missing variable.  With the env var set,
    :meth:`available` reports True, but :meth:`detect` STILL raises a
    "not configured in this build" RuntimeError because no endpoint is
    wired here — it never fabricates a score and never makes a real
    network call (the honesty rule: no fake evidence).
    """

    _detector_name = "gptzero_style_api"
    _env_required = "AUTOMEDIA_DETECTOR_GPTZERO_API_KEY"

    def detect(self, text: str) -> DetectorResult:
        """Refuse to run: either the env gate is closed or no endpoint is wired.

        Args:
            text: The text that would be sent to the external API.

        Raises:
            RuntimeError: Always — either the detector is unavailable
                (env var unset) or the external endpoint is not configured
                in this build.  An honest refusal beats fabricated evidence.
        """
        if not self.available():
            raise RuntimeError(
                f"detector '{self.detector_name}' is unavailable: env var "
                f"'{self._env_required}' is unset; set it to enable the detector"
            )
        raise RuntimeError(
            f"detector '{self.detector_name}' is not configured in this build: "
            "no external endpoint is wired. Production wiring point: replace "
            "this raise with an authenticated HTTP call to the external "
            f"AI-taste API using os.environ['{self._env_required}'] and map "
            "the response into a DetectorResult."
        )
