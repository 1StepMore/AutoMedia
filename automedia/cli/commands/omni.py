"""``automedia omni`` — manage Omni MCP adapter servers."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import typer

from automedia.mcp.parallel import start_parallel_servers, stop_parallel_servers

logger = logging.getLogger(__name__)

app = typer.Typer(name="omni", help="Manage Omni MCP adapter servers.")


# ---------------------------------------------------------------------------
# omni start-all
# ---------------------------------------------------------------------------


@app.command("start-all")
def omni_start_all(
    mode: str = typer.Option(
        "all",
        "--mode",
        "-m",
        help="Server mode: all, parallel, proxy, sdk.",
    ),
) -> None:
    """Launch all MCP servers in parallel and block until Ctrl+C.

    Starts the main AutoMedia MCP server together with OPP, OL, and ORF
    adapter servers.  Each server runs as an independent subprocess with
    stdio transport.
    """
    servers = start_parallel_servers(mode=mode)

    typer.echo(f"Launched {len(servers)} server(s):")
    for name, proc in servers.items():
        typer.echo(f"  [{name}] started (PID: {proc.pid})")
    typer.echo()
    typer.echo("Press Ctrl+C to shut down all servers.")

    try:
        # Block until interrupted
        while True:
            time.sleep(1)
            # Check if any server died unexpectedly
            for name, proc in list(servers.items()):
                if proc.poll() is not None:
                    typer.secho(
                        f"[{name}] exited unexpectedly (return code: {proc.returncode})",
                        fg=typer.colors.RED,
                        err=True,
                    )
    except KeyboardInterrupt:
        typer.echo("\nShutting down all servers...")
        stop_parallel_servers(servers)
        typer.echo("All servers stopped.")


# ---------------------------------------------------------------------------
# omni start
# ---------------------------------------------------------------------------


@app.command("start")
def omni_start(
    mode: str = typer.Option(
        "sdk",
        "--mode",
        "-m",
        help="Server mode: parallel, proxy, sdk.",
    ),
) -> None:
    """Start MCP servers based on the selected mode.

    When ``--mode parallel``, launches all servers in parallel (equivalent
    to ``start-all``).  Other modes launch a single main server.
    """
    if mode == "parallel":
        omni_start_all(mode=mode)
        return

    servers = start_parallel_servers(mode=mode)
    typer.echo(f"Launched {len(servers)} server(s) in {mode} mode:")
    for name, proc in servers.items():
        typer.echo(f"  [{name}] started (PID: {proc.pid})")
    typer.echo()
    typer.echo("Press Ctrl+C to shut down all servers.")

    try:
        while True:
            time.sleep(1)
            for name, proc in list(servers.items()):
                if proc.poll() is not None:
                    typer.secho(
                        f"[{name}] exited unexpectedly (return code: {proc.returncode})",
                        fg=typer.colors.RED,
                        err=True,
                    )
    except KeyboardInterrupt:
        typer.echo("\nShutting down all servers...")
        stop_parallel_servers(servers)
        typer.echo("All servers stopped.")


# ---------------------------------------------------------------------------
# omni localize — translate project markdown via OLAdapter
# ---------------------------------------------------------------------------


@app.command("localize")
def omni_localize(
    project: str = typer.Option(
        ..., "--project", help="Project directory path (root containing 01_content/drafts/)."
    ),
    target_langs: str = typer.Option(
        ..., "--target-langs", help="Comma-separated target language codes, e.g. en,ja,zh-CN."
    ),
) -> None:
    """Translate project markdown content into one or more target languages.

    Reads markdown files from ``01_content/drafts/``, translates each into
    every specified target language via OLAdapter, and writes the translated
    files into ``05_publish/{lang}/``.
    """
    from automedia.gates.translation_quality import L4TranslationQuality
    from automedia.omni.ol_adapter import OLAdapter
    from automedia.omni.artifact_mapping import ol_output_path

    project_dir = Path(project)
    drafts_dir = project_dir / "01_content" / "drafts"

    if not drafts_dir.is_dir():
        typer.secho(
            f"Drafts directory not found: {drafts_dir}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    langs = [lang.strip() for lang in target_langs.split(",") if lang.strip()]
    if not langs:
        typer.secho("No target languages specified.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    md_files = sorted(drafts_dir.glob("*.md"))
    if not md_files:
        typer.secho(f"No markdown files found in {drafts_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    adapter = OLAdapter()
    produced: list[Path] = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        for lang in langs:
            try:
                result = adapter.translate(
                    md_content=content,
                    source_lang="auto",
                    target_lang=lang,
                )
            except Exception as exc:
                typer.secho(
                    f"Translation failed for {md_file.name} \u2192 {lang}: {exc}",
                    fg=typer.colors.RED,
                    err=True,
                )
                continue

            # L4 Translation Quality gate (non-blocking warning only)
            gate = L4TranslationQuality()
            gate_result = gate.execute(
                {
                    "translation_result": result,
                    "source_lang": "auto",
                    "target_lang": lang,
                }
            )
            if not gate_result["passed"]:
                all_issues = list(gate_result.get("warnings", [])) + list(
                    gate_result.get("failures", [])
                )
                typer.secho(
                    f"L4 quality gate: {md_file.name} → {lang}: {'; '.join(all_issues)}",
                    err=True,
                )

            output_dir = ol_output_path(project_dir, lang, mkdir=True)
            output_file = output_dir / md_file.name
            output_file.write_text(result.translated_md, encoding="utf-8")
            produced.append(output_file)

    if not produced:
        typer.secho("No files were produced.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Localised {len(produced)} file(s):")
    for path in produced:
        typer.echo(f"  {path}")


# ---------------------------------------------------------------------------
# omni format-output — convert markdown to a target format via ORFAdapter
# ---------------------------------------------------------------------------


@app.command("format-output")
def omni_format_output(
    input: str = typer.Option(
        ..., "--input", help="Input markdown file path."
    ),
    target_format: str = typer.Option(
        ..., "--target-format", help="Target output format (e.g. docx, pdf, html)."
    ),
) -> None:
    """Convert a markdown file to the specified output format.

    Uses ORFAdapter to perform the conversion.  The output file is written
    alongside the input file with the new extension.
    """
    from automedia.omni.orf_adapter import ORFAdapter

    input_path = Path(input)
    if not input_path.is_file():
        typer.secho(
            f"Input file not found: {input_path}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    output_path = input_path.with_suffix(f".{target_format}")
    adapter = ORFAdapter()

    try:
        result = adapter.convert(
            file_path=str(input_path),
            output_path=str(output_path),
        )
    except Exception as exc:
        typer.secho(
            f"Format conversion failed: {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    actual_output = result.get("output_path", str(output_path))
    typer.echo(f"Output: {actual_output}")


# ---------------------------------------------------------------------------
# omni ingest — extract documents into markdown via OPPAdapter
# ---------------------------------------------------------------------------


@app.command("ingest")
def omni_ingest(
    dir: str = typer.Option(
        ..., "--dir", help="Directory to scan for supported documents."
    ),
    output_dir: str = typer.Option(
        ..., "--output-dir", help="Directory to write extracted markdown files."
    ),
) -> None:
    """Extract content from supported documents into markdown files.

    Scans *dir* for supported file types (.docx, .pptx, .pdf, .xlsx, .md,
    .txt), extracts their content via OPPAdapter, and writes the resulting
    markdown into *output_dir*.
    """
    from automedia.omni.opp_adapter import OPPAdapter

    scan_dir = Path(dir)
    out_dir = Path(output_dir)

    if not scan_dir.is_dir():
        typer.secho(
            f"Input directory not found: {scan_dir}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    supported_exts = {".docx", ".pptx", ".pdf", ".xlsx", ".md", ".txt"}
    files = sorted(
        f for f in scan_dir.iterdir()
        if f.suffix.lower() in supported_exts and f.is_file()
    )

    if not files:
        typer.echo(f"No supported documents found in {scan_dir}")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = OPPAdapter()
    processed: list[Path] = []

    for file in files:
        try:
            result = adapter.extract(str(file))
        except Exception as exc:
            typer.secho(
                f"Extraction failed for {file.name}: {exc}",
                fg=typer.colors.RED,
                err=True,
            )
            continue

        output_file = out_dir / f"{file.stem}.md"
        output_file.write_text(result.md_content, encoding="utf-8")
        processed.append(output_file)

    if not processed:
        typer.secho("No files were successfully processed.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Ingested {len(processed)} file(s):")
    for path in processed:
        typer.echo(f"  {path}")
