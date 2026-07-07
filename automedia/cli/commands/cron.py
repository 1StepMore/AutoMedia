"""``automedia cron`` — run cron jobs and health checks."""

from __future__ import annotations

import shutil
import subprocess

import typer

app = typer.Typer(name="cron", help="Run scheduled jobs and health checks.")

# ---------------------------------------------------------------------------
# Known cron jobs
# ---------------------------------------------------------------------------

_KNOWN_JOBS: dict[str, str] = {
    "pool-collect": "Collect new topics into the pool.",
    "pool-score": "Score and rank pool topics.",
    "pool-prune": "Prune stale pool entries.",
    "publish-check": "Check for unpublished ready content.",
}


# ---------------------------------------------------------------------------
# cron run
# ---------------------------------------------------------------------------

@app.command("run")
def cron_run(
    job_name: str = typer.Argument(..., help="Name of the cron job to execute."),
    timeout: int = typer.Option(120, "--timeout", help="Job timeout in seconds."),
) -> None:
    """Execute a named cron job."""
    if job_name not in _KNOWN_JOBS:
        typer.secho(
            f"Unknown job {job_name!r}. Known jobs: {list(_KNOWN_JOBS)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Running cron job: {job_name} — {_KNOWN_JOBS[job_name]}")

    # Dispatch to the appropriate handler
    handlers: dict[str, Callable[[], None]] = {
        "pool-collect": _job_pool_collect,
        "pool-score": _job_pool_score,
        "pool-prune": _job_pool_prune,
        "publish-check": _job_publish_check,
    }

    try:
        handlers[job_name]()
    except Exception as exc:
        typer.secho(f"Job {job_name!r} failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"Job {job_name!r} completed.", fg=typer.colors.GREEN)


def _job_pool_collect() -> None:
    """Stub: collect topics from external sources."""
    typer.echo("  [pool-collect] No collectors configured — skipping.")


def _job_pool_score() -> None:
    """Stub: score pool topics."""
    typer.echo("  [pool-score] Scoring not yet implemented — skipping.")


def _job_pool_prune() -> None:
    """Stub: prune old pool entries."""
    typer.echo("  [pool-prune] Pruning not yet implemented — skipping.")


def _job_publish_check() -> None:
    """Stub: check for content ready to publish."""
    typer.echo("  [publish-check] No publish queue — skipping.")


# Allow typing for handler dict
from typing import Callable  # noqa: E402


# ---------------------------------------------------------------------------
# cron check-health
# ---------------------------------------------------------------------------

@app.command("check-health")
def cron_check_health() -> None:
    """Run a 4-step health check of the AutoMedia system."""
    checks: list[tuple[str, bool, str]] = []

    # 1. Python version
    import sys
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python >= 3.11", py_ok, f"{sys.version_info.major}.{sys.version_info.minor}"))

    # 2. ffmpeg available
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_ok = ffmpeg_path is not None
    checks.append(("ffmpeg available", ffmpeg_ok, ffmpeg_path or "not found"))

    # 3. Config directory exists
    from pathlib import Path
    config_ok = Path(".automedia").is_dir()
    checks.append((".automedia/ directory", config_ok, "exists" if config_ok else "missing"))

    # 4. Pool DB accessible
    pool_db_path = Path(".automedia") / "pool.db"
    pool_ok = pool_db_path.is_file()
    checks.append(("pool.db accessible", pool_ok, str(pool_db_path)))

    # Print results
    typer.echo("Health Check:")
    typer.echo("-" * 50)
    all_ok = True
    for name, ok, detail in checks:
        icon = "✓" if ok else "✗"
        colour = typer.colors.GREEN if ok else typer.colors.RED
        typer.secho(f"  {icon} {name}: {detail}", fg=colour)
        if not ok:
            all_ok = False

    if not all_ok:
        typer.secho("\nSome checks failed.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho("\nAll checks passed.", fg=typer.colors.GREEN)
