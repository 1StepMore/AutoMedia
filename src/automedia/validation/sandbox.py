"""Per-invocation filesystem isolation for validation runs (#333/#334).

Validation runs are evidence-gathering, not production: they must never write
accounts, brand profiles, or project directories into the user's real
``~/.automedia`` tree or the repository root.  A suite-level sandbox gives every
invocation a private ``config/`` and ``projects/`` directory under one temporary
root, then removes it.

Explicit is honored: a caller who already exported ``AUTOMEDIA_CONFIG_DIR`` or
``AUTOMEDIA_PROJECTS_DIR`` keeps that location; the sandbox only fills in the
missing half.  ``AUTOMEDIA_VALIDATION_KEEP_SANDBOX=1`` preserves the root for
post-mortem inspection.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

CONFIG_ENV = "AUTOMEDIA_CONFIG_DIR"
PROJECTS_ENV = "AUTOMEDIA_PROJECTS_DIR"
KEEP_ENV = "AUTOMEDIA_VALIDATION_KEEP_SANDBOX"

_TRUTHY = frozenset({"1", "true", "yes"})


@dataclass(frozen=True)
class Sandbox:
    """The directories one validation invocation is allowed to write."""

    root: Path
    config_dir: Path
    projects_dir: Path
    env: dict[str, str]
    temporary: bool

    def describe(self) -> dict[str, object]:
        """Run-record metadata proving where the invocation was isolated."""
        return {
            "root": str(self.root),
            "config_dir": str(self.config_dir),
            "projects_dir": str(self.projects_dir),
            "temporary": self.temporary,
        }


@contextmanager
def validation_sandbox(environ: Mapping[str, str] | None = None) -> Iterator[Sandbox]:
    """Isolate user config and project state for one validation invocation.

    The sandbox is installed in ``os.environ`` for in-process tool steps and
    handed to CLI steps as an explicit mapping, so subprocesses see the same
    directories.  The previous environment is restored and the temporary root
    removed on exit.
    """
    source = os.environ if environ is None else environ
    existing_config = source.get(CONFIG_ENV, "")
    existing_projects = source.get(PROJECTS_ENV, "")

    if existing_config and existing_projects:
        config_dir = Path(existing_config).expanduser().resolve()
        projects_dir = Path(existing_projects).expanduser().resolve()
        yield Sandbox(
            root=config_dir.parent,
            config_dir=config_dir,
            projects_dir=projects_dir,
            env={},
            temporary=False,
        )
        return

    root = Path(tempfile.mkdtemp(prefix="automedia-validation-"))
    owned_config = root / "config"
    owned_projects = root / "projects"
    owned_config.mkdir()
    owned_projects.mkdir()

    env: dict[str, str] = {}
    if not existing_config:
        env[CONFIG_ENV] = str(owned_config)
    if not existing_projects:
        env[PROJECTS_ENV] = str(owned_projects)
    config_dir = Path(env.get(CONFIG_ENV, existing_config)).expanduser().resolve()
    projects_dir = Path(env.get(PROJECTS_ENV, existing_projects)).expanduser().resolve()

    previous = {name: os.environ.get(name) for name in env}
    os.environ.update(env)
    try:
        yield Sandbox(
            root=root,
            config_dir=config_dir,
            projects_dir=projects_dir,
            env=env,
            temporary=True,
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if source.get(KEEP_ENV, "").strip().lower() not in _TRUTHY:
            shutil.rmtree(root, ignore_errors=True)
