"""AutoMedia Omni — unified plugin-like adapter framework.

The Omni package provides a clean adapter layer over three external tools:

- **omni-pre-processor** (OPP) — document extraction
- **omni-localizer** (OL) — translation
- **omni-re-formatter** (ORF) — format conversion
"""

from __future__ import annotations

from automedia.omni.allowlist import AllowlistConfig, is_read_only, load_allowlist, validate_path
from automedia.omni.base import BaseOmniAdapter
from automedia.omni.config import OmniConfig, load_omni_config
from automedia.omni.md5_integration import (
    compute_md5,
    get_md5,
    has_changed,
    load_state,
    save_state,
    set_md5,
)
from automedia.omni.ol_adapter import OLAdapter, TranslationResult
from automedia.omni.opp_adapter import ExtractionResult, OPPAdapter
from automedia.omni.orf_adapter import ORFAdapter
from automedia.omni.registry import OmniToolRegistry


def _register_builtins() -> None:
    """Auto-register the three built-in adapters on import (idempotent)."""
    try:
        OmniToolRegistry.register(OPPAdapter())
        OmniToolRegistry.register(OLAdapter())
        OmniToolRegistry.register(ORFAdapter())
    except KeyError:
        pass


_register_builtins()

__all__ = [
    # Base
    "BaseOmniAdapter",
    # Config
    "OmniConfig",
    "load_omni_config",
    # Allowlist
    "AllowlistConfig",
    "is_read_only",
    "load_allowlist",
    "validate_path",
    # MD5
    "compute_md5",
    "get_md5",
    "has_changed",
    "load_state",
    "save_state",
    "set_md5",
    # Adapters
    "OLAdapter",
    "OPPAdapter",
    "ORFAdapter",
    "ExtractionResult",
    "TranslationResult",
    # Registry
    "OmniToolRegistry",
]
