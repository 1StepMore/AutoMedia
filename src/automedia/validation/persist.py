"""Run-record persistence for agent-tester validation (W1-T8).

Phase 6 of the engine contract (guide §3.1): write the run record to a
timestamped directory — immutable, written once — and refresh a stable
pointer file that names the latest run (guide §5.4).  Run records live under
a runtime directory such as ``validation-runs/`` which is gitignored: they
are "evidence of a moment in time, not source" (guide §3.5).

Immutability is enforced at the filesystem layer, not by convention:
``os.makedirs(exist_ok=False)`` creates the run directory exclusively, and
``scenarios.json`` is opened with ``O_CREAT|O_EXCL`` so a pre-existing run
dir or record is NEVER overwritten (plan deliberation #33 — this deliberately
hardens the guide skeleton's ``exist_ok=True``).  A collision on the primary
microsecond stamp ``%Y%m%d-%H%M%S-%f`` falls back to a random 6-hex suffix
(up to :data:`MAX_SUFFIX_RETRIES` attempts) before raising
:class:`PersistError`.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from secrets import token_hex

from automedia.validation.schema import Step

RUN_STAMP_FORMAT = "%Y%m%d-%H%M%S-%f"
"""Run directory name stamp: date + time + microseconds (guide skeleton §3.3,
hardened per deliberation #33 — collisions fall back to a random suffix)."""

MAX_SUFFIX_RETRIES = 5
"""How many random-suffix attempts follow a primary stamp collision."""


class PersistError(Exception):
    """A run record could not be persisted without overwriting existing evidence."""


def prepare_run_dir(runs_root: Path, *, stamp: str | None = None) -> Path:
    """Create and return an exclusive per-run directory (no record yet).

    Splitting directory creation from :func:`persist_run` lets the engine
    collect a GREEN step's artifacts into ``<run_dir>/artifacts/`` *before*
    the record is written (gap T-16), so artifacts and ``scenarios.json``
    share one immutable directory.  ``stamp`` pins the name (tests pin it);
    otherwise the microsecond stamp with the random-suffix collision fallback
    of :func:`_fresh_run_dir` applies.  A collision raises
    :class:`PersistError`.
    """
    if stamp is not None:
        return _exclusive_run_dir(runs_root, stamp)
    return _fresh_run_dir(runs_root)


def persist_run(
    runs_root: Path,
    run_record: dict[str, object],
    *,
    stamp: str | None = None,
    run_dir: Path | None = None,
) -> Path:
    """Persist one immutable run record; return the ``scenarios.json`` path.

    Creates ``<runs_root>/<stamp>/`` exclusively (``os.makedirs(...,
    exist_ok=False)``) and writes ``scenarios.json`` with ``O_CREAT|O_EXCL``,
    so a pre-existing run dir or record raises :class:`PersistError` instead
    of being overwritten.  ``stamp`` overrides the automatic microsecond
    timestamp (tests pin it); when ``stamp`` is ``None`` a ``%Y%m%d-%H%M%S-%f``
    name is used, and a collision (same microsecond) retries with a
    ``-<6-hex>`` random suffix up to :data:`MAX_SUFFIX_RETRIES` times before
    raising.  The run record is written as indented JSON (guide §3.3).

    ``run_dir`` accepts a directory already created by
    :func:`prepare_run_dir` (the engine's per-run artifact staging, gap
    T-16); the exclusive ``scenarios.json`` write then lands beside the
    collected ``artifacts/``.  When omitted, a fresh exclusive dir is created
    from ``runs_root`` exactly as before.
    """
    if run_dir is None:
        run_dir = prepare_run_dir(runs_root, stamp=stamp)
    record_path = run_dir / "scenarios.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(record_path, flags, 0o644)
    except FileExistsError:
        raise PersistError(
            f"run record already exists, refusing to overwrite: {record_path}"
        ) from None
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(run_record, fh, indent=2)
    return record_path


def write_latest_pointer(runs_root: Path, run_dir_name: str) -> Path:
    """Refresh the stable ``latest.txt`` pointer; return its path.

    The pointer names the newest run directory for trend diffs (guide §3.1
    phase 6 + §3.5).  It is ``latest.txt``, NOT ``latest.json`` (guide §5.4
    citation trap), and it is a convenience, never a claim of exclusivity:
    overwriting it is intended — the immutable run directories are the
    history.
    """
    pointer = runs_root / "latest.txt"
    pointer.write_text(run_dir_name, encoding="utf-8")
    return pointer


def latest_run(runs_root: Path) -> str | None:
    """Return the run dir name named by ``latest.txt``; ``None`` if absent/empty."""
    pointer = runs_root / "latest.txt"
    try:
        content = pointer.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    name = content.strip()
    return name or None


def list_runs(runs_root: Path) -> list[str]:
    """List run dir names newest-first (guide §3.5).

    Only directories that contain a ``scenarios.json`` record count as runs;
    the timestamp names sort correctly in descending lexicographic order (a
    random-suffixed name sorts after its base stamp, which is also its
    creation order).  A missing root is an empty list.
    """
    if not runs_root.is_dir():
        return []
    names = [
        entry.name
        for entry in runs_root.iterdir()
        if entry.is_dir() and (entry / "scenarios.json").is_file()
    ]
    names.sort(reverse=True)
    return names


def collect_artifacts(
    step: Step,
    step_index: int,
    run_dir: Path,
    *,
    cwd: Path,
) -> list[dict[str, object]]:
    """Copy a GREEN step's artifacts into the run dir; return one entry per check.

    Each ``collect_artifacts`` entry is copied from ``cwd / path`` (an
    absolute ``path`` is used as-is) to
    ``<run_dir>/artifacts/<step_index>-<basename>`` (guide §4.4: every green
    step names a verifiable artifact).  ``step_index`` is the 1-based step
    index of the trace (guide §3.1 phase 5).  ``copied_to`` is the created
    file's path, which lives inside the run dir.

    The returned entries carry ``{path, copied_to, ok, required, reason}``:
    ``ok=True`` means the artifact was copied; a missing source is ``ok=False``
    with ``reason="missing"`` and an existing non-file source is
    ``reason="not-a-file"``.  A missing REQUIRED artifact must be surfaced
    loudly by the caller (engine run record); ``required=False`` entries are
    tolerated the same way — both are reported, never silently dropped.
    Copies are exclusive-create: an existing target is never overwritten, so
    two same-basename sources stay distinct files.
    """
    entries: list[dict[str, object]] = []
    for check in step.collect_artifacts:
        source = cwd / check.path
        entry: dict[str, object] = {
            "path": check.path,
            "copied_to": None,
            "ok": False,
            "required": check.required,
            "reason": None,
        }
        if not source.exists():
            entry["reason"] = "missing"
        elif not source.is_file():
            entry["reason"] = "not-a-file"
        else:
            artifacts_dir = run_dir / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            target = _copy_artifact_exclusive(artifacts_dir, step_index, source)
            entry["ok"] = True
            entry["copied_to"] = str(target)
        entries.append(entry)
    return entries


def _copy_artifact_exclusive(artifacts_dir: Path, step_index: int, source: Path) -> Path:
    """Copy ``source`` into ``artifacts_dir`` under a fresh, non-overwritten name.

    The target ``<step_index>-<basename>`` is created with ``O_CREAT|O_EXCL``;
    a collision (same step index and basename) falls back to a ``-<6-hex>``
    suffix for up to :data:`MAX_SUFFIX_RETRIES` attempts, so an existing
    artifact is never overwritten.  Returns the created target.
    """
    base = f"{step_index}-{source.name}"
    for attempt in range(MAX_SUFFIX_RETRIES + 1):
        target = artifacts_dir / (base if attempt == 0 else _suffixed_name(base))
        try:
            _copy_exclusive(source, target)
        except FileExistsError:
            continue
        return target
    raise PersistError(
        f"could not allocate a unique artifact name for {source} in "
        f"{artifacts_dir} after {MAX_SUFFIX_RETRIES + 1} attempts (base {base!r})"
    )


def _suffixed_name(base: str) -> str:
    """Collision fallback: ``1-report.md`` -> ``1-report-<6-hex>.md``."""
    path = Path(base)
    return f"{path.stem}-{token_hex(3)}{path.suffix}"


def _copy_exclusive(source: Path, target: Path) -> None:
    """Byte-copy ``source`` to ``target`` created with ``O_CREAT|O_EXCL``.

    Raises :class:`FileExistsError` when ``target`` already exists (never
    truncates) and removes the partial target if the copy fails.  Metadata is
    preserved, matching the ``shutil.copy2`` semantics this replaces.
    """
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    shutil.copystat(source, target)


def _exclusive_run_dir(runs_root: Path, name: str) -> Path:
    """Create ``<runs_root>/<name>`` exclusively; :class:`PersistError` on collision."""
    run_dir = runs_root / name
    try:
        os.makedirs(run_dir, exist_ok=False)
    except FileExistsError:
        raise PersistError(
            f"run directory already exists, refusing to overwrite: {run_dir}"
        ) from None
    return run_dir


def _fresh_run_dir(runs_root: Path) -> Path:
    """Create a uniquely-named run dir: microsecond stamp, then random suffixes."""
    base = _stamp_now()
    for attempt in range(MAX_SUFFIX_RETRIES + 1):
        name = base if attempt == 0 else f"{base}-{token_hex(3)}"
        try:
            return _exclusive_run_dir(runs_root, name)
        except PersistError:
            continue
    raise PersistError(
        f"could not create a unique run directory under {runs_root} "
        f"after {MAX_SUFFIX_RETRIES + 1} attempts (base stamp {base!r})"
    )


def _stamp_now() -> str:
    """Current time as the run stamp ``%Y%m%d-%H%M%S-%f``.

    ``datetime.strftime`` is used because glibc ``time.strftime`` does not
    support the ``%f`` microsecond directive (it would pass through
    literally).  Kept as a module-level seam so tests can freeze it.
    """
    return datetime.now().strftime(RUN_STAMP_FORMAT)
