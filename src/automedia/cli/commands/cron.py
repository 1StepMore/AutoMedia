"""``automedia cron`` — run cron jobs and health checks."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from automedia.cli.output import OutputMode, get_output_mode, output_error, output_text
from automedia.pool.collector import HotCollector
from automedia.pool.db import PoolDB
from automedia.pool.dedup import TopicDeduplicator
from automedia.pool.scorer import TopicScorer

app = typer.Typer(name="cron", help="Run scheduled jobs and health checks.")

# ---------------------------------------------------------------------------
# Known cron jobs
# ---------------------------------------------------------------------------

_KNOWN_JOBS: dict[str, str] = {
    "pool-collect": "Collect new topics into the pool.",
    "pool-score": "Score and rank pool topics.",
    "pool-prune": "Prune stale pool entries.",
    "publish-check": "Check for unpublished ready content.",
    "watchdog": "Run the 4-step system health check (alias for check-health).",
}

_DEFAULT_DB = Path(".automedia") / "pool.db"


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
        output_error(f"Unknown job {job_name!r}. Known jobs: {list(_KNOWN_JOBS)}")

    if get_output_mode() == OutputMode.TEXT:
        typer.echo(f"Running cron job: {job_name} — {_KNOWN_JOBS[job_name]}")

    # Dispatch to the appropriate handler
    handlers: dict[str, Callable[[], None]] = {
        "pool-collect": _job_pool_collect,
        "pool-score": _job_pool_score,
        "pool-prune": _job_pool_prune,
        "publish-check": _job_publish_check,
        "watchdog": _job_watchdog,
    }

    try:
        handlers[job_name]()
    except Exception as exc:
        output_error(f"Job {job_name!r} failed: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    output_text(
        f"Job {job_name!r} completed.",
        data={"status": "ok", "job": job_name},
        green=True,
    )


# ---------------------------------------------------------------------------
# Job: pool-collect
# ---------------------------------------------------------------------------


def _job_pool_collect() -> None:
    """Collect hot topics from HotCollector and persist them into pool.db.

    Uses :class:`TopicDeduplicator` to avoid inserting titles that already
    exist in the pool.
    """
    db = PoolDB(_DEFAULT_DB)
    try:
        collector = HotCollector()
        topics = collector.collect_all()

        dedup = TopicDeduplicator()
        existing = db.list_topics()
        existing_titles = [t["title"] for t in existing]

        inserted = 0
        skipped = 0
        for t in topics:
            if dedup.is_duplicate(t["title"], existing_titles):
                skipped += 1
                continue
            db.add_topic(
                {
                    "title": t["title"],
                    "url": t.get("url", ""),
                    "source": t.get("source", ""),
                    "score": t.get("heat_score", 0.0),
                    "status": "pending",
                }
            )
            existing_titles.append(t["title"])
            inserted += 1

        typer.echo(
            f"  [pool-collect] Collected {len(topics)} topics: "
            f"{inserted} inserted, {skipped} dedup-skipped."
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Job: pool-score
# ---------------------------------------------------------------------------


def _job_pool_score() -> None:
    """Score all pending topics using :class:`TopicScorer` and update pool.db.

    Growth score is stored as the primary ``score`` column value.
    """
    db = PoolDB(_DEFAULT_DB)
    try:
        scorer = TopicScorer()
        pending = db.list_topics(status="pending")

        scored = 0
        for t in pending:
            # Build the topic dict expected by TopicScorer
            score_input = {
                "title": t["title"],
                "heat_score": t.get("score", 0.0),
                "collected_at": t.get("created_at", ""),
            }
            growth = scorer.score_growth(score_input)
            db.update_score(t["id"], round(growth, 4))
            scored += 1

        typer.echo(f"  [pool-score] Scored {scored} pending topic(s).")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Job: pool-prune
# ---------------------------------------------------------------------------


def _job_pool_prune() -> None:
    """Remove stale pending topics older than 7 days from pool.db."""
    db = PoolDB(_DEFAULT_DB)
    try:
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        # Collect IDs of topics to prune
        cur = db.conn.execute(
            "SELECT id FROM topics WHERE status = 'pending' AND created_at < ?",
            (cutoff,),
        )
        ids = [row[0] for row in cur.fetchall()]
        removed = db.delete_topics(ids)

        typer.echo(f"  [pool-prune] Removed {removed} stale pending topic(s).")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Job: publish-check
# ---------------------------------------------------------------------------


def _job_publish_check() -> None:
    """Scan for projects that have ``selected`` topics awaiting publish.

    Reports the count of selected topics in pool.db and any project
    directories with a ``06_publish`` sub-directory that is empty
    (i.e. content produced but not yet published).
    """
    db = PoolDB(_DEFAULT_DB)
    try:
        selected = db.list_topics(status="selected")
        typer.echo(
            f"  [publish-check] {len(selected)} topic(s) in 'selected' status awaiting publish."
        )

        # Scan for project dirs with empty 06_publish (content ready, not published)
        ready_projects: list[str] = []
        base = Path(".")
        for info_file in sorted(base.glob("*/00_project_info.json")):
            proj_dir = info_file.parent
            publish_dir = proj_dir / "06_publish"
            if publish_dir.is_dir() and not any(publish_dir.iterdir()):
                ready_projects.append(proj_dir.name)

        if ready_projects:
            typer.echo(
                f"  [publish-check] {len(ready_projects)} project(s) with empty publish dir:"
            )
            for name in ready_projects:
                typer.echo(f"    - {name}")
        else:
            typer.echo("  [publish-check] No projects pending publish.")
    finally:
        db.close()


def _job_watchdog() -> None:
    """Delegate to the check-health command handler."""
    cron_check_health()


# ---------------------------------------------------------------------------
# cron check-health
# ---------------------------------------------------------------------------


@app.command("check-health")
def cron_check_health() -> None:
    """Run a 4-step health check of the AutoMedia system."""
    checks: list[tuple[str, bool, str]] = []

    # 1. Config directory exists
    config_dir = Path(".automedia")
    config_ok = config_dir.is_dir()
    checks.append((".automedia/ config directory", config_ok, "exists" if config_ok else "missing"))

    # 2. Pool DB accessible
    pool_db_path = _DEFAULT_DB
    pool_ok = False
    pool_detail = str(pool_db_path)
    if pool_db_path.is_file():
        try:
            db = PoolDB(pool_db_path)
            db.conn.execute("SELECT COUNT(*) FROM topics")
            pool_ok = True
            pool_detail = f"{pool_db_path} (queryable)"
            db.close()
        except Exception as exc:
            pool_detail = f"{pool_db_path} (error: {exc})"
    checks.append(("pool.db accessible", pool_ok, pool_detail))

    # 3. Core dependencies installed (python + ffmpeg minimum)
    dep_details: list[str] = []
    dep_ok = True
    py_ok = sys.version_info >= (3, 11)
    if not py_ok:
        dep_ok = False
    dep_details.append(f"python {sys.version_info.major}.{sys.version_info.minor}")
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        dep_ok = False
    dep_details.append(f"ffmpeg={'yes' if ffmpeg_path else 'no'}")
    checks.append(("core dependencies", dep_ok, ", ".join(dep_details)))

    # 4. jobs.yaml valid
    yaml_ok = False
    yaml_detail = "not found"
    import automedia as _am_pkg

    _pkg_root = Path(_am_pkg.__file__).resolve().parent
    jobs_yaml = _pkg_root / "cron" / "jobs.yaml"
    if not jobs_yaml.is_file():
        jobs_yaml = Path("automedia") / "cron" / "jobs.yaml"
    if jobs_yaml.is_file():
        try:
            import yaml

            with open(jobs_yaml, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict) and "jobs" in data and isinstance(data["jobs"], list):
                yaml_ok = True
                yaml_detail = f"{len(data['jobs'])} jobs defined"
            else:
                yaml_detail = "missing 'jobs' key"
        except Exception as exc:
            yaml_detail = f"parse error: {exc}"
    checks.append(("jobs.yaml valid", yaml_ok, yaml_detail))

    all_ok = all(ok for _, ok, _ in checks)

    if output_text(
        None,
        data={
            "status": "ok" if all_ok else "error",
            "checks": [
                {"name": name, "passed": ok, "detail": detail} for name, ok, detail in checks
            ],
        },
    ):
        if not all_ok:
            raise typer.Exit(code=1)
        return

    # Print results
    typer.echo("Health Check:")
    typer.echo("-" * 50)
    for name, ok, detail in checks:
        icon = "✓" if ok else "✗"
        colour = typer.colors.GREEN if ok else typer.colors.RED
        typer.secho(f"  {icon} {name}: {detail}", fg=colour)

    if not all_ok:
        typer.secho("\nSome checks failed.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho("\nAll checks passed.", fg=typer.colors.GREEN)
