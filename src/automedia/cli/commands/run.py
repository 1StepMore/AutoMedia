"""``automedia run`` — execute the full production pipeline."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer

from automedia.cli.output import OutputMode, get_output_mode, output_error_json, output_json
from automedia.pipelines.runner import run_full_pipeline

_MODEL_CONFIG_PATH = Path.home() / ".automedia" / "model_config.yaml"


def run_cmd(
    topic: str = typer.Option(..., "--topic", "-t", help="Content topic / subject."),
    brand: str = typer.Option(..., "--brand", "-b", help="Brand identifier."),
    mode: str = typer.Option(
        "auto",
        "--mode",
        "-m",
        help="Pipeline mode: auto, text_only, video_only, qa_only.",
    ),
    decision_mode: str = typer.Option(
        "build",
        "--decision-mode",
        help="Decision layer mode: build or scale.",
    ),
    resume_from: str | None = typer.Option(
        None,
        "--resume-from",
        help="Gate name to resume from (skip preceding gates).",
    ),
) -> None:
    """Run the full AutoMedia pipeline for a given topic and brand."""
    is_json = get_output_mode() == OutputMode.JSON

    if not _MODEL_CONFIG_PATH.is_file():
        if is_json:
            output_error_json(
                f"Model config not found: {_MODEL_CONFIG_PATH}\n"
                "Run 'automedia init' first to create it."
            )
        else:
            typer.secho(
                f"Model config not found: {_MODEL_CONFIG_PATH}\n"
                "Run 'automedia init' first to create it.",
                fg=typer.colors.RED,
                err=True,
            )
        raise typer.Exit(code=1)

    if not is_json:
        typer.echo(f"Starting pipeline: topic={topic!r}  brand={brand!r}  mode={mode}")
        if resume_from:
            typer.echo(f"Resuming from gate: {resume_from}")

    try:
        result = run_full_pipeline(
            topic,
            brand,
            mode=mode,
            decision_mode=decision_mode,
            resume_from=resume_from,
        )
    except Exception as exc:
        if is_json:
            output_error_json(f"Pipeline failed: {exc}")
        else:
            typer.secho(f"Pipeline failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if is_json:
        data: dict[str, Any] = {
            "status": result.status,
            "project_id": result.project_id,
            "project_dir": result.project_dir,
            "total_duration_s": result.total_duration_s,
        }
        if result.gates_log:
            data["gates_log"] = [asdict(e) for e in result.gates_log]
        if result.assets:
            data["assets"] = [asdict(a) for a in result.assets]
        if result.error:
            data["error"] = result.error
        output_json(data)
        if result.status == "failed":
            raise typer.Exit(code=1)
        return

    # Print summary
    colour = typer.colors.GREEN if result.status == "success" else typer.colors.YELLOW
    typer.secho(f"\nPipeline finished: {result.status}", fg=colour, bold=True)

    if result.project_id:
        typer.echo(f"  Project ID : {result.project_id}")
    if result.project_dir:
        typer.echo(f"  Project dir: {result.project_dir}")
    typer.echo(f"  Duration   : {result.total_duration_s:.1f}s")

    if result.gates_log:
        typer.echo(f"\n  Gates executed: {len(result.gates_log)}")
        for entry in result.gates_log:
            icon = "✓" if entry.status == "passed" else "✗"
            typer.echo(f"    {icon} {entry.gate_name} ({entry.duration_s:.2f}s)")

    if result.assets:
        typer.echo(f"\n  Assets produced: {len(result.assets)}")
        for asset in result.assets:
            typer.echo(f"    - [{asset.type}] {asset.path}")

    if result.error:
        typer.secho(f"\n  Error: {result.error}", fg=typer.colors.RED)

    if result.status == "failed":
        raise typer.Exit(code=1)
