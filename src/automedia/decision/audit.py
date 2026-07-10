"""Force-provenance audit logging.

Records all ``--force-provenance`` bypass events with timestamp and
user info to ``~/.automedia/audit/force_provenance.log``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _audit_log_path() -> Path:
    """Return the path to the force-provenance audit log."""
    return Path.home() / ".automedia" / "audit" / "force_provenance.log"


def log_force_provenance(
    topic: str,
    brand: str,
    user: str = "unknown",
    args: str = "",
) -> None:
    """Append a force-provenance bypass event to the audit log."""
    log_path = _audit_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).isoformat()
    entry = f"[{timestamp}] user={user} topic={topic!r} brand={brand!r} args={args}\n"

    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(entry)
