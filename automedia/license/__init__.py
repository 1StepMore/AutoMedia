"""License system — open-core feature gating.

Exports
-------
- ``LicenseManager`` — check status and commercial feature availability
- ``LicenseStatus`` — enum (OS_COMMUNITY, COMMERCIAL, EXPIRED)
"""

from __future__ import annotations

from automedia.license.manager import LicenseManager, LicenseStatus

__all__ = ["LicenseManager", "LicenseStatus"]
