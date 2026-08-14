"""Director sign-off for agent-tester validation runs (W4-T5).

The framework's final quality gate is the human director's sign-off (guide
§6.4): the validator agent grades, the director disposes.  Signing a run
converts it from a disposable draft into acceptance evidence — a recorded
decision, not a memory.

A sign-off lives in ``<run_dir>/signed.txt`` as one line per sign-off:

    ``<ISO-8601 timestamp> <signer> <verdict>``

e.g. ``2026-08-14T12:00:00 director approved``.  The verdict is free-form
(the director's choice: "approved", "approved-with-waivers", "rejected", ...).

Sign-offs APPEND, never overwrite: the director may re-verify and sign again,
and the sign-off history is immutable — the same immutability philosophy as
the run records themselves (persist_run's exclusive-create).  The report
renderer (W4-T3) consumes :func:`signoff_status` to list unsigned runs.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from automedia.validation.persist import list_runs

SIGN_STAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
"""Sign-off timestamp: ISO-8601 date + time (guide §6.4: run name + date +
verdict; second precision is the pinned format — the line is for human
reading, the run dir stamp already carries microseconds)."""

DEFAULT_SIGNER = "director"
"""Default signer name; any principal may sign (signer is recorded per line)."""

SIGNED_FILENAME = "signed.txt"
"""The per-run sign-off record file inside a run directory."""


class SignoffError(Exception):
    """A sign-off could not be recorded: unknown run or unusable verdict."""


def sign_run(
    runs_root: Path,
    run_name: str,
    verdict: str,
    *,
    signer: str = DEFAULT_SIGNER,
) -> Path:
    """Append one sign-off line to ``<runs_root>/<run_name>/signed.txt``.

    The line is ``<YYYY-MM-DDTHH:MM:SS> <signer> <verdict>`` (one line per
    sign-off; the director may re-verify and sign again).  The file is opened
    in append mode: an existing ``signed.txt`` is NEVER overwritten, and a
    missing one is created.  The run directory itself must already exist
    (a run is evidence; signing a run that was never persisted is an error),
    otherwise :class:`SignoffError` is raised.  An empty/whitespace verdict,
    or one containing a newline (which would corrupt the one-line-per-sign-off
    record format), also raises :class:`SignoffError`.

    Returns the ``signed.txt`` path.
    """
    if not verdict.strip():
        raise SignoffError("sign-off verdict must be a non-empty string")
    if "\n" in verdict or "\r" in verdict:
        raise SignoffError(
            "sign-off verdict must be a single line (one line per sign-off)"
        )
    run_dir = runs_root / run_name
    if not run_dir.is_dir():
        raise SignoffError(
            f"cannot sign unknown run {run_name!r}: run directory does not "
            f"exist: {run_dir}"
        )
    signed_path = run_dir / SIGNED_FILENAME
    line = f"{_stamp_now()} {signer} {verdict}"
    with signed_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return signed_path


def is_signed(runs_root: Path, run_name: str) -> bool:
    """Whether the run has a non-empty ``signed.txt`` (i.e. a recorded verdict)."""
    signed_path = runs_root / run_name / SIGNED_FILENAME
    if not signed_path.is_file():
        return False
    return bool(signed_path.read_text(encoding="utf-8").strip())


def list_unsigned(runs_root: Path) -> list[str]:
    """Run dir names (newest-first, via ``persist.list_runs``) without a sign-off.

    A run counts as unsigned when its ``signed.txt`` is absent or empty — an
    empty file carries no verdict, so it is not evidence of anything.
    """
    return [name for name in list_runs(runs_root) if not is_signed(runs_root, name)]


def signoff_status(runs_root: Path) -> dict[str, dict[str, object]]:
    """Per-run sign-off state for the report renderer (W4-T3).

    Returns ``{run_name: {"run": run_name, "signed": bool,
    "verdict_lines": [str, ...]}}`` for every run (newest-first order from
    ``persist.list_runs``).  ``verdict_lines`` are the raw ``signed.txt``
    lines (the sign-off history, immutable and append-only); an unsigned run
    has ``signed=False`` and ``verdict_lines=[]``.
    """
    status: dict[str, dict[str, object]] = {}
    for name in list_runs(runs_root):
        signed_path = runs_root / name / SIGNED_FILENAME
        verdict_lines = (
            signed_path.read_text(encoding="utf-8").splitlines()
            if signed_path.is_file()
            else []
        )
        status[name] = {
            "run": name,
            "signed": bool(verdict_lines),
            "verdict_lines": verdict_lines,
        }
    return status


def _stamp_now() -> str:
    """Current time as the sign-off stamp ``%Y-%m-%dT%H:%M:%S``.

    Module-level seam so tests can freeze the timestamp (persist.py
    precedent).  ``datetime.strftime`` is used because glibc ``time.strftime``
    does not support the ``%f`` directive (unused here, but the pattern is
    shared).
    """
    return datetime.now().strftime(SIGN_STAMP_FORMAT)
