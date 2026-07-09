"""AuditLog — lightweight in-memory audit trail for multi-tenant operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class AuditLog:
    """Simple in-memory audit log.

    In production this would be backed by a database table; the class-level
    ``_entries`` list serves as a thread-safe (for single-process) store
    sufficient for the current PRD-3 scope.
    """

    _entries: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def record(
        cls,
        who: str,
        action: str,
        what: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an auditable event.

        Parameters
        ----------
        who:
            User or system actor identifier (e.g. email, service name).
        action:
            Short description of the action performed.
        what:
            The resource or target the action was performed on.
        metadata:
            Optional key-value pairs for additional context.
        """
        cls._entries.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "who": who,
                "action": action,
                "what": what,
                "metadata": metadata or {},
            }
        )

    @classmethod
    def query(cls, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return audit entries, optionally filtered by exact key-value match.

        Parameters
        ----------
        filters:
            Optional dict of ``{field: value}`` pairs.  Only entries where
            *every* field matches are returned (AND semantics).

        Returns
        -------
        list[dict]
            Matching audit entries in insertion order (newest last).
        """
        results = list(cls._entries)
        if filters:
            for key, value in filters.items():
                results = [r for r in results if r.get(key) == value]
        return results

    @classmethod
    def clear(cls) -> None:
        """Remove all audit entries (useful for testing)."""
        cls._entries = []
