"""
Backward-compatibility shim for ``automedia.platform``.

.. deprecated::
   Use :mod:`automedia.platform_drafts` instead.

This shim will be removed in v2.0.
"""

import warnings

from automedia.platform_drafts import XiaohongshuAdapter, ZhihuDraftAdapter  # noqa: F401

__all__ = [
    "XiaohongshuAdapter",
    "ZhihuDraftAdapter",
]

warnings.warn(
    "automedia.platform is deprecated; use automedia.platform_drafts instead.",
    DeprecationWarning,
    stacklevel=2,
)
