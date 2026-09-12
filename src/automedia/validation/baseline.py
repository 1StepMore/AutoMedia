"""Immutable baseline regeneration for the agent-tester validation layer (gap R-10).

The committed baseline at ``scenarios/baseline/2026-08-14-preflight.json`` is a
model artifact: :func:`automedia.validation.diff.diff_latest` and
``validate matrix`` resolve it as the default comparison point, so silently
rewriting it destroys the reference.  It was previously regenerated with
``json.dump(r, open(path, "w"))`` — a non-exclusive write that overwrote the
prior RED baseline in place (the exact "GREEN with no recorded RED" state the
honesty rules call suspect).  This module routes regeneration through
:func:`automedia.validation.persist.persist_baseline`, whose ``O_CREAT|O_EXCL``
write refuses to overwrite an existing baseline.

To record a new baseline, point ``baseline_path`` at a new file; the committed
baseline is never rewritten in place.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from automedia.validation.adapters import ToolCallable
from automedia.validation.engine import run_validation_suite_async
from automedia.validation.persist import persist_baseline

DEFAULT_BASELINE_PATH: str = "scenarios/baseline/2026-08-14-preflight.json"
"""The committed baseline all diff/matrix tooling resolves by default."""

BASELINE_NOTE: str = "full-suite baseline"
"""Note stamped on a regenerated baseline record (readable provenance)."""


async def regenerate_baseline_async(
    server: ToolCallable | None,
    *,
    baseline_path: str | Path = DEFAULT_BASELINE_PATH,
    scenarios_dir: str | Path | None = None,
    runs_root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """Run the whole library and write a NEW baseline record exclusively.

    ``save=False`` keeps the run evidence-free (the baseline IS the committed
    artifact), then the record is written with
    :func:`~automedia.validation.persist.persist_baseline`.  A pre-existing
    target raises :class:`~automedia.validation.persist.PersistError` — the
    committed baseline is never overwritten in place.
    """
    record = await run_validation_suite_async(
        server,
        scenarios_dir,
        runs_root=None if runs_root is None else Path(runs_root),
        save=False,
        cwd=None if cwd is None else Path(cwd),
    )
    record["baseline"] = True
    record["note"] = BASELINE_NOTE
    return persist_baseline(Path(baseline_path), record)


def regenerate_baseline(
    server: ToolCallable | None,
    *,
    baseline_path: str | Path = DEFAULT_BASELINE_PATH,
    scenarios_dir: str | Path | None = None,
    runs_root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """Sync wrapper of :func:`regenerate_baseline_async` (CLI/test path only)."""
    return asyncio.run(
        regenerate_baseline_async(
            server,
            baseline_path=baseline_path,
            scenarios_dir=scenarios_dir,
            runs_root=runs_root,
            cwd=cwd,
        )
    )
