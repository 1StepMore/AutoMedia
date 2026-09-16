"""``automedia cron`` — run cron jobs and health checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
import yaml

from automedia.cli.output import OutputMode, get_output_mode, output_error, output_text
from automedia.cron.schedule import is_schedule_due
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
    "run-pipeline": "Execute a scheduled pipeline run from cron/jobs.yaml.",
    "run-distribute": "Execute scheduled distribution commands from cron/jobs.yaml.",
}

_DEFAULT_DB = Path(".automedia") / "pool.db"


# ---------------------------------------------------------------------------
# cron run
# ---------------------------------------------------------------------------


@app.command("run")
def cron_run(
    job_name: str | None = typer.Argument(None, help="Name of the cron job to execute."),
    due: bool = typer.Option(
        False,
        "--due",
        help="Run every schedule entry due now (the external crond contract).",
    ),
    timeout: int = typer.Option(120, "--timeout", help="Job timeout in seconds."),
) -> None:
    """Execute a named cron job, or every schedule entry due now (``--due``)."""
    if due:
        _run_due_command()
        return

    if job_name is None:
        output_error(f"Provide a job name or --due. Known jobs: {list(_KNOWN_JOBS)}")
        return

    if job_name not in _KNOWN_JOBS:
        output_error(f"Unknown job {job_name!r}. Known jobs: {list(_KNOWN_JOBS)}")

    if get_output_mode() == OutputMode.TEXT:
        typer.echo(f"Running cron job: {job_name} — {_KNOWN_JOBS[job_name]}")

    try:
        _due_handlers()[job_name]()
    except Exception as exc:
        output_error(f"Job {job_name!r} failed: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    output_text(
        f"Job {job_name!r} completed.",
        data={"status": "ok", "job": job_name},
        green=True,
    )


# ---------------------------------------------------------------------------
# --due dispatch
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    """Injectable clock seam — tests monkeypatch this to a fixed instant."""
    return datetime.now(UTC)


def _due_handlers() -> dict[str, Callable[[], None]]:
    """Handler map for named jobs, built per call so tests can patch module attrs."""
    return {
        "pool-collect": _job_pool_collect,
        "pool-score": _job_pool_score,
        "pool-prune": _job_pool_prune,
        "publish-check": _job_publish_check,
        "watchdog": _job_watchdog,
        "run-pipeline": _job_run_pipeline,
        "run-distribute": _job_run_distribute,
        "check-health": cron_check_health,
    }


def _run_due_command() -> None:
    now = _utcnow()
    ran, failed = _run_due_jobs(now)

    if get_output_mode() == OutputMode.TEXT:
        typer.echo(f"cron --due: {ran} entr{'y' if ran == 1 else 'ies'} due, {failed} failed.")

    output_text(
        None,
        data={
            "status": "failed" if failed else "ok",
            "due": ran,
            "failed": failed,
            "now": now.isoformat(),
        },
        green=not failed,
    )

    if failed:
        raise typer.Exit(code=1)


def _run_due_jobs(now: datetime) -> tuple[int, int]:
    """Dispatch every entry due at *now*; return ``(dispatched, failed)``.

    Two sources are consulted, both from the canonical schedule store:

    1. The static ``jobs:`` list (canonical file, package ``cron/jobs.yaml``
       fallback) — dispatched to their in-process handlers.
    2. The ``pipeline_schedules:`` list — ``kind=="pipeline"`` entries go through
       the pool→pipeline bridge (:func:`run_scheduled_pipeline`), while
       ``kind=="distribute"`` entries execute their stored command.
    """
    from automedia.cron.runner import run_scheduled_pipeline
    from automedia.mcp.tools import _read_pipeline_schedules

    dispatched = 0
    failed = 0

    for job in _read_static_jobs():
        if not is_schedule_due(str(job.get("schedule", "")), now):
            continue
        name = str(job.get("name", "unnamed"))
        handler_name = _resolve_due_handler(job)
        if handler_name is None:
            typer.secho(
                f"  [cron --due] {name!r} is due but maps to no known handler "
                f"(command={job.get('command', '')!r}); skipping.",
                fg=typer.colors.YELLOW,
            )
            continue
        dispatched += 1
        if not _invoke_due_handler(name, handler_name):
            failed += 1

    for entry in _read_pipeline_schedules():
        if not is_schedule_due(str(entry.get("expression", "")), now):
            continue
        name = str(entry.get("name", "unnamed"))
        dispatched += 1

        if entry.get("kind") == "distribute":
            if _execute_distribute_entry(dict(entry)).get("status") != "success":
                failed += 1
            continue

        typer.echo(f"  [cron --due] Running pipeline schedule: {name!r} ...")
        try:
            result = run_scheduled_pipeline(dict(entry))
        except Exception as exc:
            typer.secho(f"  [cron --due] {name!r} EXCEPTION: {exc}", fg=typer.colors.RED)
            failed += 1
            continue
        if result.get("status") == "failed":
            typer.secho(
                f"  [cron --due] {name!r} FAILED: {result.get('error', 'unknown error')}",
                fg=typer.colors.RED,
            )
            failed += 1

    return dispatched, failed


def _invoke_due_handler(name: str, handler_name: str) -> bool:
    """Run one due handler, returning ``True`` on success; never raises."""
    handler = _due_handlers().get(handler_name)
    if handler is None:
        return False
    try:
        handler()
    except Exception as exc:
        typer.secho(f"  [cron --due] Job {name!r} failed: {exc}", fg=typer.colors.RED)
        return False
    return True


def _resolve_due_handler(job: Mapping[str, Any]) -> str | None:
    handlers = _due_handlers()
    tokens = str(job.get("command", "")).split()
    if "cron" in tokens:
        remainder = tokens[tokens.index("cron") + 1 :]
        candidate = (
            remainder[1] if remainder and remainder[0] == "run" and len(remainder) > 1 else ""
        ) or (remainder[0] if remainder else "")
        if candidate in handlers:
            return candidate

    name = str(job.get("name", ""))
    if name in handlers:
        return name
    return None


def _read_static_jobs() -> list[dict[str, Any]]:
    """Read the static ``jobs:`` list from the canonical store (package fallback)."""
    from automedia.mcp.tools._shared import _get_jobs_yaml_path, _get_package_jobs_yaml_path

    for path in (_get_jobs_yaml_path(), _get_package_jobs_yaml_path()):
        data = _load_yaml_mapping(path)
        jobs = data.get("jobs") if data else None
        if isinstance(jobs, list) and jobs:
            return [dict(job) for job in jobs if isinstance(job, dict)]
    return []


def _load_yaml_mapping(path: Path) -> dict[str, Any] | None:
    """Best-effort load of a YAML mapping; returns ``None`` on any failure."""
    if not path.is_file():
        return None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    return loaded if isinstance(loaded, dict) else None


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
# Job: run-pipeline (cron dispatcher path — runs all schedules)
# ---------------------------------------------------------------------------


def _job_run_pipeline() -> None:
    """Execute all pipeline schedules from ``cron/jobs.yaml``.

    Reads every schedule defined in ``pipeline_schedules`` and runs
    each one sequentially.  Per-schedule errors are collected and
    reported — a single failing schedule does **not** stop the batch.
    """
    from automedia.cron.runner import run_scheduled_pipeline
    from automedia.mcp.tools import _read_pipeline_schedules

    schedules = [s for s in _read_pipeline_schedules() if s.get("kind", "pipeline") != "distribute"]
    if not schedules:
        typer.echo("  [run-pipeline] No pipeline schedules defined in cron/jobs.yaml.")
        return

    results: list[dict[str, Any]] = []
    for entry in schedules:
        name = entry.get("name", "unnamed")
        typer.echo(f"  [run-pipeline] Running schedule: {name!r} ...")
        try:
            res = run_scheduled_pipeline(dict(entry))
            results.append(res)
            status = res.get("status", "unknown")
            if status == "failed":
                typer.secho(
                    f"  [run-pipeline] {name!r} FAILED: {res.get('error', 'unknown error')}",
                    fg=typer.colors.RED,
                )
            else:
                typer.echo(
                    f"  [run-pipeline] {name!r} → {status}  "
                    f"(topic={res.get('topic', '')}, "
                    f"project_id={res.get('project_id', '')})"
                )
        except Exception as exc:
            typer.secho(
                f"  [run-pipeline] {name!r} EXCEPTION: {exc}",
                fg=typer.colors.RED,
            )
            results.append(
                {
                    "status": "failed",
                    "error": {
                        "code": "CLI_ERROR",
                        "message": str(exc),
                        "resolution": "Check the error message and fix the issue before retrying",
                    },
                    "name": name,
                }
            )

    passed = sum(1 for r in results if r.get("status") in ("success", "partial"))
    failed = len(results) - passed
    typer.echo(
        f"  [run-pipeline] Batch complete: {passed} passed, {failed} failed "
        f"(out of {len(results)} schedules)."
    )


# ---------------------------------------------------------------------------
# Job: run-distribute
# ---------------------------------------------------------------------------


def _job_run_distribute() -> None:
    """Execute scheduled distribution commands from pipeline_schedules.

    Reads every schedule entry in ``pipeline_schedules`` that has a
    ``command`` field starting with ``automedia distribute`` and executes
    it via ``subprocess.run``.  Per-entry errors are collected and
    reported — a single failure does not stop the batch.
    """
    from automedia.mcp.tools import _read_pipeline_schedules

    schedules = _read_pipeline_schedules()
    distribute_entries = [s for s in schedules if s.get("kind") == "distribute"]

    if not distribute_entries:
        typer.echo("  [run-distribute] No scheduled distributions found.")
        return

    results = [_execute_distribute_entry(dict(entry)) for entry in distribute_entries]

    passed = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - passed
    typer.echo(
        f"  [run-distribute] Batch complete: {passed} passed, {failed} failed "
        f"(out of {len(results)} entries)."
    )


def _execute_distribute_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Run one ``kind=="distribute"`` entry; return its result dict (never raises)."""
    name = entry.get("name", "unnamed")
    command = entry.get("command", "")
    typer.echo(f"  [run-distribute] Executing: {name!r} ...")

    try:
        proc = subprocess.run(  # noqa: S602 — command strings come from trusted pipeline schedule config
            command,
            shell=True,  # nosec B602 — command from trusted pipeline schedule config
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode == 0:
            typer.echo(f"  [run-distribute] {name!r} → ok")
            return {"name": name, "status": "success"}
        error_msg = proc.stderr.strip() or f"exit code {proc.returncode}"
        typer.secho(
            f"  [run-distribute] {name!r} FAILED: {error_msg}",
            fg=typer.colors.RED,
        )
        return {"name": name, "status": "failed", "error": error_msg}
    except subprocess.TimeoutExpired:
        typer.secho(
            f"  [run-distribute] {name!r} TIMEOUT (exceeded 600s)",
            fg=typer.colors.RED,
        )
        return {"name": name, "status": "failed", "error": "timeout"}
    except Exception as exc:
        typer.secho(
            f"  [run-distribute] {name!r} EXCEPTION: {exc}",
            fg=typer.colors.RED,
        )
        return {"name": name, "status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------
# cron run-pipeline (standalone command)
# ---------------------------------------------------------------------------


@app.command("run-pipeline")
def cron_run_pipeline(
    name: str = typer.Option(
        "",
        "--name",
        "-n",
        help="Schedule name to run (empty = run all schedules).",
    ),
    pool_db_path: str = typer.Option(
        "",
        "--pool-db",
        help="Explicit path to the topic pool SQLite database.",
    ),
) -> None:
    """Execute a scheduled pipeline run from ``cron/jobs.yaml``.

    Reads the ``pipeline_schedules`` section of the cron YAML config,
    selects a topic from the pool, runs the full pipeline with the
    configured **mode**, and optionally publishes to a **platform**.

    When ``--name`` is provided only that schedule is executed.
    When ``--name`` is empty **all** schedules are executed sequentially.
    """
    from automedia.cron.runner import run_scheduled_pipeline
    from automedia.mcp.tools import _read_pipeline_schedules

    schedules = _read_pipeline_schedules()
    if not schedules:
        output_error("No pipeline schedules found in cron/jobs.yaml.")

    if name:
        matched = [s for s in schedules if s.get("name") == name]
        if not matched:
            available = [s.get("name", "?") for s in schedules]
            output_error(f"Schedule {name!r} not found. Available schedules: {available}")
        entries = matched
    else:
        entries = schedules

    results: list[dict[str, Any]] = []
    for entry in entries:
        sched_name = entry.get("name", "unnamed")
        if get_output_mode() == OutputMode.TEXT:
            typer.echo(f"Running pipeline schedule: {sched_name!r}")

        try:
            res = run_scheduled_pipeline(dict(entry), pool_db_path=pool_db_path)
            results.append(res)

            if output_text(None, data=res):
                continue

            status = res.get("status", "unknown")
            if status == "failed":
                typer.secho(
                    f"  ✗ {sched_name!r} failed: {res.get('error', 'unknown')}",
                    fg=typer.colors.RED,
                )
            else:
                typer.secho(
                    f"  ✓ {sched_name!r} → {status}  "
                    f"(topic={res.get('topic', '')}, "
                    f"project_id={res.get('project_id', '')})",
                    fg=typer.colors.GREEN,
                )
        except Exception as exc:
            error_dict = {
                "code": "CLI_ERROR",
                "message": str(exc),
                "resolution": "Check the error message and fix the issue before retrying",
            }
            results.append({"status": "failed", "error": error_dict, "name": sched_name})
            output_text(
                f"  ✗ {sched_name!r} exception: {exc}",
                data={"status": "failed", "error": error_dict, "name": sched_name},
            )

    if output_text(None, data={"results": results, "count": len(results)}):
        failed = sum(1 for r in results if r.get("status") == "failed")
        if failed:
            raise typer.Exit(code=1)
        return

    passed = sum(1 for r in results if r.get("status") in ("success", "partial"))
    failed = len(results) - passed
    if failed:
        typer.secho(
            f"\n{passed}/{len(results)} schedules completed, {failed} failed.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    typer.secho(
        f"\nAll {len(results)} schedule(s) completed successfully.",
        fg=typer.colors.GREEN,
    )


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
