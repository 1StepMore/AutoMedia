"""Workflow configuration — load, validate, and merge workflow YAML definitions.

A *workflow* encapsulates everything needed to run the AutoMedia pipeline:
target platforms, pipeline mode, brand override, gate modifiers, prompt
template overrides, media spec overrides, and scheduling.  Workflows live
as individual ``.yaml`` files in the ``workflows/`` subdirectory of either
the project ``.automedia/`` or user ``~/.automedia/`` config directory.

Public API
----------
- ``Workflow`` — dataclass with 9 fields (name, mode, platforms, brand, …)
- ``WorkflowLoader(workflows_dir=None)``
  - ``load(name) -> Workflow``
  - ``load_all() -> dict[str, Workflow]``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from automedia.core.config_loader import deep_merge
from automedia.core.paths import get_user_config_dir

# ---------------------------------------------------------------------------
# Workflow dataclass
# ---------------------------------------------------------------------------


@dataclass
class Workflow:
    """A named workflow configuration for the AutoMedia pipeline.

    Parameters
    ----------
    name:
        Workflow identifier (should match the YAML filename stem).
    mode:
        Pipeline execution mode.  Must be one of
        :data:`automedia.pipelines.runner.VALID_MODES`.
    platforms:
        Target platform names.  Each must be registered in
        :class:`automedia.adapters.registry.AdapterRegistry`.
    brand:
        Optional brand identifier override.  When ``None`` the pipeline
        uses its default brand resolution.
    gates:
        Optional gate modifiers dict with keys ``include``, ``exclude``,
        and/or ``override_failure_mode``.  Passed through to
        :func:`automedia.pipelines.runner.validate_gate_modifiers`.
    prompts:
        Optional prompt template name → content overrides.
    media:
        Optional media spec overrides (platform → :class:`PlatformMediaSpec`
        fields).
    schedule:
        Optional scheduling configuration.  Expected keys:
        ``expression`` (cron string) and ``count`` (int, number of
        topics per run).
    extends:
        Optional parent workflow name.  When set, the parent workflow
        is loaded first and all fields are deep-merged (child overrides
        parent).
    """

    name: str
    mode: str = "auto"
    platforms: list[str] = field(default_factory=list)
    brand: str | None = None
    gates: dict[str, Any] | None = None
    prompts: dict[str, str] | None = None
    media: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    extends: str | None = None


# ---------------------------------------------------------------------------
# WorkflowLoader
# ---------------------------------------------------------------------------


class WorkflowLoader:
    """Load and validate workflow YAML definitions.

    Resolution order (highest priority first):
    1. ``~/.automedia/workflows/<name>.yaml`` (user-level)
    2. ``<workflows_dir>/<name>.yaml`` (project-level)

    Parameters
    ----------
    workflows_dir:
        Root of the project-level workflows directory.  Defaults to
        ``<cwd>/.automedia/workflows``.  When a workflow is not found
        here, the loader falls back to the user-level workflows
        directory (``~/.automedia/workflows``).
    """

    MAX_EXTENDS_DEPTH = 3

    def __init__(self, workflows_dir: str | Path | None = None) -> None:
        self._workflows_dir = (
            Path(workflows_dir) if workflows_dir is not None
            else Path.cwd() / ".automedia" / "workflows"
        )
        self._user_workflows_dir = get_user_config_dir() / "workflows"

    # -- Properties ---------------------------------------------------------

    @property
    def workflows_dir(self) -> Path:
        """The resolved project-level workflows directory."""
        return self._workflows_dir

    @property
    def user_workflows_dir(self) -> Path:
        """The resolved user-level workflows directory."""
        return self._user_workflows_dir

    # -- File resolution ----------------------------------------------------

    def _find_file(self, name: str) -> Path | None:
        """Locate a workflow YAML file by *name*.

        Checks user-level directory first (higher priority), then
        project-level directory.  Accepts both ``.yaml`` and ``.yml``
        extensions.
        """
        for base in (self._user_workflows_dir, self._workflows_dir):
            for ext in (".yaml", ".yml"):
                path = base / f"{name}{ext}"
                if path.is_file():
                    return path
        return None

    def _load_raw(self, name: str) -> dict[str, Any]:
        """Load a raw workflow YAML dict without validation or merge."""
        path = self._find_file(name)
        if path is None:
            dirs = [str(self._user_workflows_dir), str(self._workflows_dir)]
            raise FileNotFoundError(
                f"Workflow {name!r} not found in:\n  " + "\n  ".join(dirs)
            )
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(
                f"Workflow file {path} must be a YAML mapping, "
                f"got {type(data).__name__}"
            )
        # Validate name field matches filename
        yaml_name = data.get("name")
        if yaml_name is not None and yaml_name != name:
            raise ValueError(
                f"Workflow file {path} declares name {yaml_name!r} "
                f"but filename expects {name!r}"
            )
        return data

    # -- Extends resolution -------------------------------------------------

    def _resolve_extends(
        self,
        name: str,
        visited: set[str],
        depth: int,
    ) -> dict[str, Any]:
        """Recursively resolve the ``extends`` inheritance chain.

        Parameters
        ----------
        name:
            Workflow name to load.
        visited:
            Set of workflow names already visited in this chain (used
            for circular reference detection).
        depth:
            Current depth in the extends chain (0 for the top-level
            workflow).

        Returns
        -------
        dict
            Fully merged workflow dict with the ``extends`` key removed.

        Raises
        ------
        ValueError
            If the extends chain exceeds :attr:`MAX_EXTENDS_DEPTH` or a
            circular reference is detected.
        """
        if depth > self.MAX_EXTENDS_DEPTH:
            raise ValueError(
                f"Extends chain exceeds max depth "
                f"({self.MAX_EXTENDS_DEPTH}) for workflow {name!r}"
            )
        if name in visited:
            chain = " → ".join(visited | {name})
            raise ValueError(
                f"Circular extends detected for workflow {name!r}: {chain}"
            )
        visited.add(name)

        data = self._load_raw(name)
        parent_name = data.get("extends")

        if parent_name is not None:
            if not isinstance(parent_name, str):
                raise ValueError(
                    f"Workflow {name!r} 'extends' field must be a string, "
                    f"got {type(parent_name).__name__}"
                )
            parent = self._resolve_extends(parent_name, visited, depth + 1)
            merged = deep_merge(parent, data)
            merged.pop("extends", None)
            return merged

        # No parent — just strip the extends key
        data.pop("extends", None)
        return data

    # -- Validation ---------------------------------------------------------

    def _validate(self, data: dict[str, Any]) -> None:
        """Validate workflow fields after merge.

        Checks
        ------
        * ``mode`` is a known pipeline mode.
        * ``platforms`` (if present) are registered in
          :class:`~automedia.adapters.registry.AdapterRegistry`.
        """
        name = data.get("name", "?")

        # Mode validation — lazy import to avoid circular deps with runner.py
        from automedia.pipelines.runner import VALID_MODES

        mode = data.get("mode", "auto")
        if mode not in VALID_MODES:
            raise ValueError(
                f"Invalid mode {mode!r} in workflow {name!r}. "
                f"Valid modes: {sorted(VALID_MODES)}"
            )

        # Platform validation
        platforms = data.get("platforms", [])
        if platforms:
            # Lazy import to ensure adapters are registered
            from automedia.adapters.registry import AdapterRegistry

            try:
                available = AdapterRegistry.list()
            except Exception:
                available = []
            for p in platforms:
                if p not in available:
                    raise ValueError(
                        f"Unknown platform {p!r} in workflow {name!r}. "
                        f"Registered platforms: {sorted(available)}"
                    )

    # -- Public API ---------------------------------------------------------

    def load(self, name: str) -> Workflow:
        """Load a single workflow by name.

        Resolution order (highest priority first):
        1. ``~/.automedia/workflows/<name>.yaml`` (user-level)
        2. ``<workflows_dir>/<name>.yaml`` (project-level)

        If the workflow has an ``extends`` field, the parent is loaded
        and deep-merged (child fields override parent).  The final dict
        is validated before constructing the :class:`Workflow`.

        Parameters
        ----------
        name:
            Workflow name (corresponds to ``<name>.yaml`` or ``<name>.yml``).

        Returns
        -------
        Workflow
            Validated workflow dataclass.

        Raises
        ------
        FileNotFoundError
            If no workflow file is found for *name*.
        ValueError
            If validation fails or the extends chain is invalid.
        """
        visited: set[str] = set()
        raw = self._resolve_extends(name, visited, depth=0)
        self._validate(raw)
        return Workflow(**raw)

    def load_all(self) -> dict[str, Workflow]:
        """Load all unique workflows from user and project directories.

        When the same workflow name exists in both directories, the
        user-level version takes priority (since it is checked first).

        Returns
        -------
        dict[str, Workflow]
            Mapping of ``{workflow_name: Workflow}``.
        """
        workflows: dict[str, Workflow] = {}
        seen: set[str] = set()

        # Collect file stems from both dirs; user dir first so it wins
        # on name collision.
        entries: list[tuple[str, Path]] = []
        for base in (self._user_workflows_dir, self._workflows_dir):
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if entry.suffix in (".yaml", ".yml") and entry.stem not in seen:
                    seen.add(entry.stem)
                    entries.append((entry.stem, entry))

        for stem, _ in entries:
            try:
                workflows[stem] = self.load(stem)
            except (FileNotFoundError, ValueError):
                continue

        return workflows
