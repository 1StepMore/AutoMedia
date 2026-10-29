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

The sandbox also provisions a scoped ``mcp_allowlist.yaml`` (via
``AUTOMEDIA_MCP_ALLOWLIST_PATH``) covering the sandbox dirs and
``/tmp/automedia/``, so the MCP tools' fail-closed allowlist checks pass for
scenario steps that address sandbox paths — unless the caller already
exported their own allowlist path.
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
ALLOWLIST_ENV = "AUTOMEDIA_MCP_ALLOWLIST_PATH"

_TRUTHY = frozenset({"1", "true", "yes"})


def _write_sandbox_allowlist(directory: Path, config_dir: Path, projects_dir: Path) -> Path:
    """Write a per-invocation ``mcp_allowlist.yaml`` scoped to the sandbox.

    Scenario steps legitimately pass ``base_dir: ${AUTOMEDIA_PROJECTS_DIR}``
    (the journeys do) and some committed recovery scenarios pin
    ``/tmp/automedia/`` paths.  With fail-closed allowlist enforcement in the
    MCP tools, a validation run must carry its own allowlist or those steps
    would flip to ``ALLOWLIST_DENIED``.  A caller who already exported
    ``AUTOMEDIA_MCP_ALLOWLIST_PATH`` keeps theirs (explicit wins, like the
    config/projects env vars).
    """
    import yaml

    # "/tmp/automedia/" is the committed recovery scenarios' pinned fixture
    # path and a factory allowlist entry (not a secret temp file).
    entries = sorted(
        {
            str(directory),
            str(config_dir),
            str(projects_dir),
            "/tmp/automedia/",  # noqa: S108 — pinned scenario fixture path
        }
    )
    payload = {
        "comment": (
            "Generated per-invocation validation allowlist — scoped to the sandbox; do not edit."
        ),
        "allowed_directories": entries,
    }
    path = directory / "mcp_allowlist.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def _reset_mcp_allowlist_cache() -> None:
    """Drop the allowlist module's cached entries after an env change."""
    from automedia.mcp.allowlist import _reset_allowlist_cache

    _reset_allowlist_cache()


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
    caller_allowlist = source.get(ALLOWLIST_ENV, "")

    if existing_config and existing_projects:
        config_dir = Path(existing_config).expanduser().resolve()
        projects_dir = Path(existing_projects).expanduser().resolve()
        extra_env: dict[str, str] = {}
        allowlist_home: Path | None = None
        if not caller_allowlist:
            allowlist_home = Path(tempfile.mkdtemp(prefix="automedia-validation-allowlist-"))
            extra_env[ALLOWLIST_ENV] = str(
                _write_sandbox_allowlist(allowlist_home, config_dir, projects_dir)
            )
        previous = {name: os.environ.get(name) for name in extra_env}
        os.environ.update(extra_env)
        _reset_mcp_allowlist_cache()
        try:
            yield Sandbox(
                root=config_dir.parent,
                config_dir=config_dir,
                projects_dir=projects_dir,
                env=extra_env,
                temporary=False,
            )
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            _reset_mcp_allowlist_cache()
            if allowlist_home is not None:
                shutil.rmtree(allowlist_home, ignore_errors=True)
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
    if not caller_allowlist:
        env[ALLOWLIST_ENV] = str(_write_sandbox_allowlist(root, config_dir, projects_dir))

    previous = {name: os.environ.get(name) for name in env}
    os.environ.update(env)
    _reset_mcp_allowlist_cache()
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
        _reset_mcp_allowlist_cache()
        if source.get(KEEP_ENV, "").strip().lower() not in _TRUTHY:
            shutil.rmtree(root, ignore_errors=True)
