"""PublishEngine — iterate all enabled adapters and publish."""

from __future__ import annotations

from typing import Any

from automedia.adapters.base import BasePlatformAdapter
from automedia.adapters.registry import AdapterRegistry


class PublishEngine:
    """Orchestrates publishing across every registered adapter.

    Usage::

        engine = PublishEngine()
        results = engine.publish_all("/path/to/artifact", project)
    """

    # Allow overriding the registry class for testing / extensibility.
    registry_class: type[AdapterRegistry] = AdapterRegistry

    def publish_all(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        account_ids: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Iterate adapters and publish.

        When *account_ids* is provided, publishes only to those accounts
        (instantiating adapters with account context).  Falls back to legacy
        behavior when ``None``.

        Partial failure: each account publish is independent; failures on
        one account don't block others.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.
        project:
            Full project dict.
        account_ids:
            Optional list of account identifiers for PRD-4 account-aware
            publishing.

        Returns
        -------
        dict[str, dict]
            Mapping ``{platform_or_account_id -> result_dict}`` for every
            adapter that was actually invoked.
        """
        results: dict[str, dict[str, Any]] = {}

        if account_ids:
            # PRD-4 path: publish per-account
            from automedia.accounts.registry import AccountRegistry  # noqa: PLC0415

            registry = AccountRegistry()

            for account_id in account_ids:
                info = registry.get(account_id)
                if not info:
                    results[account_id] = {
                        "status": "error",
                        "reason": f"Account not found: {account_id}",
                    }
                    continue

                platform: str = info["platform"]
                try:
                    adapter_cls = self.registry_class.get(platform)
                    adapter: BasePlatformAdapter = adapter_cls(account_id=account_id)

                    if not adapter.validate(artifact_dir):
                        results[account_id] = {
                            "status": "skipped",
                            "reason": "validation failed",
                        }
                        continue

                    result = adapter.publish(artifact_dir, project)
                    results[account_id] = result
                except Exception as exc:
                    results[account_id] = {"status": "error", "reason": str(exc)}
        else:
            # Legacy path: unchanged behavior
            for name in self.registry_class.list():
                adapter_cls = self.registry_class.get(name)
                adapter: BasePlatformAdapter = adapter_cls()

                if not adapter.enabled:
                    continue

                if not adapter.validate(artifact_dir):
                    results[name] = {
                        "status": "skipped",
                        "reason": "validation failed",
                    }
                    continue

                try:
                    result = adapter.publish(artifact_dir, project)
                    results[name] = result
                except Exception as exc:
                    results[name] = {"status": "error", "reason": str(exc)}

        return results
