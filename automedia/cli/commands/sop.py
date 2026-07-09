"""``automedia sop`` — SOP document generation CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from automedia.sop.runner import SOPRunner

app = typer.Typer(name="sop", help="SOP document generation.")


# ---------------------------------------------------------------------------
# sop generate          → execution handbook
# ---------------------------------------------------------------------------


@app.command("generate")
def sop_generate(
    brand: str = typer.Option(..., "--brand", help="Brand identifier"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output directory (default: ~/.automedia/sop/<brand>/)"
    ),
) -> None:
    """Generate an execution handbook for *brand*."""
    runner = SOPRunner(brand)
    handbook = runner.generate_execution_handbook()

    output_dir = Path(output) if output else Path.home() / ".automedia" / "sop" / brand
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "execution_handbook.md"
    out_path.write_text(handbook, encoding="utf-8")
    typer.secho(f"Handbook generated: {out_path}", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# sop generate-daily    → daily tasks YAML
# ---------------------------------------------------------------------------


@app.command("generate-daily")
def sop_generate_daily(
    brand: str = typer.Option(..., "--brand", help="Brand identifier"),
    date: str = typer.Option(
        "", "--date", "-d", help="Date string (YYYY-MM-DD). Defaults to today."
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output directory (default: ~/.automedia/sop/<brand>/)"
    ),
) -> None:
    """Generate daily tasks for *brand* as YAML."""
    runner = SOPRunner(brand)
    daily = runner.generate_daily_tasks(date)

    output_dir = Path(output) if output else Path.home() / ".automedia" / "sop" / brand
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "daily_tasks.yaml"
    out_path.write_text(daily, encoding="utf-8")
    typer.secho(f"Daily tasks generated: {out_path}", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# sop generate-report   → progress report
# ---------------------------------------------------------------------------


@app.command("generate-report")
def sop_generate_report(
    brand: str = typer.Option(..., "--brand", help="Brand identifier"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output directory (default: ~/.automedia/sop/<brand>/)"
    ),
) -> None:
    """Generate a progress report for *brand*."""
    runner = SOPRunner(brand)
    report = runner.generate_progress_report()

    output_dir = Path(output) if output else Path.home() / ".automedia" / "sop" / brand
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "progress_report.md"
    out_path.write_text(report, encoding="utf-8")
    typer.secho(f"Progress report generated: {out_path}", fg=typer.colors.GREEN)
