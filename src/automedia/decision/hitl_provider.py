"""Decision → HITL bridge — wires the decision dependency graph into HITL.

This module lives in ``decision/`` and imports from both ``decision`` and
``hitl``.  It is the *only* place where the two packages are coupled at
runtime.  Callers that need a fully-wired ``HITLConfig`` should use
:func:`create_hitl_config` instead of importing ``HITLConfig`` directly.
"""

from __future__ import annotations

from automedia.decision import dependency
from automedia.hitl.config import HITLConfig


def create_hitl_config(
    preset_name: str = "test_automated",
    overrides_dir: str | None = None,
) -> HITLConfig:
    """Create an :class:`HITLConfig` with the decision layer wired as
    :class:`~automedia.hitl.protocol.NodeProvider`.

    Parameters
    ----------
    preset_name:
        Preset to load (default ``"test_automated"`` which auto-generates
        from the decision dependency graph).
    overrides_dir:
        Optional path to override YAML files.

    Returns
    -------
    HITLConfig
        A fully-wired config instance.
    """
    return HITLConfig(
        preset_name=preset_name,
        overrides_dir=overrides_dir,
        node_provider=dependency,
    )
