"""``automedia pool`` — manage the topic pool database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from automedia.pool.db import PoolDB

app = typer.Typer(name="pool", help="Manage the topic pool database.")

_DEFAULT_DB = Path(".automedia") / "pool.db"


def _get_db(db_path: str | None) -> PoolDB:
    """Open (or create) the PoolDB at the given path."""
    path = Path(db_path) if db_path else _DEFAULT_DB
    return PoolDB(path)


# ---------------------------------------------------------------------------
# pool list
# ---------------------------------------------------------------------------

@app.command("list")
def pool_list(
    status: str | None = typer.Option(
        None, "--status", "-s", help="Filter by status (pending / selected / published)."
    ),
    db_path: str | None = typer.Option(None, "--db", help="Path to pool SQLite file."),
) -> None:
    """List topics in the pool, optionally filtered by status."""
    try:
        db = _get_db(db_path)
        topics = db.list_topics(status=status)
        db.close()
    except Exception as exc:
        typer.secho(f"Error listing pool: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if not topics:
        typer.echo("No topics found.")
        return

    typer.echo(f"{'ID':<6} {'Status':<12} {'Source':<12} {'Title'}")
    typer.echo("-" * 60)
    for t in topics:
        typer.echo(f"{t['id']:<6} {t['status']:<12} {t.get('source', ''):<12} {t['title']}")


# ---------------------------------------------------------------------------
# pool add
# ---------------------------------------------------------------------------

@app.command("add")
def pool_add(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic title."),
    url: str = typer.Option("", "--url", "-u", help="Source URL."),
    source: str = typer.Option("", "--source", "-s", help="Source platform (e.g. weibo)."),
    db_path: str | None = typer.Option(None, "--db", help="Path to pool SQLite file."),
) -> None:
    """Add a new topic to the pool."""
    try:
        db = _get_db(db_path)
        topic_id = db.add_topic({
            "title": topic,
            "url": url,
            "source": source,
        })
        db.close()
    except Exception as exc:
        typer.secho(f"Error adding topic: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"Topic added (id={topic_id}): {topic}", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# pool prune
# ---------------------------------------------------------------------------

@app.command("prune")
def pool_prune(
    days: int = typer.Option(7, "--days", "-d", help="Remove topics older than N days."),
    db_path: str | None = typer.Option(None, "--db", help="Path to pool SQLite file."),
) -> None:
    """Remove stale topics older than *days* days."""
    try:
        db = _get_db(db_path)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = db.conn.execute(
            "DELETE FROM topics WHERE created_at < ? AND status = 'pending'",
            (cutoff,),
        )
        db.conn.commit()
        removed = cur.rowcount
        db.close()
    except Exception as exc:
        typer.secho(f"Error pruning pool: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Pruned {removed} pending topic(s) older than {days} day(s).")
