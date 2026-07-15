"""User-friendly error formatting for the AutoMedia CLI.

Replaces raw Python tracebacks in user-facing output with concise,
actionable error messages. Full tracebacks are still captured by
structlog and are shown only when the caller passes ``--verbose``.

Usage::

    from automedia.cli.output_format import output_formatted_error

    try:
        ...
    except Exception as exc:
        output_formatted_error(
            "Pipeline failed",
            error=str(exc),
            verbose=verbose,
            exc_info=exc,
            gates_log=result.gates_log if result else None,
        )
"""

from __future__ import annotations

import sys
import traceback

import typer

from automedia.pipelines.gate_engine import GateLogEntry

# Known gate name prefixes for pattern matching in error strings.
_GATE_PREFIXES = [
    "pre-gate",
    "CW",
    "D0",
    "G0", "G1", "G2", "G3", "G4", "G5",
    "V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "L1", "L2", "L3", "L4",
]


def output_formatted_error(
    summary: str,
    *,
    error: str = "",
    verbose: bool = False,
    exc_info: BaseException | None = None,
    gates_log: list[GateLogEntry] | None = None,
) -> None:
    """Print a user-friendly error message to stderr.

    Parameters
    ----------
    summary:
        Short description of what failed (e.g. ``"Pipeline failed"``).
    error:
        Raw error string from the exception or result.
    verbose:
        When ``True`` the full Python traceback is also printed.
    exc_info:
        The original exception (if any) for traceback rendering.
    gates_log:
        Optional gate log entries from a ``PipelineResult``.  Used to
        identify the failing gate and provide a concrete suggestion.
    """
    gate_name = _failing_gate(error, gates_log)

    if gate_name:
        _print(
            f"{summary} at {gate_name} \u274c {error}",
            bold_part=gate_name,
        )
        _print(
            f"  Suggestion: Use --resume-from {gate_name} to retry after fixing.",
            bold_part=f"--resume-from {gate_name}",
        )
    elif error:
        _print(f"{summary}: {error}")
        _print("  Run with --verbose for details.", bold_part="--verbose")
    else:
        _print(f"{summary}.")
        _print("  Run with --verbose for details.", bold_part="--verbose")

    if verbose:
        typer.secho("\n--- verbose traceback ---", fg=typer.colors.YELLOW, err=True)
        if exc_info is not None:
            traceback.print_exception(
                type(exc_info), exc_info, exc_info.__traceback__, file=sys.stderr,
            )
        else:
            traceback.print_stack(file=sys.stderr)


def output_pipeline_error(
    result_error: str,
    *,
    gates_log: list[GateLogEntry] | None = None,
    verbose: bool = False,
) -> None:
    """Print a user-friendly error from a failed ``PipelineResult.error``.

    This is the common case: the pipeline ran but one or more gates
    failed.  The error is already a string on the result object.
    """
    gate_name = _failing_gate(result_error, gates_log)

    if gate_name:
        _print(
            f"Pipeline stopped at {gate_name} \u274c {result_error}",
            bold_part=gate_name,
        )
        _print(
            f"  Use --resume-from {gate_name} to retry after fixing.",
            bold_part=f"--resume-from {gate_name}",
        )
    else:
        _print(f"Pipeline failed: {result_error}")

    if verbose:
        typer.secho(
            "\n(no additional traceback \u2014 error captured from pipeline result)",
            fg=typer.colors.YELLOW,
            err=True,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _print(msg: str, *, bold_part: str = "") -> None:
    """Print *msg* in red to stderr, optionally highlighting *bold_part* in bold.

    When *bold_part* is found inside *msg* it is wrapped in ANSI bold
    escapes so it stands out in the terminal.
    """
    if bold_part and bold_part in msg:
        prefix, _, suffix = msg.partition(bold_part)
        typer.secho(prefix, fg=typer.colors.RED, err=True, nl=False)
        typer.secho(bold_part, fg=typer.colors.RED, bold=True, err=True, nl=False)
        typer.secho(suffix, fg=typer.colors.RED, err=True)
    else:
        typer.secho(msg, fg=typer.colors.RED, err=True)


def _failing_gate(
    error: str,
    gates_log: list[GateLogEntry] | None,
) -> str | None:
    """Return the name of the first non-passed gate, or ``None``."""
    if gates_log:
        for entry in gates_log:
            if entry.status != "passed":
                name = entry.gate_name
                if error and name in error:
                    return name
                return name

    # Fallback: try to match a known gate prefix in the error string.
    if error:
        for prefix in _GATE_PREFIXES:
            if prefix in error:
                return prefix

    return None
