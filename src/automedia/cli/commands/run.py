"""``automedia run`` — execute the full production pipeline."""

from __future__ import annotations

import shutil
import sys
import threading
from dataclasses import asdict
from typing import Any

import click
import typer

from automedia.cli.output import OutputMode, get_output_mode, output_error, output_text
from automedia.cli.output_format import output_formatted_error, output_pipeline_error
from automedia.core.logging import bind_correlation_id
from automedia.core.paths import get_user_config_dir
from automedia.core.project import Project, find_project_dir
from automedia.pipelines.gate_engine import PipelineProgress, PipelineResult
from automedia.pipelines.runner import VALID_MODES, run_full_pipeline

_MODEL_CONFIG_PATH = get_user_config_dir() / "model_config.yaml"

#: Per-gate status marker for the post-run summary.  ``skipped`` gets its own
#: marker instead of ✗ because a skipped gate did not fail — it evaluated
#: nothing (health-assessment P0-1: an un-run V gate must not read as either a
#: pass or a failure).
#: Process exit codes for ``automedia run``: 0 success, 1 failure, 2 is the
#: typer/click usage error, 3 = awaiting human review (the run parked at a
#: HITL gate — neither success nor failure).
EXIT_AWAITING_REVIEW = 3

_GATE_ICONS: dict[str, str] = {
    "passed": "✓",
    "failed": "✗",
    "error": "✗",
    "skipped": "⊘",
}


class CLIPipelineProgress(PipelineProgress):
    """Streams gate progress to the CLI terminal in real time."""

    def __init__(self, project_id: str = "") -> None:
        super().__init__(project_id)
        self._completed: int = 0
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def on_gate_start(
        self,
        gate_name: str,
        attempt_number: int = 1,
        retry_level: str | None = None,
        strategy_delta: dict[str, Any] | None = None,
    ) -> None:
        super().on_gate_start(
            gate_name,
            attempt_number=attempt_number,
            retry_level=retry_level,
            strategy_delta=strategy_delta,
        )
        sys.stdout.write(f"  {gate_name}...\n")
        sys.stdout.flush()

        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
        )
        self._heartbeat_thread.start()

    def on_gate_end(
        self,
        gate_name: str,
        passed: bool,
        duration: float,
        detail: str = "",
        attempt_number: int = 1,
        retry_level: str | None = None,
        strategy_delta: dict[str, Any] | None = None,
    ) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)

        super().on_gate_end(
            gate_name,
            passed,
            duration,
            detail=detail,
            attempt_number=attempt_number,
            retry_level=retry_level,
            strategy_delta=strategy_delta,
        )
        self._completed = len(self._gates_done)

        if passed:
            typer.secho(
                f"  {gate_name} ✅ ({duration:.1f}s) — passed",
                fg=typer.colors.GREEN,
                bold=True,
            )
        else:
            fail_reason = detail if detail else "failed"
            typer.secho(
                f"  {gate_name} ❌ ({duration:.1f}s) — {fail_reason}",
                fg=typer.colors.RED,
                bold=True,
            )

        total = self.total_gates or self._completed
        typer.secho(
            f"  [{self._completed}/{total} gates complete]",
            fg=typer.colors.BLUE,
        )

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(10):
            sys.stdout.write("  ·\n")
            sys.stdout.flush()


def _validate_brand(value: str) -> str:
    """Validate brand identifier is non-empty.

    An empty value means "not supplied": it is filled in from the parked
    project when ``--project-id`` is given, and rejected with a clear message
    afterwards if there is no project to take it from.
    """
    if not value:
        return value
    if not value.strip():
        raise typer.BadParameter("Brand identifier must not be empty")
    return value


def _resolve_resume_identity(project_id: str) -> tuple[str, str] | None:
    """Return ``(topic, brand)`` recorded on the parked *project_id*.

    ``None`` when the project cannot be found, so the caller can emit its own
    "no such project" error rather than a confusing missing-option one.
    """
    project_dir = find_project_dir(project_id)
    if project_dir is None:
        return None
    project = Project.load(project_dir)
    return project.topic, project.brand


def _is_failure_status(status: str, allow_partial: bool) -> bool:
    """Return ``True`` when *status* must exit non-zero.

    ``failed`` (pipeline-level error) always fails.  ``partial`` (a gate
    stopped the run) fails unless the caller explicitly opted in with
    ``--allow-partial``.  ``awaiting_review`` is neither success nor
    failure — it exits with its own code (3), so it never reads as a
    failure here.
    """
    if status == "failed":
        return True
    if status == "awaiting_review":
        return False
    return status == "partial" and not allow_partial


