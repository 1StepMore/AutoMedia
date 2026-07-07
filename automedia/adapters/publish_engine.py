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
    ) -> dict[str, dict[str, Any]]:
        """Iterate all registered adapters and call ``publish()`` on enabled ones.

        Returns
        -------
        dict[str, dict]
            Mapping ``{platform_name -> result_dict}`` for every adapter
            that was actually invoked (enabled).
        """
        results: dict[str, dict[str, Any]] = {}

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