def run_cmd(
    topic: str | None = typer.Option(None, "--topic", "-t", help="Content topic / subject."),
    topics: str | None = typer.Option(
        None,
        "--topics",
        help="Comma-separated topics for batch mode (overrides --topic).",
    ),
    brand: str = typer.Option(
        "",
        "--brand",
        "-b",
        callback=_validate_brand,
        help="Brand identifier. Optional when --project-id is given; taken from the project.",
    ),
    mode: str = typer.Option(  # type: ignore[call-overload]  # external click.Choice vs typer's vendored click ParamType
        "auto",
        "--mode",
        "-m",
        click_type=click.Choice(list(VALID_MODES)),
        help=(
            "Pipeline mode: auto, text_only, text_with_cover, "
            "video_only, qa_only, image-carousel, social-thread, "
            "short-video, repurpose. video_only and short-video produce a "
            "video: without a configured video engine (or with no image/audio "
            "input to build it from) their V gates are reported as skipped and "
            "the run is marked partial."
        ),
    ),
    decision_mode: str = typer.Option(
        "build",
        "--decision-mode",
        help="(DEPRECATED) Decision mode for pipeline execution — no longer functional",
    ),
    resume_from: str | None = typer.Option(
        None,
        "--resume-from",
        help="Gate name to resume from (skip preceding gates).",
    ),
    auto_resume: bool = typer.Option(
        False,
        "--auto-resume",
        help="Resume from the last passed gate (reads history.db).",
    ),
    allow_partial: bool = typer.Option(
        False,
        "--allow-partial",
        help=(
            "Exit 0 when the pipeline stops at a gate (status 'partial'). "
            "A failed pipeline still exits non-zero."
        ),
    ),
    skip_review: bool = typer.Option(
        False,
        "--skip-review",
        help=(
            "Auto-pass the H0 human-review gate for unattended runs. "
            "Default pauses for human approval."
        ),
    ),
    wait_for_review: bool = typer.Option(
        False,
        "--wait-for-review",
        help=(
            "Prompt on stdin when the H0 gate pauses, so a human can approve or "
            "reject in this terminal. No-op when stdin is not a terminal; use "
            "`automedia hitl approve|reject <project_id>` instead."
        ),
    ),
    hitl_block: bool = typer.Option(
        False,
        "--hitl-block",
        help=(
            "Block at H0 even when stdin is not a TTY; for a human watching "
            "logs who will decide out-of-band."
        ),
    ),
    project_id: str | None = typer.Option(
        None,
        "--project-id",
        help=(
            "Resume an existing (parked) project by id, consuming a decision "
            "delivered by `automedia hitl approve`."
        ),
    ),
    hitl_timeout: float = typer.Option(
        None,
        "--hitl-timeout",
        help=(
            "Seconds to wait for an H0 decision before applying the timeout "
            "policy. Overrides gate_engine.hitl_timeout_s (default 3600)."
        ),
    ),
    hitl_on_timeout: str = typer.Option(
        None,
        "--hitl-on-timeout",
        help=(
            "What an undecided H0 pause does when the timeout expires: 'reject' "
            "fails the pipeline (default), 'approve' ships unreviewed content. "
            "Overrides gate_engine.hitl_on_timeout."
        ),
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full error traceback for debugging.",
    ),
    source_path: str = typer.Option(
        "",
        "--source-path",
        help="Path to a source document (.md, .txt, .pdf). Content is loaded into the pipeline.",
    ),
    source_url: str = typer.Option(
        "",
        "--source-url",
        help="URL to fetch source content from. Content is loaded into the pipeline.",
    ),
) -> None:
    """Run the full AutoMedia pipeline for a given topic and brand.

    Use --topic for a single topic or --topics for batch production
    (comma-separated, sequential execution with per-topic reporting).

    A run parked at the H0 human-review gate reports status
    "awaiting_review" and exits with code 3 — neither success (0) nor
    failure (1).  Decide out-of-band with `automedia hitl pending` /
    `automedia hitl approve <id>`, then resume the same project by
    passing `--project-id <id>`.
    """

    if not _MODEL_CONFIG_PATH.is_file():
        output_error(
            f"Model config not found: {_MODEL_CONFIG_PATH}\n"
            "Run 'automedia init' first to create it."
        )

    # ------------------------------------------------------------------
    # Batch mode (--topics)
    # ------------------------------------------------------------------
    if topics:
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        if not topic_list:
            output_error("No topics provided after splitting --topics.")
            raise typer.Exit(code=1)

        # Warn once if HyperFrames is missing and mode may need video
        if mode != "text_only" and shutil.which("hyperframes") is None:
            typer.secho(
                "⚠ HyperFrames not detected. Video quality gates (V0-V7) will be skipped.",
                fg=typer.colors.YELLOW,
            )
            typer.echo(
                "   Install HyperFrames for full video QA, or use --mode text_only to skip video."
            )

        batch_results: list[dict[str, Any]] = []
        for t in topic_list:
            if get_output_mode() == OutputMode.TEXT:
                typer.echo(f"\n{'=' * 60}")
                typer.echo(f"Batch topic: {t!r}  brand={brand!r}  mode={mode}")
                typer.echo(f"{'=' * 60}")

            try:
                bind_correlation_id()
                cli_progress = (
                    CLIPipelineProgress() if get_output_mode() == OutputMode.TEXT else None
                )
                result = run_full_pipeline(
                    t,
                    brand,
                    mode=mode,
                    decision_mode=decision_mode,
                    resume_from=resume_from,
                    auto_resume=auto_resume,
                    skip_review=skip_review,
                    hitl_timeout_s=hitl_timeout,
                    hitl_on_timeout=hitl_on_timeout,
                    wait_for_review=wait_for_review,
                    progress=cli_progress,
                    source_path=source_path,
                    source_url=source_url,
                    block_on_hitl=(True if hitl_block else None),
                    resume_project_id=project_id,
                )
                batch_results.append(
                    {
                        "topic": t,
                        "status": result.status,
                        "project_id": result.project_id,
                        "error": result.error,
                    }
                )
            except Exception as exc:
                batch_results.append(
                    {
                        "topic": t,
                        "status": "failed",
                        "project_id": "",
                        "error": {
                            "code": "CLI_ERROR",
                            "message": str(exc),
                            "resolution": (
                                "Check the error message and fix the issue before retrying"
                            ),
                        },
                    }
                )
                if verbose:
                    import traceback as _tb

                    _tb.print_exc()

        # Batch summary
        passed = sum(1 for r in batch_results if r["status"] == "success")
        awaiting = sum(1 for r in batch_results if r["status"] == "awaiting_review")
        failed = len(batch_results) - passed - awaiting

        if get_output_mode() == OutputMode.JSON:
            output_text(
                None,
                data={
                    "results": batch_results,
                    "passed": passed,
                    "awaiting": awaiting,
                    "failed": failed,
                },
            )
        else:
            if failed:
                icon = typer.colors.YELLOW
            elif awaiting:
                icon = typer.colors.CYAN
            else:
                icon = typer.colors.GREEN
            typer.secho(
                f"\n{'=' * 60}\n"
                f"Batch complete — {passed}/{len(batch_results)} passed, "
                f"{awaiting} awaiting, {failed} failed",
                fg=icon,
                bold=True,
            )
            for r in batch_results:
                if r["status"] == "success":
                    status_icon = "✓"
                elif r["status"] == "awaiting_review":
                    status_icon = "⊘"
                else:
                    status_icon = "✗"
                pid = r["project_id"] or "(none)"
                typer.echo(f"  {status_icon} {r['topic']!r} → {r['status']}  [{pid}]")
                if r["error"]:
                    typer.secho(f"       error: {r['error']}", fg=typer.colors.RED)

        if failed:
            raise typer.Exit(code=1)
        if awaiting:
            raise typer.Exit(code=EXIT_AWAITING_REVIEW)
        return

    # ------------------------------------------------------------------
    # Single topic mode (--topic)
    # ------------------------------------------------------------------
    if not topic:
        if project_id:
            # A parked project already knows its own topic/brand, so resuming it
            # must not force the operator to retype them (#108).
            resolved = _resolve_resume_identity(project_id)
            if resolved is not None:
                topic, brand = topic or resolved[0], brand or resolved[1]
        if not topic:
            output_error("Either --topic or --topics is required.")
            raise typer.Exit(code=1)
    if not brand:
        output_error("--brand is required unless --project-id supplies it.")
        raise typer.Exit(code=1)

    if skip_review and wait_for_review:
        output_error(
            "--skip-review and --wait-for-review are mutually exclusive: the "
            "first removes the pause, the second waits for it."
        )
        raise typer.Exit(code=1)

    if skip_review and hitl_block:
        output_error(
            "--skip-review and --hitl-block are mutually exclusive: the "
            "first removes the pause, the second forces the run to wait at it."
        )
        raise typer.Exit(code=1)

    if hitl_on_timeout is not None and hitl_on_timeout not in ("approve", "reject"):
        output_error(f"--hitl-on-timeout must be 'approve' or 'reject', got {hitl_on_timeout!r}.")
        raise typer.Exit(code=1)

    if hitl_timeout is not None and hitl_timeout <= 0:
        output_error("--hitl-timeout must be a positive number of seconds.")
        raise typer.Exit(code=1)

    if get_output_mode() == OutputMode.TEXT:
        typer.echo(f"Starting pipeline: topic={topic!r}  brand={brand!r}  mode={mode}")
        if resume_from:
            typer.echo(f"Resuming from gate: {resume_from}")
        if source_path:
            typer.echo(f"Source path: {source_path}")
        if source_url:
            typer.echo(f"Source URL: {source_url}")

    # Warn if HyperFrames is missing and mode may need video
    if mode != "text_only" and shutil.which("hyperframes") is None:
        typer.secho(
            "⚠ HyperFrames not detected. Video quality gates (V0-V7) will be skipped.",
            fg=typer.colors.YELLOW,
        )
        typer.echo(
            "   Install HyperFrames for full video QA, or use --mode text_only to skip video."
        )

    pipeline_result: PipelineResult | None = None
    try:
        bind_correlation_id()
        cli_progress = CLIPipelineProgress() if get_output_mode() == OutputMode.TEXT else None
        pipeline_result = run_full_pipeline(
            topic,
            brand,
            mode=mode,
            decision_mode=decision_mode,
            resume_from=resume_from,
            auto_resume=auto_resume,
            skip_review=skip_review,
            hitl_timeout_s=hitl_timeout,
            hitl_on_timeout=hitl_on_timeout,
            wait_for_review=wait_for_review,
            progress=cli_progress,
            source_path=source_path,
            source_url=source_url,
            block_on_hitl=(True if hitl_block else None),
            resume_project_id=project_id,
        )
    except Exception as exc:
        output_formatted_error(
            "Pipeline stopped",
            error=str(exc),
            verbose=verbose,
            exc_info=exc,
            gates_log=pipeline_result.gates_log if pipeline_result else None,
        )
        raise typer.Exit(code=1) from exc

    data: dict[str, Any] = {
        "status": pipeline_result.status,
        "project_id": pipeline_result.project_id,
        "project_dir": pipeline_result.project_dir,
        "total_duration_s": pipeline_result.total_duration_s,
    }
    if pipeline_result.gates_log:
        data["gates_log"] = [asdict(e) for e in pipeline_result.gates_log]
    if pipeline_result.assets:
        data["assets"] = [asdict(a) for a in pipeline_result.assets]
    if pipeline_result.error:
        data["error"] = pipeline_result.error

    if output_text(None, data=data):
        if pipeline_result.status == "awaiting_review":
            raise typer.Exit(code=EXIT_AWAITING_REVIEW)
        if _is_failure_status(pipeline_result.status, allow_partial):
            raise typer.Exit(code=1)
        return

    # Print summary
    if pipeline_result.status == "success":
        colour = typer.colors.GREEN
    elif pipeline_result.status == "awaiting_review":
        colour = typer.colors.CYAN
    else:
        colour = typer.colors.YELLOW
    typer.secho(f"\nPipeline finished: {pipeline_result.status}", fg=colour, bold=True)

    if pipeline_result.project_id:
        typer.echo(f"  Project ID : {pipeline_result.project_id}")
    if pipeline_result.project_dir:
        typer.echo(f"  Project dir: {pipeline_result.project_dir}")
    typer.echo(f"  Duration   : {pipeline_result.total_duration_s:.1f}s")

    if pipeline_result.gates_log:
        typer.echo(f"\n  Gates executed: {len(pipeline_result.gates_log)}")
        for entry in pipeline_result.gates_log:
            icon = _GATE_ICONS.get(entry.status, "")
            typer.echo(f"    {icon} {entry.gate_name} ({entry.duration_s:.2f}s)")

    if pipeline_result.affected_downstream:
        typer.secho(
            f"⚠ Downstream affected: {', '.join(pipeline_result.affected_downstream)}",
            fg=typer.colors.YELLOW,
        )

    if pipeline_result.assets:
        typer.echo(f"\n  Assets produced: {len(pipeline_result.assets)}")
        for asset in pipeline_result.assets:
            typer.echo(f"    - [{asset.type}] {asset.path}")

    if pipeline_result.error:
        output_pipeline_error(
            pipeline_result.error,
            gates_log=pipeline_result.gates_log,
            verbose=verbose,
        )

    if pipeline_result.status == "awaiting_review":
        parked_id = pipeline_result.project_id or "<project_id>"
        typer.secho(
            "\n⚠ Project is parked awaiting human review (H0).",
            fg=typer.colors.CYAN,
            bold=True,
        )
        typer.echo(
            "  Decide out-of-band: `automedia hitl pending` / "
            f"`automedia hitl approve {parked_id}`."
        )
        typer.echo(
            f"  Then resume it: `automedia run --topic {topic!r} --brand {brand!r} "
            f"--project-id {parked_id}`."
        )
        raise typer.Exit(code=EXIT_AWAITING_REVIEW)

    if _is_failure_status(pipeline_result.status, allow_partial):
        raise typer.Exit(code=1)
